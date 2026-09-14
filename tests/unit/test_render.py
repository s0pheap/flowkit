"""Server-side final render (agent/services/render.py, agent/api/render.py).

Pure helpers are tested directly. One end-to-end test builds a three-scene video
from generated clips with real ffmpeg (skipped when ffmpeg isn't installed) and
checks the output the way /fk-concat-fit-narrator's verify step did.
"""
import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from agent import auth, config
from agent.api import active_project, look_feel
from agent.db import crud, schema
from agent.main import app
from agent.services import render
from agent.utils import paths

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
ADMIN_KEY = "admin-render-key"
PROJECT = "cccccccc-0000-4000-8000-000000000001"
OTHER = "dddddddd-0000-4000-8000-000000000002"


# ─── Pure helpers ────────────────────────────────────────────

class TestHelpers:
    def test_output_size_keeps_1080p_for_small_sources(self):
        assert render.output_size("HORIZONTAL", {"width": 1280, "height": 720}) == (1920, 1080)
        assert render.output_size("VERTICAL", None) == (1080, 1920)

    def test_output_size_never_downscales_4k(self):
        assert render.output_size("HORIZONTAL", {"width": 3840, "height": 2160}) == (3840, 2160)
        # A landscape 4K clip in a vertical video does not set the size.
        assert render.output_size("VERTICAL", {"width": 3840, "height": 2160}) == (1080, 1920)

    def test_problems_lists_missing_and_expired_sources(self):
        past = int(time.time()) - 10
        plan = {"segments": [
            {"display_order": 0, "mode": "generate", "video_source": None},
            {"display_order": 1, "mode": "generate", "video_source": f"https://x/video/a?Expires={past}"},
            {"display_order": 2, "mode": "ffmpeg", "needs_render": True, "image_url": None},
            {"display_order": 3, "mode": "ffmpeg", "needs_render": True, "image_url": "https://x/image/b"},
            {"display_order": 4, "mode": "generate", "video_source": "output/x/4k/scene.mp4"},
        ]}
        issues = render.problems(plan)
        assert len(issues) == 3
        assert "Scene 1 has no video" in issues[0]
        assert "/fk-refresh-urls" in issues[1]
        assert "keyframe" in issues[2]

    def test_segment_command_mixes_narration_and_adds_silence_when_clip_is_mute(self, tmp_path):
        seg = {"duration": 2.5, "trim_start": 1.0}
        cmd = render.segment_command(seg, "clip.mp4", False, tmp_path / "o.mp4", 1920, 1080, "n.wav", [])
        joined = " ".join(cmd)
        assert "-ss 1.0 -i clip.mp4 -i n.wav" in joined
        assert "anullsrc" in joined and "[2:a]volume=0.3" in joined and "[1:a]volume=1.5" in joined
        assert cmd[cmd.index("-t", cmd.index("-map")) + 1] == "2.5"
        assert "-ar 48000 -ac 2" in joined

    def test_segment_command_slows_a_stretched_clip_and_its_sound(self, tmp_path):
        seg = {"duration": 10.0, "trim_start": 1.0, "speed": 0.7}
        joined = " ".join(render.segment_command(seg, "clip.mp4", True, tmp_path / "o.mp4", 1920, 1080, "n.wav", []))
        assert "[0:v]setpts=(PTS-STARTPTS)/0.7,scale=" in joined
        assert "[0:a]atempo=0.7[slow];[slow]volume=0.3" in joined
        normal = " ".join(render.segment_command({"duration": 5.0, "trim_start": 1.0}, "clip.mp4", True,
                                                 tmp_path / "o.mp4", 1920, 1080, None, []))
        assert "setpts" not in normal and "atempo" not in normal

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    def test_stretched_segment_really_lasts_the_fixed_length(self, tmp_path):
        ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=3", "-f", "lavfi", "-i",
           "sine=frequency=330:duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(tmp_path / "c.mp4"))
        out = tmp_path / "o.mp4"
        seg = {"duration": 4.0, "trim_start": 1.0, "speed": 0.5}
        subprocess.run(render.segment_command(seg, str(tmp_path / "c.mp4"), True, out, 640, 360, None, []), check=True)
        length = float(json.loads(probe(out, "format=duration"))["format"]["duration"])
        assert abs(length - 4.0) < 0.15

    def test_music_command_loops_fades_and_ducks(self, tmp_path):
        cmd = render.music_command(tmp_path / "v.mp4", tmp_path / "m.mp3", tmp_path / "o.mp4", 20.0, volume=0.2)
        joined = " ".join(cmd)
        assert "-stream_loop -1 -i" in joined and "-c:v copy" in joined
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "atrim=0:20.000" in graph and "volume=0.200" in graph
        assert "afade=t=in:st=0:d=1.00" in graph and "afade=t=out:st=17.000:d=3.00" in graph
        assert "sidechaincompress" in graph and "normalize=0" in graph
        plain = render.music_command(tmp_path / "v.mp4", tmp_path / "m.mp3", tmp_path / "o.mp4", 2.0,
                                     duck=False, fade_in=0, fade_out=5)
        graph = plain[plain.index("-filter_complex") + 1]
        assert "sidechaincompress" not in graph and "afade=t=in" not in graph and "st=1.000:d=1.00" in graph

    def test_music_file_stays_in_the_project_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "OUTPUT_DIR", tmp_path)
        folder = render.music_dir("proj")
        folder.mkdir(parents=True)
        (folder / "bed.mp3").write_bytes(b"x")
        (folder / "notes.txt").write_bytes(b"x")
        (tmp_path / "proj" / "secret.mp3").write_bytes(b"x")
        assert render.music_file("proj", "bed.mp3") == (folder / "bed.mp3").resolve()
        for bad in ("notes.txt", "../secret.mp3", "..\\secret.mp3","", ".bed.mp3", "C:bed.mp3", "missing.mp3"):
            assert render.music_file("proj", bad) is None, bad
        assert [p.name for p in render.list_music("proj")] == ["bed.mp3"]

    def test_overlay_text_goes_through_files(self, tmp_path, monkeypatch):
        font = tmp_path / "font.ttf"
        font.write_bytes(b"")
        monkeypatch.setattr(config, "OVERLAY_FONT", str(font))
        filters = render.overlay_filters([{"text": "It's 50% : done", "style": "cost", "_align": 2}],
                                         tmp_path, "scene_000", 4.0, 1920)
        assert len(filters) == 1
        assert "textfile=" in filters[0] and "It's" not in filters[0]
        assert "fontcolor=0xFFD700" in filters[0] and "x=w-text_w-40" in filters[0]
        assert (tmp_path / "scene_000_overlay0.txt").read_text(encoding="utf-8") == "It's 50% : done"


# ─── API + a real render ─────────────────────────────────────

@pytest.fixture
async def env(tmp_path, monkeypatch):
    await schema.close_db()
    out = tmp_path / "output"
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "render.db")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "OUTPUT_DIR", out)
    monkeypatch.setattr(paths, "OUTPUT_DIR", out)
    monkeypatch.setattr(look_feel, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setattr(active_project, "_STATE_FILE", tmp_path / "active.json")
    render._jobs.clear()
    await schema.init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100") as client:
        yield tmp_path, client
    await schema.close_db()


def ff(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True, cwd=cwd)


def probe(path, entries):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
                          capture_output=True, text=True, check=True).stdout


async def make_user(client, name, project):
    r = await client.post("/api/admin/users", headers={"X-API-Key": ADMIN_KEY},
                          json={"name": name, "project_ids": [project]})
    return {"X-API-Key": r.json()["api_key"]}


async def seed_video(root: Path):
    """Three scenes: a Veo clip with sound + narration + overlay fading into a mute Veo clip, then an ffmpeg scene."""
    await crud.create_project(name="Render Test", id=PROJECT, language="en")
    video = await crud.create_video(project_id=PROJECT, title="v", orientation="HORIZONTAL")
    slug = "render_test"
    src = root / "src"
    src.mkdir()
    ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=3", "-f", "lavfi", "-i",
       "sine=frequency=330:duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src / "a.mp4"))
    ff("-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=3", "-c:v", "libx264", "-an", str(src / "b.mp4"))
    ff("-f", "lavfi", "-i", "color=c=teal:size=1280x720", "-frames:v", "1", str(src / "key.png"))

    scenes = []
    for order in range(3):
        scenes.append(await crud.create_scene(video_id=video["id"], display_order=order, prompt=f"scene {order}"))
    await crud.update_scene(scenes[0]["id"], horizontal_video_url=(src / "a.mp4").as_uri(),
                            narrator_text="Hello there. This is a test.",
                            look_feel=json.dumps({"mode": "generate", "transition": "fade", "transition_duration": 0.5}))
    await crud.update_scene(scenes[1]["id"], horizontal_video_url=(src / "b.mp4").as_uri())
    await crud.update_scene(scenes[2]["id"], horizontal_image_url=str(src / "key.png"),
                            look_feel=json.dumps({"mode": "ffmpeg", "motion": "zoom_in", "duration": 1.5}))

    wav = paths.scene_tts_path(slug, 0, scenes[0]["id"])
    wav.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", "sine=frequency=660:duration=1.2", "-ar", "24000", "-ac", "1", str(wav))
    words = [{"word": w, "start": 0.1 + i * 0.18, "end": 0.25 + i * 0.18}
             for i, w in enumerate("Hello there. This is a test.".split())]
    wav.with_suffix(".words.json").write_text(json.dumps(
        {"text": "Hello there. This is a test.", "words": words, "timing_source": "gemini", "duration": 1.2}))
    return video, scenes


async def wait_for(client, vid, headers, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = (await client.get(f"/api/videos/{vid}/render", headers=headers)).json()
        if status["status"] in ("done", "failed"):
            return status
        await asyncio.sleep(0.5)
    pytest.fail(f"render did not finish: {status}")


class TestRenderApi:
    async def test_not_ready_video_is_refused_with_reasons(self, env):
        _root, client = env
        await crud.create_project(name="Empty", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v", orientation="HORIZONTAL")
        await crud.create_scene(video_id=video["id"], display_order=0, prompt="p")
        r = await client.post(f"/api/videos/{video['id']}/render", headers={"X-API-Key": ADMIN_KEY}, json={})
        assert r.status_code == 409
        assert "Run /fk-gen-videos" in r.json()["detail"]["problems"][0]

    async def test_other_users_cannot_render_or_download(self, env):
        _root, client = env
        await crud.create_project(name="Mine", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v")
        bob = await make_user(client, "bob", OTHER)
        for method, path in (("POST", "render"), ("GET", "render"), ("GET", "final.mp4"), ("GET", "captions.srt"),
                             ("PUT", "text-overlays"), ("GET", "review-feedback")):
            r = await client.request(method, f"/api/videos/{video['id']}/{path}", headers=bob,
                                     json={} if method != "GET" else None)
            assert r.status_code == 404, path

    async def test_media_token_only_opens_file_routes(self, env):
        _root, client = env
        await crud.create_project(name="Mine", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v")
        alice = await make_user(client, "alice", PROJECT)
        token = (await client.get("/api/auth/media-token", headers=alice)).json()["token"]
        assert (await client.get(f"/api/videos/{video['id']}/final.mp4?token={token}")).status_code == 404  # authed, no file
        assert (await client.get(f"/api/videos/{video['id']}/final.mp4?token=bad")).status_code == 401
        assert (await client.get(f"/api/videos/{video['id']}/render?token={token}")).status_code == 401
        assert (await client.get(f"/api/projects?token={token}")).status_code == 401

    async def test_text_overlays_are_validated(self, env):
        _root, client = env
        await crud.create_project(name="Mine", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v")
        key = {"X-API-Key": ADMIN_KEY}
        bad = await client.put(f"/api/videos/{video['id']}/text-overlays", headers=key,
                               json={"0": [{"text": "x", "style": "shout"}]})
        assert bad.status_code == 400
        good = await client.put(f"/api/videos/{video['id']}/text-overlays", headers=key,
                                json={"0": [{"text": "22 Feb 2026", "style": "date"}]})
        assert good.json() == {"scenes": 1, "items": 1}
        assert (await client.get(f"/api/videos/{video['id']}/text-overlays", headers=key)).json()["0"][0]["style"] == "date"

    async def test_review_board_page_is_public_and_feedback_is_per_project(self, env):
        _root, client = env
        assert (await client.get("/review-board")).status_code == 200
        await crud.create_project(name="Mine", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v")
        alice = await make_user(client, "alice", PROJECT)
        await client.put(f"/api/videos/{video['id']}/review-feedback", headers=alice, json={"s1": {"rating": "good"}})
        assert (await client.get(f"/api/videos/{video['id']}/review-feedback", headers=alice)).json() == {"s1": {"rating": "good"}}

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    async def test_music_tracks_upload_list_and_delete(self, env):
        root, client = env
        await crud.create_project(name="Mine", id=PROJECT)
        video = await crud.create_video(project_id=PROJECT, title="v")
        vid = video["id"]
        alice = await make_user(client, "alice", PROJECT)
        bob = await make_user(client, "bob", OTHER)
        ff("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(root / "bed.mp3"))
        data = (root / "bed.mp3").read_bytes()

        assert (await client.put(f"/api/videos/{vid}/music/bed.mp3", headers=bob, content=data)).status_code == 404
        assert (await client.put(f"/api/videos/{vid}/music/bed.exe", headers=alice, content=data)).status_code == 400
        assert (await client.put(f"/api/videos/{vid}/music/fake.mp3", headers=alice, content=b"not audio")).status_code == 400
        up = await client.put(f"/api/videos/{vid}/music/My Song (v2).mp3", headers=alice, content=data)
        assert up.status_code == 200, up.text
        assert up.json()["name"] == "My Song (v2).mp3" and up.json()["duration"] == pytest.approx(2, abs=0.2)

        tracks = (await client.get(f"/api/videos/{vid}/music", headers=alice)).json()["tracks"]
        assert [t["name"] for t in tracks] == ["My Song (v2).mp3"]
        assert not list((root / "output" / "mine" / "music").glob(".*"))  # no partial upload left behind
        token = (await client.get("/api/auth/media-token", headers=alice)).json()["token"]
        played = await client.get(f"{tracks[0]['url']}?token={token}")
        assert played.status_code == 200 and played.headers["content-type"] == "audio/mpeg"

        missing = await client.post(f"/api/videos/{vid}/render", headers=alice, json={"music": {"track": "nope.mp3"}})
        assert missing.status_code in (404, 409)
        assert (await client.delete(f"/api/videos/{vid}/music/My Song (v2).mp3", headers=bob)).status_code == 404
        assert (await client.delete(f"/api/videos/{vid}/music/My Song (v2).mp3", headers=alice)).json() == {"ok": True}
        assert (await client.get(f"/api/videos/{vid}/music", headers=alice)).json() == {"tracks": []}

    async def test_duplicate_project_names_are_refused(self, env):
        _root, client = env
        await crud.create_project(name="Moon Base", id=PROJECT)
        other = await crud.create_project(name="Other", id=OTHER)
        r = await client.patch(f"/api/projects/{other['id']}", headers={"X-API-Key": ADMIN_KEY}, json={"name": "moon base"})
        assert r.status_code == 409

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    async def test_full_render(self, env):
        root, client = env
        video, scenes = await seed_video(root)
        alice = await make_user(client, "alice", PROJECT)
        vid = video["id"]
        await client.put(f"/api/videos/{vid}/text-overlays", headers=alice,
                         json={"0": [{"text": "22 Feb 2026", "style": "date"}]})

        plan = (await client.get(f"/api/videos/{vid}/assembly-plan", headers=alice)).json()
        started = await client.post(f"/api/videos/{vid}/render", headers=alice, json={"subs": "soft"})
        assert started.status_code == 202, started.text
        again = await client.post(f"/api/videos/{vid}/render", headers=alice, json={})
        assert again.status_code in (202, 409)

        status = await wait_for(client, vid, alice)
        assert status["status"] == "done", status
        assert status["done_steps"] == status["total_steps"]
        assert status["download_url"] == f"/api/videos/{vid}/final.mp4"
        assert abs(status["duration"] - plan["total_duration"]) < 0.35

        out = root / status["output_path"]
        streams = json.loads(probe(out, "stream=codec_type,codec_name,width,height,sample_rate,channels"))["streams"]
        kinds = {s["codec_type"] for s in streams}
        assert kinds == {"video", "audio", "subtitle"}
        video_stream = next(s for s in streams if s["codec_type"] == "video")
        assert (video_stream["width"], video_stream["height"]) == (1920, 1080)
        audio = next(s for s in streams if s["codec_type"] == "audio")
        assert (audio["sample_rate"], audio["channels"]) == ("48000", 2)
        assert (root / "output" / "render_test" / "motion").exists()  # the ffmpeg scene was rendered by the job

        dl = await client.get(f"/api/videos/{vid}/final.mp4?download=1", headers=alice)
        assert dl.status_code == 200 and dl.headers["content-type"] == "video/mp4"
        assert "attachment" in dl.headers.get("content-disposition", "")
        ranged = await client.get(f"/api/videos/{vid}/final.mp4", headers={**alice, "Range": "bytes=0-99"})
        assert ranged.status_code == 206 and len(ranged.content) == 100
        srt = await client.get(f"/api/videos/{vid}/captions.srt", headers=alice)
        assert "Hello there." in srt.text

        # A restart forgets live jobs; the status file still answers.
        render._jobs.clear()
        assert (await client.get(f"/api/videos/{vid}/render", headers=alice)).json()["status"] == "done"

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    async def test_burned_subtitles(self, env):
        root, client = env
        video, _ = await seed_video(root)
        key = {"X-API-Key": ADMIN_KEY}
        await client.post(f"/api/videos/{video['id']}/render", headers=key, json={"subs": "burn"})
        status = await wait_for(client, video["id"], key)
        assert status["status"] == "done", status
        kinds = {s["codec_type"] for s in json.loads(probe(root / status["output_path"], "stream=codec_type"))["streams"]}
        assert kinds == {"video", "audio"}

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    async def test_each_video_of_a_project_keeps_its_own_render(self, env):
        root, client = env
        video, _ = await seed_video(root)
        other = await crud.create_video(project_id=PROJECT, title="khmer", orientation="HORIZONTAL")
        key = {"X-API-Key": ADMIN_KEY}
        await client.post(f"/api/videos/{video['id']}/render", headers=key, json={"subs": "none"})
        status = await wait_for(client, video["id"], key)
        assert status["status"] == "done", status
        assert video["id"][:8] in status["output_path"]
        assert (root / "output" / "render_test" / "render_status" / f"{video['id']}.json").exists()
        # The other video in the same project has no render and cannot download this one.
        assert (await client.get(f"/api/videos/{other['id']}/render", headers=key)).json()["status"] == "none"
        assert (await client.get(f"/api/videos/{other['id']}/final.mp4", headers=key)).status_code == 404
        assert (await client.get(f"/api/videos/{video['id']}/final.mp4", headers=key)).status_code == 200

    async def test_legacy_project_status_answers_only_for_its_video(self, env):
        root, _client = env
        folder = root / "output" / "legacy"
        folder.mkdir(parents=True)
        (folder / "legacy_narrator_cut.mp4").write_bytes(b"x")
        (folder / "render_status.json").write_text(json.dumps({
            "video_id": "aaaa1111-0000", "slug": "legacy", "status": "done",
            "output_path": "output/legacy/legacy_narrator_cut.mp4"}), encoding="utf-8")
        assert render.get_job("aaaa1111-0000", "legacy").status == "done"
        assert render.final_file("aaaa1111-0000", "legacy").name == "legacy_narrator_cut.mp4"
        assert render.get_job("bbbb2222-0000", "legacy") is None

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    async def test_render_with_background_music(self, env):
        root, client = env
        video, _ = await seed_video(root)
        vid = video["id"]
        key = {"X-API-Key": ADMIN_KEY}
        none_yet = await client.post(f"/api/videos/{vid}/render", headers=key, json={"music": {}})
        assert none_yet.status_code == 409 and "no music" in none_yet.text
        ff("-f", "lavfi", "-i", "sine=frequency=110:duration=1.5", str(root / "bed.mp3"))
        await client.put(f"/api/videos/{vid}/music/bed.mp3", headers=key, content=(root / "bed.mp3").read_bytes())

        started = await client.post(f"/api/videos/{vid}/render", headers=key,
                                    json={"subs": "none", "music": {"volume": 0.3}})
        assert started.status_code == 202, started.text
        assert started.json()["music"]["track"] == "bed.mp3"  # the newest track when none is named
        status = await wait_for(client, vid, key)
        assert status["status"] == "done", status
        assert status["done_steps"] == status["total_steps"]
        out = root / status["output_path"]
        kinds = {s["codec_type"] for s in json.loads(probe(out, "stream=codec_type"))["streams"]}
        assert kinds == {"video", "audio"}
        # The mute middle scene now carries the (looped) music bed.
        level = subprocess.run(["ffmpeg", "-hide_banner", "-ss", "3.2", "-t", "1", "-i", str(out), "-af", "volumedetect",
                                "-f", "null", "-"], capture_output=True, text=True).stderr
        mean = float(next(l for l in level.splitlines() if "mean_volume" in l).split(":")[1].split()[0])
        assert mean > -45, level


class TestBurnedSubtitleStyle:
    def test_khmer_captions_pick_a_khmer_font_in_an_english_project(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "SUBTITLE_FONT", "")
        monkeypatch.setattr(config, "SUBTITLE_FONTS_DIR", tmp_path / "none")
        assert render.captions_language("1\n00:00:00,000 --> 00:00:01,000\nភ្នំស្រី\n", "en") == "km"
        assert render.captions_language("1\n00:00:00,000 --> 00:00:01,000\nHello.\n", "en") == "en"
        monkeypatch.setattr(render.platform, "system", lambda: "Windows")
        assert render.subtitle_font("km") == "Khmer UI"
        monkeypatch.setattr(render.platform, "system", lambda: "Linux")
        assert render.subtitle_font("km") == "Noto Sans Khmer"

    def test_styled_ass_replaces_only_the_default_style(self):
        ass = ("[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
               "Style: Default,Arial,16,&Hffffff,&Hffffff,&H0,&H0,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n"
               "[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Style: Default,kept\n")
        out = render.styled_ass(ass, "Khmer UI", 18, 40)
        assert "Style: Default,Khmer UI,18," in out and out.count("Khmer UI") == 1
        assert ",10,10,40,0\n" in out
        assert "Default,,0,0,0,,Style: Default,kept" in out

    def test_bundled_khmer_font_is_preferred_when_its_file_is_there(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "SUBTITLE_FONT", "")
        monkeypatch.setattr(config, "SUBTITLE_FONTS_DIR", tmp_path)
        monkeypatch.setattr(render.platform, "system", lambda: "Windows")
        assert (render.subtitle_font("km"), render.subtitle_size("km", 18)) == ("Khmer UI", 18)
        (tmp_path / "KantumruyPro-Bold.ttf").write_bytes(b"")
        assert (render.subtitle_font("km"), render.subtitle_size("km", 18)) == ("Kantumruy Pro", 22)
        assert (render.subtitle_font("en"), render.subtitle_size("en", 18)) == ("Arial", 18)
        monkeypatch.setattr(config, "SUBTITLE_FONT", "Battambang")
        assert (render.subtitle_font("km"), render.subtitle_size("km", 18)) == ("Battambang", 18)

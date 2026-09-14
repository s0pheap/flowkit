"""Video review with the caller's own AI agent, and choosing the host CLI per request (agent/api/reviews.py)."""
import shutil

import pytest

from agent.db import crud
from agent.services import video_reviewer
from tests.unit.test_render import ADMIN_KEY, HAS_FFMPEG, OTHER, PROJECT, env, ff, make_user  # noqa: F401

ANALYSIS = {
    "dimensions": {"character_consistency": 8, "prompt_adherence": 7, "motion_quality": 9,
                   "visual_fidelity": 8, "temporal_coherence": 8, "composition": 7},
    "errors": [{"severity": "MINOR", "time_range": "2s-3s", "description": "prop count changes"}],
    "usable_segments": [{"time_range": "0s-8s", "score": 8}],
}


@pytest.fixture
async def scene_with_clip(env, monkeypatch):
    root, client = env
    clip = root / "clip.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2", "-c:v", "libx264", str(clip))
    await crud.create_project(name="Review Test", id=PROJECT, language="km")
    await crud.create_project(name="Other", id=OTHER)
    video = await crud.create_video(project_id=PROJECT, title="v", orientation="HORIZONTAL")
    scene = await crud.create_scene(video_id=video["id"], display_order=0, prompt="Bold Maiden raises the lantern")
    await crud.update_scene(scene["id"], horizontal_video_url="https://flow-content.google/video/x",
                            horizontal_video_status="COMPLETED")

    async def fake_download(url, dest):
        shutil.copyfile(clip, dest)
    monkeypatch.setattr(video_reviewer, "_download_video", fake_download)
    monkeypatch.setattr(video_reviewer, "REVIEW_JOBS_DIR", root / "review_jobs")
    return client, video, scene


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
async def test_own_agent_prepares_sheets_and_scores_the_posted_analysis(scene_with_clip):
    client, video, scene = scene_with_clip
    user = await make_user(client, "maly", PROJECT)
    base = f"/api/videos/{video['id']}"

    prepared = await client.post(f"{base}/scenes/{scene['id']}/review/prepare",
                                 params={"project_id": PROJECT}, headers=user)
    assert prepared.status_code == 200, prepared.text
    job = prepared.json()
    assert job["sheet_count"] >= 1 and len(job["sheets"]) == job["sheet_count"]
    assert "Bold Maiden raises the lantern" in job["prompt"] and '"dimensions"' in job["prompt"]

    sheet = await client.get(job["sheets"][0], headers=user)
    assert sheet.status_code == 200 and sheet.headers["content-type"] == "image/jpeg"
    assert sheet.content[:2] == b"\xff\xd8"

    # Another user's key cannot see this project's review.
    stranger = await make_user(client, "other", OTHER)
    assert (await client.get(job["sheets"][0], headers=stranger)).status_code in (403, 404)

    scored = await client.post(job["result_url"], json=ANALYSIS, headers=user)
    assert scored.status_code == 200, scored.text
    review = scored.json()
    assert review["scene_id"] == scene["id"]
    assert review["overall_score"] == video_reviewer._compute_overall(ANALYSIS["dimensions"])
    assert review["verdict"] == "good" and review["frames_analyzed"] == job["n_frames"]

    # The job is closed once scored.
    assert (await client.post(job["result_url"], json=ANALYSIS, headers=user)).status_code == 404


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
async def test_result_accepts_the_agents_text_reply_and_rejects_nonsense(scene_with_clip):
    client, video, scene = scene_with_clip
    key = {"X-API-Key": ADMIN_KEY}
    job = (await client.post(f"/api/videos/{video['id']}/scenes/{scene['id']}/review/prepare",
                             params={"project_id": PROJECT}, headers=key)).json()
    bad = await client.post(job["result_url"], json={"raw": "I could not see the images"}, headers=key)
    assert bad.status_code == 400
    text = "Here is the review:\n```json\n" + __import__("json").dumps(ANALYSIS) + "\n```"
    ok = await client.post(job["result_url"], json={"raw": text}, headers=key)
    assert ok.status_code == 200 and ok.json()["verdict"] == "good"


async def test_host_provider_must_be_known_and_installed(scene_with_clip, monkeypatch):
    client, video, scene = scene_with_clip
    key = {"X-API-Key": ADMIN_KEY}
    monkeypatch.setattr(video_reviewer, "host_providers", lambda: {"claude": False, "agy": True, "codex": False})
    url = f"/api/videos/{video['id']}/scenes/{scene['id']}/review"
    unknown = await client.post(url, params={"project_id": PROJECT, "provider": "gpt"}, headers=key)
    assert unknown.status_code == 400 and "Unknown provider" in unknown.text
    missing = await client.post(url, params={"project_id": PROJECT, "provider": "claude"}, headers=key)
    assert missing.status_code == 400 and "not installed" in missing.text and "agy" in missing.text

    seen = {}

    async def fake_review(scene_row, characters, **kw):
        seen.update(kw)
        return video_reviewer.scene_review_from_analysis(scene_row["id"], ANALYSIS, 8, 4.0)
    monkeypatch.setattr("agent.api.reviews.review_scene_video", fake_review)
    chosen = await client.post(url, params={"project_id": PROJECT, "provider": "agy"}, headers=key)
    assert chosen.status_code == 200, chosen.text
    assert seen["provider"] == "agy"


def test_old_review_jobs_are_purged(tmp_path, monkeypatch):
    monkeypatch.setattr(video_reviewer, "REVIEW_JOBS_DIR", tmp_path)
    old, fresh = tmp_path / ("a" * 32), tmp_path / ("b" * 32)
    old.mkdir()
    fresh.mkdir()
    import os
    import time
    stale = time.time() - video_reviewer.REVIEW_JOB_TTL_S - 10
    os.utime(old, (stale, stale))
    assert video_reviewer.purge_review_jobs() == 1
    assert not old.exists() and fresh.exists()
    assert video_reviewer.load_review_job("../etc") is None

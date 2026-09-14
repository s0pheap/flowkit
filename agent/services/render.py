"""Server-side final cut: the assembly plan turned into one MP4 with narration and subtitles.

This is what `/fk-concat-fit-narrator` used to do in the caller's shell, moved
onto the agent so a user on another computer gets the same result and downloads
it. Every length, offset and transition still comes from the assembly plan, so
the captions land where the narration plays.

Steps, per video:
  1. render any ffmpeg (motion) scene that has no clip yet
  2. per scene: trim, scale/pad to one size, 24 fps, mix narration over the clip's
     own audio, burn text overlays
  3. per transition group: the plan's xfade/acrossfade filter
  4. concat the groups
  5. optional background music under the whole cut, looped, faded, and ducked
     while the narrator speaks
  6. captions.srt on the same plan, embedded (soft) or burned in

One render runs at a time; they are CPU-heavy and share the machine with Chrome.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

from agent import config
from agent.models.look_feel import LookFeel
from agent.utils.paths import project_dir, scene_filename

logger = logging.getLogger(__name__)

SubsMode = Literal["soft", "burn", "none"]

FPS = 24
BASE_SIZE = {"HORIZONTAL": (1920, 1080), "VERTICAL": (1080, 1920)}
SFX_VOLUME = 0.3
NARRATION_VOLUME = 1.5
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")

# Overlay styles from /fk-gen-text-overlays: (size at 1080p, colour).
OVERLAY_STYLES = {
    "stat": (42, "white"),
    "cost": (42, "0xFFD700"),
    "date": (39, "0x00FFFF"),
    "name": (39, "white"),
}

# ISO 639-1 project language → ISO 639-2 for the subtitle track.
SUB_LANG = {"en": "eng", "ko": "kor", "vi": "vie", "ja": "jpn", "zh": "zho", "es": "spa",
            "fr": "fra", "de": "deu", "th": "tha", "ar": "ara", "hi": "hin", "pt": "por", "ru": "rus",
            "km": "khm"}

# Scripts that settle the captions' language whatever the project language says
# (a Khmer narration in an English project still needs a Khmer font).
_CAPTION_SCRIPTS = [(re.compile(r"[ក-៿᧠-᧿]"), "km")]

_gate = asyncio.Semaphore(1)
_jobs: dict[str, "RenderJob"] = {}
_tasks: set[asyncio.Task] = set()  # keep running renders referenced


class RenderError(RuntimeError):
    pass


@dataclass
class RenderJob:
    video_id: str
    slug: str
    status: Literal["queued", "running", "done", "failed"] = "queued"
    step: str = "waiting for another render to finish"
    done_steps: int = 0
    total_steps: int = 0
    subs: str = "soft"
    buffer: float = 0.5
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    captions_path: Optional[str] = None
    duration: Optional[float] = None
    size_bytes: Optional[int] = None
    music: Optional[dict] = None  # {"track", "volume", "duck", "fade_in", "fade_out"}
    warnings: list[str] = field(default_factory=list)

    def public(self) -> dict:
        data = asdict(self)
        data["download_url"] = f"/api/videos/{self.video_id}/final.mp4" if self.status == "done" else None
        data["captions_url"] = (f"/api/videos/{self.video_id}/captions.srt"
                                if self.status == "done" and self.captions_path else None)
        return data


# ─── Paths ───────────────────────────────────────────────────

def final_path(slug: str) -> Path:
    return project_dir(slug) / f"{slug}_narrator_cut.mp4"


def final_captions_path(slug: str) -> Path:
    return project_dir(slug) / f"{slug}_narrator_cut.srt"


def music_dir(slug: str) -> Path:
    """Background tracks for a project: uploads and /fk-gen-music downloads both land here."""
    return project_dir(slug) / "music"


def list_music(slug: str) -> list[Path]:
    """The project's tracks, newest first."""
    folder = music_dir(slug)
    if not folder.is_dir():
        return []
    tracks = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS]
    return sorted(tracks, key=lambda p: p.stat().st_mtime, reverse=True)


def music_file(slug: str, name: str) -> Optional[Path]:
    """The track called ``name`` in the project's music folder, or None. Never a path outside it."""
    if not name or name.startswith(".") or any(c in name for c in '/\\:'):
        return None
    folder = music_dir(slug).resolve()
    path = (folder / name).resolve()
    if path.parent != folder or path.suffix.lower() not in MUSIC_EXTS or not path.is_file():
        return None
    return path


def _status_file(slug: str) -> Path:
    return project_dir(slug) / "render_status.json"


def _abs(ref: str) -> str:
    """Plan paths are relative to the repo root; URLs pass through."""
    if re.match(r"^https?://", ref):
        return ref
    path = Path(ref)
    return str(path if path.is_absolute() else config.BASE_DIR / path)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(config.BASE_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)


# ─── Job registry ────────────────────────────────────────────

def get_job(video_id: str, slug: str) -> Optional[RenderJob]:
    """The live job, else the last one recorded on disk (a restart marks a running job failed)."""
    if video_id in _jobs:
        return _jobs[video_id]
    status = _status_file(slug)
    if not status.exists():
        return None
    try:
        data = json.loads(status.read_text(encoding="utf-8"))
        job = RenderJob(**{k: v for k, v in data.items() if k in RenderJob.__dataclass_fields__})
    except (OSError, ValueError, TypeError):
        return None
    if job.status in ("queued", "running"):
        job.status, job.error = "failed", "The agent restarted during this render. Start it again."
    if job.status == "done" and not final_path(slug).exists():
        return None
    return job


def is_active(video_id: str) -> bool:
    job = _jobs.get(video_id)
    return bool(job and job.status in ("queued", "running"))


def _save(job: RenderJob) -> None:
    try:
        path = _status_file(job.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write render status for %s: %s", job.video_id, e)


def _progress(job: RenderJob, step: str, advance: bool = True) -> None:
    if advance:
        job.done_steps += 1
    job.step = step
    _save(job)


# ─── Checks before starting ──────────────────────────────────

def _expired(url: str) -> bool:
    m = re.search(r"[?&](?:Expires|expires|exp)=(\d{9,})", url)
    return bool(m and int(m.group(1)) < time.time() + 300)


def problems(plan: dict) -> list[str]:
    """Reasons the plan can't be rendered as it stands. ffmpeg scenes without a clip are fine: the job renders them."""
    issues = []
    for seg in plan["segments"]:
        n = seg["display_order"] + 1
        if seg["mode"] == "ffmpeg":
            if seg["needs_render"] and not seg.get("image_url"):
                issues.append(f"Scene {n} has no keyframe image yet. Run /fk-gen-images.")
            continue
        source = seg.get("video_source")
        if not source:
            issues.append(f"Scene {n} has no video yet. Run /fk-gen-videos.")
        elif source.startswith("http") and _expired(source):
            issues.append(f"Scene {n}'s video link has expired. Run /fk-refresh-urls first.")
    return issues


# ─── ffmpeg helpers ──────────────────────────────────────────

async def _run(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 1800) -> str:
    loop = asyncio.get_running_loop()
    proc = await loop.run_in_executor(None, lambda: subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None, timeout=timeout))
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-8:]
        raise RenderError(f"{Path(cmd[0]).name} failed: " + " | ".join(tail)[-900:])
    return proc.stdout


async def _probe(source: str) -> dict:
    out = await _run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                      "-of", "json", source], timeout=120)
    streams = json.loads(out or "{}").get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {"width": video.get("width"), "height": video.get("height"),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


async def _duration(path: Path) -> Optional[float]:
    try:
        out = await _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
        return round(float(out.strip()), 2)
    except (RenderError, ValueError):
        return None


def output_size(orientation: str, probed: Optional[dict]) -> tuple[int, int]:
    """1080p for the orientation, or the source size when a clip is bigger (never downscale 4K)."""
    base_w, base_h = BASE_SIZE.get(orientation, BASE_SIZE["HORIZONTAL"])
    if probed and probed.get("width") and probed.get("height"):
        w, h = probed["width"], probed["height"]
        if (w >= h) == (base_w >= base_h) and w * h > base_w * base_h:
            return w - w % 2, h - h % 2
    return base_w, base_h


def _filter_path(path: Path) -> str:
    """A path inside a filtergraph option: forward slashes, drive colon escaped."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def overlay_font() -> Optional[Path]:
    if config.OVERLAY_FONT:
        return Path(config.OVERLAY_FONT)
    candidates = {
        "Windows": ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/arialbd.ttf"],
        "Darwin": ["/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    }.get(platform.system(), [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ])
    return next((Path(c) for c in candidates if Path(c).exists()), None)


# Fonts that look better than the OS default, used when their files are in SUBTITLE_FONTS_DIR:
# language -> (family, file prefix, size scale so the letters match the default font's height).
BUNDLED_SUBTITLE_FONTS = {"km": ("Kantumruy Pro", "KantumruyPro", 1.2)}


def _bundled_font(language: str) -> Optional[tuple[str, float]]:
    entry = BUNDLED_SUBTITLE_FONTS.get(language)
    if not entry or not config.SUBTITLE_FONTS_DIR.is_dir():
        return None
    family, prefix, scale = entry
    return (family, scale) if any(config.SUBTITLE_FONTS_DIR.glob(f"{prefix}*.[ot]tf")) else None


def _fonts_dir_arg(cwd: Path) -> str:
    """SUBTITLE_FONTS_DIR for a filter run in ``cwd``: relative when it can be, since a drive colon breaks filter parsing."""
    try:
        return Path(os.path.relpath(config.SUBTITLE_FONTS_DIR.resolve(), cwd.resolve())).as_posix()
    except ValueError:  # another drive: quote the escaped absolute path
        return f"'{_filter_path(config.SUBTITLE_FONTS_DIR.resolve())}'"


def subtitle_size(language: str, size: int) -> int:
    bundled = None if config.SUBTITLE_FONT else _bundled_font(language)
    return round(size * bundled[1]) if bundled else size


def subtitle_font(language: str) -> str:
    if config.SUBTITLE_FONT:
        return config.SUBTITLE_FONT
    bundled = _bundled_font(language)
    if bundled:
        return bundled[0]
    system = platform.system()
    if language in ("ko", "ja", "zh"):
        return {"Windows": "Malgun Gothic", "Darwin": "Apple SD Gothic Neo"}.get(system, "Noto Sans CJK KR")
    if language == "km":
        return {"Windows": "Khmer UI", "Darwin": "Khmer Sangam MN"}.get(system, "Noto Sans Khmer")
    return {"Windows": "Arial", "Darwin": "Arial"}.get(system, "DejaVu Sans")


def captions_language(text: str, language: str) -> str:
    """The captions' language: their script when it gives it away, else the project language."""
    for pattern, lang in _CAPTION_SCRIPTS:
        if pattern.search(text):
            return lang
    return language


def styled_ass(ass: str, font: str, size: int, margin: int) -> str:
    """Restyle the Default style of an ffmpeg-converted .ass: bold white text, 2px outline, no shadow."""
    style = f"Style: Default,{font},{size},&Hffffff,&Hffffff,&H0,&H0,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin},0"
    return re.sub(r"^Style: Default,.*$", lambda _: style, ass, count=1, flags=re.MULTILINE)


def overlay_filters(items: list[dict], work_dir: Path, stem: str, duration: float, width: int) -> list[str]:
    """drawtext filters for one scene. Text goes through files, so no quoting of user text is needed."""
    font = overlay_font()
    if not items or not font:
        return []
    scale = 2 if width >= 2160 else 1  # 4K sizes are double the 1080p ones
    end = max(duration - 0.5, 0.6)
    filters = []
    for i, item in enumerate(items[:2]):
        size, colour = OVERLAY_STYLES.get(item.get("style"), OVERLAY_STYLES["name"])
        text_file = work_dir / f"{stem}_overlay{i}.txt"
        text_file.write_text(str(item.get("text", ""))[:80], encoding="utf-8")
        margin = 40 * scale
        x = [f"{margin}", "(w-text_w)/2", f"w-text_w-{margin}"][int(item.get("_align", 1))]
        y = f"h*0.25+{i * 60 * scale}"
        filters.append(
            f"drawtext=fontfile='{_filter_path(font)}':textfile='{_filter_path(text_file)}'"
            f":fontsize={size * scale}:fontcolor={colour}:borderw={2 * scale}:bordercolor=black"
            f":x={x}:y={y}:enable='between(t,0.5,{end:.2f})'"
        )
    return filters


def segment_command(seg: dict, source: str, has_audio: bool, out: Path, width: int, height: int,
                    narration: Optional[str], overlays: list[str]) -> list[str]:
    """One ffmpeg pass per scene: trim, normalise size/fps/format, mix narration, burn overlays."""
    duration = seg["duration"]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if seg.get("trim_start"):
        cmd += ["-ss", str(seg["trim_start"])]
    cmd += ["-i", source]
    inputs = 1
    narration_idx = None
    if narration:
        cmd += ["-i", narration]
        narration_idx, inputs = inputs, inputs + 1
    bg = "0:a"
    if not has_audio:
        cmd += ["-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=48000:cl=stereo"]
        bg = f"{inputs}:a"

    video = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p")
    if overlays:
        video += "," + ",".join(overlays)
    video += "[vout]"
    if narration_idx is not None:
        audio = (f"[{bg}]volume={SFX_VOLUME}[bg];[{narration_idx}:a]volume={NARRATION_VOLUME}[fg];"
                 f"[bg][fg]amix=inputs=2:duration=first[aout]")
    else:
        audio = f"[{bg}]anull[aout]"

    return cmd + [
        "-filter_complex", f"{video};{audio}",
        "-map", "[vout]", "-map", "[aout]", "-t", f"{duration}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(out),
    ]


def music_command(video: Path, track: Path, out: Path, duration: float, volume: float = 0.15,
                  duck: bool = True, fade_in: float = 1.0, fade_out: float = 3.0) -> list[str]:
    """Lay ``track`` under the finished cut: looped to length, faded, and ducked while anyone speaks.

    The video stream is copied; only the audio is mixed again.
    """
    fade_in, fade_out = min(fade_in, duration / 2), min(fade_out, duration / 2)
    bed = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration:.3f},"
           f"asetpts=PTS-STARTPTS,volume={volume:.3f}")
    if fade_in > 0:
        bed += f",afade=t=in:st=0:d={fade_in:.2f}"
    if fade_out > 0:
        bed += f",afade=t=out:st={max(duration - fade_out, 0):.3f}:d={fade_out:.2f}"
    if duck:
        graph = (f"[0:a]asplit=2[main][key];{bed}[bed];"
                 "[bed][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=500[ducked];"
                 "[main][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        graph = f"{bed}[bed];[0:a][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-stream_loop", "-1", "-i", str(track),
        "-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-t", f"{duration:.3f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(out),
    ]


def load_overlays(slug: str) -> dict[int, list[dict]]:
    path = project_dir(slug) / "text_overlays.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items() if isinstance(v, list)}
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable %s", path)
        return {}


# ─── The job ─────────────────────────────────────────────────

async def _render(job: RenderJob, plan: dict, language: str) -> None:
    from agent.api.look_feel import write_captions  # the plan and captions live with the look & feel routes
    from agent.services.motion import render_motion

    slug, orientation = plan["slug"], plan["orientation"]
    segments = plan["segments"]
    out_dir = project_dir(slug)
    work = out_dir / "trimmed"
    work.mkdir(parents=True, exist_ok=True)
    overlays = load_overlays(slug)

    to_render = [s for s in segments if s["mode"] == "ffmpeg" and s["needs_render"]]
    multi_groups = [g for g in plan["groups"] if len(g["segments"]) > 1]
    job.total_steps = (len(to_render) + len(segments) + len(multi_groups) + 1
                       + (1 if job.music else 0) + (0 if job.subs == "none" else 1))
    job.status, job.started_at = "running", time.time()
    _progress(job, "starting", advance=False)

    # 1. Motion clips that don't exist yet.
    for seg in to_render:
        _progress(job, f"rendering motion for scene {seg['display_order'] + 1}", advance=False)
        look = LookFeel.model_validate(seg["look_feel"])
        await render_motion(seg["image_url"], Path(_abs(seg["motion_path"])), look, seg["duration"], orientation)
        seg["video_source"] = seg["motion_path"]
        job.done_steps += 1

    # 2. Size from the first Veo clip (never downscale a 4K source).
    first_veo = next((s for s in segments if s["mode"] == "generate"), None)
    probed = await _probe(_abs(first_veo["video_source"])) if first_veo else None
    width, height = output_size(orientation, probed)

    trimmed: list[Path] = []
    for seg in segments:
        n = seg["display_order"]
        _progress(job, f"cutting scene {n + 1} of {len(segments)}", advance=False)
        source = _abs(seg["video_source"])
        info = probed if seg is first_veo else await _probe(source)
        out = work / scene_filename(n, seg["scene_id"])
        items = [dict(item, _align=n % 3) for item in overlays.get(n, [])]
        filters = overlay_filters(items, work, out.stem, seg["duration"], width)
        narration = _abs(seg["narration_path"]) if seg.get("narration_path") else None
        await _run(segment_command(seg, source, info["has_audio"], out, width, height, narration, filters))
        trimmed.append(out)
        job.done_steps += 1
    if overlays and not overlay_font():
        job.warnings.append("Text overlays skipped: no font found. Set OVERLAY_FONT in .env.")

    # 3. Transitions.
    pieces: list[Path] = []
    for gi, group in enumerate(plan["groups"]):
        idxs = group["segments"]
        if len(idxs) == 1:
            pieces.append(trimmed[idxs[0]])
            continue
        _progress(job, f"joining transition group {gi + 1}", advance=False)
        out = work / f"group_{gi:03d}.mp4"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for i in idxs:
            cmd += ["-i", str(trimmed[i])]
        cmd += ["-filter_complex", group["filter_complex"], "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(out)]
        await _run(cmd)
        pieces.append(out)
        job.done_steps += 1

    # 4. Concat.
    _progress(job, "joining all scenes", advance=False)
    final = final_path(slug)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in pieces), encoding="utf-8")
    staged = work / "final.tmp.mp4"
    await _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", listing.name, "-c", "copy", "-movflags", "+faststart", staged.name], cwd=work)
    job.done_steps += 1

    # 5. Background music.
    if job.music:
        _progress(job, "adding background music", advance=False)
        track = music_file(slug, job.music["track"])
        if not track:
            raise RenderError(f"The music track {job.music['track']!r} is no longer in the project. Pick another one.")
        length = await _duration(staged) or plan["total_duration"]
        opts = {k: job.music[k] for k in ("volume", "duck", "fade_in", "fade_out") if k in job.music}
        mixed = work / "final.music.mp4"
        await _run(music_command(staged, track, mixed, length, **opts))
        staged.unlink()
        mixed.rename(staged)
        job.done_steps += 1

    # 6. Subtitles on the same plan.
    if job.subs != "none":
        _progress(job, "adding subtitles", advance=False)
        result = await write_captions(job.video_id, orientation, job.buffer)
        captions = config.BASE_DIR / result["captions_path"]
        if result["cue_count"] and captions.exists():
            shutil.copyfile(captions, final_captions_path(slug))
            job.captions_path = _rel(final_captions_path(slug))
            if result.get("estimated_timing_scenes"):
                job.warnings.append(f"{len(result['estimated_timing_scenes'])} scene(s) have estimated caption timing.")
            subbed = work / "final.subs.mp4"
            sub_language = captions_language(captions.read_text(encoding="utf-8"), language)
            if job.subs == "soft":
                await _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(staged),
                            "-i", str(captions), "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
                            "-metadata:s:s:0", f"language={SUB_LANG.get(sub_language, 'und')}",
                            "-movflags", "+faststart", str(subbed)])
            else:
                size, margin = (12, 120) if orientation == "VERTICAL" else (18, 40)
                # Through .ass so libass can shape with HarfBuzz: without it Khmer (and other scripts whose
                # vowels and subscripts stack) come out as detached marks. Paths are relative to the
                # project folder, so there is no drive colon to escape.
                ass = captions.with_suffix(".ass")
                await _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", "subtitles/captions.srt", "subtitles/captions.ass"], cwd=out_dir)
                ass.write_text(styled_ass(ass.read_text(encoding="utf-8"), subtitle_font(sub_language),
                                          subtitle_size(sub_language, size), margin), encoding="utf-8")
                fonts = f":fontsdir={_fonts_dir_arg(out_dir)}" if config.SUBTITLE_FONTS_DIR.is_dir() else ""
                await _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(staged),
                            "-vf", f"ass=subtitles/captions.ass{fonts}:shaping=complex",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "copy", "-movflags", "+faststart", str(subbed)], cwd=out_dir)
            staged.unlink()
            subbed.rename(staged)
        else:
            job.warnings.append("No narration captions to add.")
        job.done_steps += 1

    staged.replace(final)
    job.output_path = _rel(final)
    job.duration = await _duration(final)
    job.size_bytes = final.stat().st_size


def start(video_id: str, plan: dict, language: str, subs: SubsMode, buffer: float,
          music: Optional[dict] = None) -> RenderJob:
    job = RenderJob(video_id=video_id, slug=plan["slug"], subs=subs, buffer=buffer, music=music)
    _jobs[video_id] = job
    _save(job)

    async def run():
        async with _gate:
            try:
                await _render(job, plan, language)
                job.status, job.step = "done", "finished"
                logger.info("Rendered %s -> %s (%.1fs)", video_id, job.output_path, job.duration or 0)
            except Exception as e:  # the job reports it; nothing awaits this task
                job.status, job.step = "failed", "failed"
                job.error = str(e)
                if "403" in job.error or "Forbidden" in job.error:
                    job.error += " — a video link may have expired; run /fk-refresh-urls and render again."
                logger.exception("Render failed for %s", video_id)
            finally:
                job.finished_at = time.time()
                _save(job)

    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job

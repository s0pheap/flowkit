"""Look & feel, motion renders, the assembly plan, and subtitles.

These all hang off the same timeline (``agent/services/assembly.py``): a scene's
length comes from its look & feel or its narration, and captions are placed on
the timeline the concat step will actually produce.
"""
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.request import url2pathname

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import auth
from agent.config import BASE_DIR
from agent.db import crud
from agent.models.enums import Orientation
from agent.models.look_feel import MOTIONS, STRENGTHS, TRANSITIONS, LookFeel, parse_look_feel
from agent.models.project import video_clip_seconds, video_model_family
from agent.services import assembly, subtitles
from agent.services.gemini_tts import wav_duration
from agent.services.motion import render_motion
from agent.services.tts import load_word_timings, timings_path_for, write_word_timings
from agent.utils.paths import project_dir, resolve_4k_file, scene_filename, scene_tts_path
from agent.utils.slugify import slugify

logger = logging.getLogger(__name__)

router = APIRouter(tags=["look-feel"])

_RENDER_GATE = asyncio.Semaphore(2)
_probe_cache: dict[tuple[str, float], Optional[float]] = {}
#: Lengths of clips that live at a signed URL, keyed by the URL without its query
#: (the media's path), so re-signing doesn't measure the same clip again.
_remote_clip_seconds: dict[str, float] = {}
_REMOTE_PROBES_AT_ONCE = 6


class MotionRenderRequest(BaseModel):
    orientation: Optional[Orientation] = None
    preview: bool = False
    duration: Optional[float] = Field(None, gt=0.5, le=60)


class SubtitlesRequest(BaseModel):
    orientation: Optional[Orientation] = None
    buffer: float = Field(assembly.NARRATION_BUFFER, ge=0, le=3)
    max_chars: Optional[int] = Field(None, ge=10, le=80)


# ─── Helpers ─────────────────────────────────────────────────

def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)


def _local_file(ref: Optional[str]) -> Optional[Path]:
    """A local path for a file path or file:// URL; None for remote URLs."""
    if not ref:
        return None
    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https"):
        return None
    path = Path(url2pathname(parsed.path)) if parsed.scheme == "file" else Path(ref)
    return path if path.exists() else None


def _probe_duration(path: Path) -> Optional[float]:
    key = (str(path), path.stat().st_mtime)
    if key not in _probe_cache:
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            _probe_cache[key] = float(out.stdout.strip())
        except (ValueError, OSError, subprocess.SubprocessError):
            _probe_cache[key] = None
    return _probe_cache[key]


def _probe_remote_duration(url: str) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", url],
            capture_output=True, text=True, timeout=20,
        )
        return float(out.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


async def _remote_clip_durations(urls: list[str]) -> dict[str, float]:
    """Length of each remote clip, by URL. Measures only clips not seen before, a few at
    a time, off the event loop. A failed probe (an expired URL) is not remembered."""
    wanted = {url: url.split("?", 1)[0] for url in urls}
    missing = {key: url for url, key in wanted.items() if key not in _remote_clip_seconds}
    if missing:
        gate = asyncio.Semaphore(_REMOTE_PROBES_AT_ONCE)
        loop = asyncio.get_running_loop()

        async def measure(key: str, url: str):
            async with gate:
                seconds = await loop.run_in_executor(None, _probe_remote_duration, url)
            if seconds:
                _remote_clip_seconds[key] = seconds

        await asyncio.gather(*(measure(key, url) for key, url in missing.items()))
    return {url: _remote_clip_seconds[key] for url, key in wanted.items() if key in _remote_clip_seconds}


def _motion_path(slug: str, scene: dict, preview: bool = False) -> Path:
    name = scene_filename(scene["display_order"], scene["id"])
    return project_dir(slug) / "motion" / (f"preview_{name}" if preview else name)


def _veo_source(slug: str, scene: dict, prefix: str) -> tuple[Optional[str], Optional[Path]]:
    """Best Veo clip for a scene: local 4K, then upscale, then the base render."""
    local_4k = resolve_4k_file(slug, scene["display_order"], scene["id"])
    if local_4k:
        return _rel(local_4k), local_4k
    for field in (f"{prefix}_upscale_url", f"{prefix}_video_url"):
        ref = scene.get(field)
        if ref:
            local = _local_file(ref)
            return (_rel(local) if local else ref), local
    return None, None


def _default_look(scene: dict, next_scene: Optional[dict]) -> LookFeel:
    """Look for a scene nobody has set: a Veo shot that cuts, except that a chain
    continuing straight into its child crossfades, as the concat step always did."""
    if (next_scene and next_scene.get("chain_type") == "CONTINUATION"
            and next_scene.get("parent_scene_id") == scene["id"]):
        return LookFeel(transition="fade", transition_duration=0.5)
    return LookFeel()


async def _video_context(vid: str, orientation: Optional[str]) -> tuple[dict, dict, str, str, list[dict]]:
    video = await crud.get_video(vid)
    if not video:
        raise HTTPException(404, "Video not found")
    project = await crud.get_project(video["project_id"])
    if not project:
        raise HTTPException(404, "Project not found")
    scenes = sorted(await crud.list_scenes(vid), key=lambda s: s.get("display_order", 0))
    if not scenes:
        raise HTTPException(404, "No scenes found for video")
    ori = orientation or video.get("orientation") or "VERTICAL"
    return video, project, slugify(project.get("name") or "unnamed_project"), ori, scenes


async def _build_plan(vid: str, orientation: Optional[str], buffer: float) -> dict:
    video, project, slug, ori, scenes = await _video_context(vid, orientation)
    prefix = ori.lower()

    looks = [parse_look_feel(scene.get("look_feel")) or _default_look(scene, scenes[idx + 1] if idx + 1 < len(scenes) else None)
             for idx, scene in enumerate(scenes)]
    sources = [_veo_source(slug, scene, prefix) for scene in scenes]
    # Clips at a signed URL are measured too: the render reads them from there, and
    # a project can hold 8 s Veo and 10 s Omni clips side by side.
    remote = await _remote_clip_durations([
        ref for look, (ref, local) in zip(looks, sources)
        if look.mode == "generate" and ref and not local and ref.startswith(("http://", "https://"))
    ])
    # Only a clip that can't be measured (none yet, or an expired URL) is assumed
    # to be as long as the project's model makes them.
    expected_clip = float(video_clip_seconds(video_model_family(project)))
    items, extras = [], {}
    for scene, look, (veo_ref, veo_local) in zip(scenes, looks, sources):
        wav = scene_tts_path(slug, scene["display_order"], scene["id"])
        narration = wav_duration(wav) if wav.exists() else None
        motion = _motion_path(slug, scene)
        if look.mode != "generate":
            clip = None
        elif veo_local:
            clip = _probe_duration(veo_local)
        else:
            clip = remote.get(veo_ref) or expected_clip
        items.append(assembly.SceneTiming(
            scene_id=scene["id"],
            display_order=scene["display_order"],
            look=look,
            narration_duration=narration,
            clip_duration=clip,
        ))
        timings = timings_path_for(str(wav))
        extras[scene["id"]] = {
            "look_feel": look.model_dump(),
            "has_custom_look_feel": scene.get("look_feel") is not None,
            "image_url": scene.get(f"{prefix}_image_url"),
            "video_source": _rel(motion) if look.mode == "ffmpeg" else veo_ref,
            "video_source_local": motion.exists() if look.mode == "ffmpeg" else veo_local is not None,
            "veo_video_source": veo_ref,
            "motion_path": _rel(motion),
            "motion_rendered": motion.exists(),
            "needs_render": look.mode == "ffmpeg" and not motion.exists(),
            "narration_path": _rel(wav) if wav.exists() else None,
            "timings_path": _rel(timings) if timings.exists() else None,
            "narrator_text": scene.get("narrator_text"),
        }

    segments = assembly.plan_timeline(items, buffer)
    for seg in segments:
        seg.update(extras[seg["scene_id"]])
    groups = [
        {"segments": idxs, "filter_complex": assembly.xfade_filter([segments[i] for i in idxs])}
        for idxs in assembly.group_segments(segments)
    ]
    return {
        "video_id": vid,
        "project_id": project["id"],
        "slug": slug,
        "output_dir": _rel(project_dir(slug)),
        "orientation": ori,
        "buffer": buffer,
        "total_duration": assembly.total_duration(segments),
        "veo_scenes": sum(1 for s in segments if s["mode"] == "generate"),
        "ffmpeg_scenes": sum(1 for s in segments if s["mode"] == "ffmpeg"),
        "segments": segments,
        "groups": groups,
    }


# ─── Routes ──────────────────────────────────────────────────

@router.get("/look-feel/options")
async def look_feel_options():
    return {
        "modes": ["generate", "ffmpeg"],
        "motions": list(MOTIONS),
        "strengths": list(STRENGTHS),
        "transitions": list(TRANSITIONS),
        "defaults": LookFeel().model_dump(),
    }


@router.get("/videos/{vid}/assembly-plan")
async def assembly_plan(vid: str, orientation: Optional[Orientation] = None,
                        buffer: float = assembly.NARRATION_BUFFER):
    """Per-scene length, start, source clip and transition for the final cut."""
    await auth.require_video(vid)
    return await _build_plan(vid, orientation, buffer)


@router.post("/scenes/{sid}/motion")
async def render_scene_motion(sid: str, body: MotionRenderRequest):
    """Render the scene's keyframe with its look & feel pan/zoom (ffmpeg, no Flow call)."""
    scene = await auth.require_scene(sid)
    plan = await _build_plan(scene["video_id"], body.orientation, assembly.NARRATION_BUFFER)
    seg = next(s for s in plan["segments"] if s["scene_id"] == sid)
    if not seg["image_url"]:
        raise HTTPException(409, f"Scene has no {plan['orientation'].lower()} keyframe yet — run /fk-gen-images first")

    look = LookFeel.model_validate(seg["look_feel"])
    duration = body.duration or seg["duration"]
    out = _motion_path(plan["slug"], scene, preview=body.preview)
    async with _RENDER_GATE:
        try:
            await render_motion(seg["image_url"], out, look, duration, plan["orientation"], preview=body.preview)
        except RuntimeError as e:
            raise HTTPException(502, str(e))
    return {
        "scene_id": sid,
        "path": _rel(out),
        "duration": duration,
        "preview": body.preview,
        "url": f"/api/scenes/{sid}/motion.mp4?preview={'true' if body.preview else 'false'}",
    }


@router.get("/scenes/{sid}/motion.mp4")
async def scene_motion_file(sid: str, preview: bool = False):
    scene = await auth.require_scene(sid)
    video = await crud.get_video(scene["video_id"])
    project = await crud.get_project(video["project_id"]) if video else None
    if not project:
        raise HTTPException(404, "Project not found")
    path = _motion_path(slugify(project.get("name") or "unnamed_project"), scene, preview=preview)
    if not path.exists():
        raise HTTPException(404, "Motion clip not rendered yet")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})


@router.post("/videos/{vid}/subtitles")
async def build_subtitles(vid: str, body: SubtitlesRequest):
    """Write per-scene SRTs and a whole-video captions.srt placed on the assembly timeline."""
    await auth.require_video(vid)
    return await write_captions(vid, body.orientation, body.buffer, body.max_chars)


async def write_captions(vid: str, orientation: Optional[str], buffer: float, max_chars_override: Optional[int] = None) -> dict:
    """Build captions.srt (and per-scene SRTs) on the plan for this buffer. Shared with the server render."""
    plan = await _build_plan(vid, orientation, buffer)
    out_dir = project_dir(plan["slug"]) / "subtitles"
    out_dir.mkdir(parents=True, exist_ok=True)

    loaded = {}
    for seg in plan["segments"]:
        if not (seg["narration_path"] and seg["narrator_text"]):
            continue
        wav = str(BASE_DIR / seg["narration_path"])
        timing = load_word_timings(wav)
        if not timing or timing.get("text") != seg["narrator_text"]:
            timing = await write_word_timings(wav, seg["narrator_text"])
        loaded[seg["scene_id"]] = timing

    all_text = " ".join(t.get("text", "") or "" for t in loaded.values())
    max_chars = max_chars_override or subtitles.default_max_chars(all_text)

    video_cues, scene_files, estimated = [], [], []
    for seg in plan["segments"]:
        timing = loaded.get(seg["scene_id"])
        if not timing:
            continue
        if timing.get("timing_source") == "estimated":
            estimated.append(seg["scene_id"])
        words = timing.get("words") or []
        scene_srt = out_dir / Path(seg["narration_path"]).with_suffix(".srt").name
        scene_srt.write_text(subtitles.to_srt(subtitles.build_cues(words, max_chars)), encoding="utf-8")
        scene_files.append(_rel(scene_srt))
        shifted = subtitles.shift_words(words, seg["start"], window=seg["duration"])
        video_cues.extend(subtitles.build_cues(shifted, max_chars))

    video_cues = subtitles.tidy_cues(video_cues)
    captions = out_dir / "captions.srt"
    captions.write_text(subtitles.to_srt(video_cues), encoding="utf-8")
    return {
        "video_id": vid,
        "captions_path": _rel(captions),
        "scene_files": scene_files,
        "cue_count": len(video_cues),
        "max_chars": max_chars,
        "scenes_with_captions": len(loaded),
        "estimated_timing_scenes": estimated,
        "total_duration": plan["total_duration"],
    }

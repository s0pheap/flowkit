"""Ken Burns motion from a scene keyframe — the free alternative to a Veo render.

The filter builders are pure so they can be tested without ffmpeg; only
``render_motion`` touches the network (to fetch a signed keyframe URL) and
spawns ffmpeg.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx

from agent.models.look_feel import LookFeel

logger = logging.getLogger(__name__)

FPS = 24

#: How far the frame zooms over the whole shot (1.0 + this at the far end).
ZOOM_AMOUNT = {"subtle": 0.08, "medium": 0.16, "strong": 0.28}

OUTPUT_SIZE = {"HORIZONTAL": (1920, 1080), "VERTICAL": (1080, 1920)}
PREVIEW_SIZE = {"HORIZONTAL": (960, 540), "VERTICAL": (540, 960)}


def zoompan_expressions(motion: str, strength: str, frames: int) -> tuple[str, str, str]:
    """(zoom, x, y) expressions for ffmpeg's zoompan filter."""
    amount = ZOOM_AMOUNT[strength]
    n = max(frames - 1, 1)
    progress = f"on/{n}"
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    held = f"{1 + amount:.4f}"

    if motion == "zoom_in":
        return f"1+{amount:.4f}*{progress}", center_x, center_y
    if motion == "zoom_out":
        return f"{held}-{amount:.4f}*{progress}", center_x, center_y
    # Pans hold a fixed zoom so there is spare picture to travel across.
    if motion == "pan_right":
        return held, f"(iw-iw/zoom)*{progress}", center_y
    if motion == "pan_left":
        return held, f"(iw-iw/zoom)*(1-{progress})", center_y
    if motion == "pan_down":
        return held, center_x, f"(ih-ih/zoom)*{progress}"
    if motion == "pan_up":
        return held, center_x, f"(ih-ih/zoom)*(1-{progress})"
    return "1", "0", "0"


def build_motion_filter(look: LookFeel, duration: float, width: int, height: int,
                        fps: int = FPS, oversample: int = 3) -> str:
    """Video filter that turns one still into a ``duration``-second moving shot.

    zoompan snaps its crop to whole pixels, which judders on slow moves, so the
    still is first blown up by ``oversample`` and the move happens on that.
    """
    frames = max(1, round(duration * fps))
    zoom, x, y = zoompan_expressions(look.motion, look.strength, frames)
    big_w, big_h = width * oversample, height * oversample
    return (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
        f"crop={big_w}:{big_h},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )


def build_motion_command(image_path: str, output_path: str, look: LookFeel, duration: float,
                         orientation: str, preview: bool = False) -> list[str]:
    """ffmpeg argv for one motion clip, with a silent stereo track so it concats with Veo clips."""
    width, height = (PREVIEW_SIZE if preview else OUTPUT_SIZE)[orientation]
    vf = build_motion_filter(look, duration, width, height, oversample=2 if preview else 3)
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", image_path,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast" if preview else "medium",
        "-crf", "28" if preview else "18",
        "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]


async def _local_image(source: str, workdir: Path) -> Path:
    """A local path for a keyframe given as a file path, file:// URL, or signed http URL."""
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        dest = workdir / "keyframe"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(source)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return dest
    if parsed.scheme == "file":
        return Path(url2pathname(parsed.path))
    return Path(source)


async def render_motion(image_source: str, output_path: Path, look: LookFeel, duration: float,
                        orientation: str, preview: bool = False) -> Path:
    """Render the keyframe into a moving clip at ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            image = await _local_image(image_source, Path(tmp))
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Could not download the keyframe ({e}). Signed URLs expire — run /fk-refresh-urls."
            ) from e
        if not image.exists():
            raise RuntimeError(f"Keyframe not found: {image}")
        cmd = build_motion_command(str(image), str(output_path), look, duration, orientation, preview)
        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg motion render failed: {proc.stderr[-400:]}")
    logger.info("Rendered %s motion (%.2fs, preview=%s) -> %s", look.motion, duration, preview, output_path)
    return output_path

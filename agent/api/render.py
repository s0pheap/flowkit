"""Final video on the server, its downloads, and the files the review board and overlays keep.

Everything here works for a remote user: nothing needs the caller's disk.
"""
import json
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse
from urllib.request import url2pathname

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from agent import auth
from agent.api import look_feel
from agent.db import crud
from agent.models.enums import Orientation
from agent.services import assembly, render
from agent.utils.paths import project_dir, resolve_4k_file
from agent.utils.slugify import slugify

router = APIRouter(tags=["render"])

REVIEW_BOARD_HTML = Path(__file__).resolve().parent.parent.parent / "tools" / "review_board.html"
OVERLAY_STYLES = set(render.OVERLAY_STYLES)
MAX_FEEDBACK_BYTES = 1_000_000


class RenderRequest(BaseModel):
    orientation: Optional[Orientation] = None
    buffer: float = Field(assembly.NARRATION_BUFFER, ge=0, le=3)
    subs: Literal["soft", "burn", "none"] = "soft"


async def _slug(vid: str) -> tuple[dict, dict, str]:
    video = await auth.require_video(vid)
    project = await crud.get_project(video["project_id"])
    if not project:
        raise HTTPException(404, "Project not found")
    return video, project, slugify(project.get("name") or "unnamed_project")


# ─── Render ──────────────────────────────────────────────────

@router.post("/videos/{vid}/render", status_code=202)
async def start_render(vid: str, body: RenderRequest):
    """Build the final MP4 on the server. Poll GET /render, then download final.mp4."""
    _video, project, _slug_ = await _slug(vid)
    if render.is_active(vid):
        raise HTTPException(409, "A render for this video is already running. Poll GET /api/videos/{vid}/render.")
    plan = await look_feel._build_plan(vid, body.orientation, body.buffer)
    issues = render.problems(plan)
    if issues:
        raise HTTPException(409, {"message": "The video isn't ready to render.", "problems": issues})
    job = render.start(vid, plan, project.get("language") or "en", body.subs, body.buffer)
    return job.public()


@router.get("/videos/{vid}/render")
async def render_status(vid: str):
    _video, _project, slug = await _slug(vid)
    job = render.get_job(vid, slug)
    return job.public() if job else {"video_id": vid, "status": "none"}


@router.get("/videos/{vid}/final.mp4")
async def final_video(vid: str, download: bool = False):
    _video, _project, slug = await _slug(vid)
    path = render.final_path(slug)
    if not path.exists():
        raise HTTPException(404, "No final video yet. Start one with POST /api/videos/{vid}/render.")
    return FileResponse(path, media_type="video/mp4", filename=path.name if download else None,
                        headers={"Cache-Control": "no-cache"})


@router.get("/videos/{vid}/captions.srt")
async def final_captions(vid: str, download: bool = False):
    _video, _project, slug = await _slug(vid)
    path = render.final_captions_path(slug)
    if not path.exists():
        path = project_dir(slug) / "subtitles" / "captions.srt"
    if not path.exists():
        raise HTTPException(404, "No captions yet. Narrate the video, then build subtitles or render.")
    return FileResponse(path, media_type="application/x-subrip; charset=utf-8",
                        filename=f"{slug}.srt" if download else None, headers={"Cache-Control": "no-cache"})


# ─── Text overlays (/fk-gen-text-overlays) ───────────────────

@router.get("/videos/{vid}/text-overlays")
async def get_text_overlays(vid: str):
    _video, _project, slug = await _slug(vid)
    path = project_dir(slug) / "text_overlays.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@router.put("/videos/{vid}/text-overlays")
async def put_text_overlays(vid: str, body: dict = Body(...)):
    """`{"<display_order>": [{"text": "...", "style": "date|name|stat|cost"}, ...]}`, at most 2 per scene."""
    _video, _project, slug = await _slug(vid)
    clean = {}
    for key, items in body.items():
        if not str(key).isdigit() or not isinstance(items, list):
            raise HTTPException(400, f"Keys must be scene display_order numbers with a list of items (bad key {key!r})")
        if len(items) > 2:
            raise HTTPException(400, f"Scene {key}: at most 2 overlays")
        for item in items:
            if not isinstance(item, dict) or item.get("style") not in OVERLAY_STYLES:
                raise HTTPException(400, f"Scene {key}: style must be one of {sorted(OVERLAY_STYLES)}")
            if not isinstance(item.get("text"), str) or not 0 < len(item["text"]) <= 40:
                raise HTTPException(400, f"Scene {key}: text must be 1-40 characters")
        clean[str(int(key))] = [{"text": i["text"], "style": i["style"]} for i in items]
    path = project_dir(slug) / "text_overlays.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scenes": len(clean), "items": sum(len(v) for v in clean.values())}


# ─── Review board ────────────────────────────────────────────

def review_board_page():
    """The board itself holds no data; every call it makes needs a key."""
    return FileResponse(REVIEW_BOARD_HTML, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/videos/{vid}/review-feedback")
async def get_review_feedback(vid: str):
    _video, _project, slug = await _slug(vid)
    path = project_dir(slug) / "review_feedback.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@router.put("/videos/{vid}/review-feedback")
async def put_review_feedback(vid: str, body: dict = Body(...)):
    _video, _project, slug = await _slug(vid)
    text = json.dumps(body, ensure_ascii=False, indent=2)
    if len(text.encode()) > MAX_FEEDBACK_BYTES:
        raise HTTPException(413, "Feedback is too large")
    path = project_dir(slug) / "review_feedback.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"ok": True}


@router.get("/scenes/{sid}/clip.mp4")
async def scene_clip(sid: str, orientation: Optional[Orientation] = None):
    """The scene's Veo clip: a local file when the agent has one, otherwise a redirect to Flow's signed link."""
    scene = await auth.require_scene(sid)
    _video, _project, slug = await _slug(scene["video_id"])
    prefix = (orientation or _video.get("orientation") or "VERTICAL").lower()
    local = resolve_4k_file(slug, scene["display_order"], scene["id"])
    if local:
        return FileResponse(local, media_type="video/mp4")
    for field in (f"{prefix}_upscale_url", f"{prefix}_video_url"):
        ref = scene.get(field)
        if not ref:
            continue
        parsed = urlparse(ref)
        if parsed.scheme in ("http", "https"):
            return RedirectResponse(ref, status_code=307)
        path = Path(url2pathname(parsed.path)) if parsed.scheme == "file" else Path(ref)
        if path.exists():
            return FileResponse(path, media_type="video/mp4")
    raise HTTPException(404, "This scene has no video yet")

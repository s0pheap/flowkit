"""FastAPI router for video review endpoints.

Two ways to review:
- On the host: ``POST …/review`` runs the vision analysis on this server with a
  CLI (``provider=claude|agy``, else the server's active provider) or the SDK.
- With the caller's own AI agent: ``POST …/review/prepare`` returns contact
  sheets and the vision prompt, the agent looks at them, and
  ``POST …/reviews/{review_id}/result`` scores its JSON exactly like a host review.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from agent.models.review import VideoReview, SceneReview
from agent.services import video_reviewer
from agent.services.video_reviewer import review_video, review_scene_video
from agent import auth
from agent.db.crud import get_video, get_project_characters, list_scenes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["reviews"])


def _check_mode_orientation(mode: str, orientation: Optional[str]) -> None:
    if mode not in ("light", "deep"):
        raise HTTPException(400, "mode must be 'light' or 'deep'")
    if orientation and orientation.upper() not in ("VERTICAL", "HORIZONTAL"):
        raise HTTPException(400, "orientation must be 'VERTICAL' or 'HORIZONTAL'")


def _host_provider(provider: Optional[str]) -> Optional[str]:
    """A CLI the caller asked the host to use. It must be known and installed here."""
    if not provider:
        return None
    installed = video_reviewer.host_providers()
    if provider not in installed:
        raise HTTPException(400, f"Unknown provider {provider!r}. Known: {sorted(installed)}")
    if not installed[provider]:
        available = [name for name, ok in installed.items() if ok]
        raise HTTPException(400, f"{provider!r} is not installed on this server. Installed: {available or 'none'}. "
                                 "Use your own agent instead: POST …/review/prepare.")
    return provider


async def _resolve_orientation(vid: str, video: Optional[dict], orientation: Optional[str]) -> str:
    if orientation:
        return orientation.upper()
    if video and video.get("orientation"):
        return video["orientation"]
    return await _detect_orientation(vid)


@router.post("/{vid}/review", response_model=VideoReview)
async def review_video_endpoint(
    vid: str,
    project_id: str = Query(..., description="Project ID"),
    mode: str = Query("light", description="Review mode: light (4fps) or deep (8fps)"),
    orientation: Optional[str] = Query(None, description="Orientation: VERTICAL or HORIZONTAL (auto-detected if omitted)"),
    scene_ids: Optional[str] = Query(None, description="Comma-separated scene IDs to review (omit for all)"),
    provider: Optional[str] = Query(None, description="Host CLI for the analysis: claude or agy (default: server setting)"),
):
    """Review all scene videos in a video, with the vision analysis running on this host."""
    _check_mode_orientation(mode, orientation)
    provider = _host_provider(provider)
    await auth.require_project(project_id)
    video = await auth.require_video(vid)
    orientation = await _resolve_orientation(vid, video, orientation)

    parsed_scene_ids = [s.strip() for s in scene_ids.split(",") if s.strip()] if scene_ids else None
    logger.info("Starting %s review for video %s (project %s, %s, scenes=%s, provider=%s)", mode, vid, project_id,
                orientation, len(parsed_scene_ids) if parsed_scene_ids else "all", provider or "default")
    try:
        result = await review_video(vid, project_id, mode=mode, orientation=orientation,
                                    scene_ids=parsed_scene_ids, provider=provider)
    except Exception as e:
        logger.exception("Review failed for video %s: %s", vid, e)
        raise HTTPException(500, f"Review failed: {e}")

    return result


@router.post("/{vid}/scenes/{sid}/review", response_model=SceneReview)
async def review_scene_endpoint(
    vid: str,
    sid: str,
    project_id: str = Query(..., description="Project ID"),
    mode: str = Query("light", description="Review mode: light (4fps) or deep (8fps)"),
    orientation: Optional[str] = Query(None, description="Orientation: VERTICAL or HORIZONTAL (auto-detected if omitted)"),
    provider: Optional[str] = Query(None, description="Host CLI for the analysis: claude or agy (default: server setting)"),
):
    """Review a single scene video, with the vision analysis running on this host."""
    _check_mode_orientation(mode, orientation)
    provider = _host_provider(provider)
    await auth.require_project(project_id)
    scene = await auth.require_scene(sid)
    if scene.get("video_id") != vid:
        raise HTTPException(404, "Scene does not belong to this video")
    orientation = await _resolve_orientation(vid, await get_video(vid), orientation)

    characters = await get_project_characters(project_id)

    logger.info("Starting %s review for scene %s (%s, provider=%s)", mode, sid, orientation, provider or "default")
    try:
        result = await review_scene_video(scene, characters, mode=mode, orientation=orientation,
                                          project_id=project_id, provider=provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Review failed for scene %s: %s", sid, e)
        raise HTTPException(500, f"Review failed: {e}")

    return result


# ─── Own-agent review ────────────────────────────────────────

def _job_view(vid: str, job: dict) -> dict:
    """What the agent needs: the prompt, where to fetch each sheet, and where to post the result."""
    base = f"/api/videos/{vid}/reviews/{job['review_id']}"
    return {
        **{k: job[k] for k in ("review_id", "scene_id", "display_order", "mode", "orientation",
                               "fps", "n_frames", "sheet_count", "prompt")},
        "sheets": [f"{base}/sheets/{i}.jpg" for i in range(1, job["sheet_count"] + 1)],
        "result_url": f"{base}/result",
    }


@router.post("/{vid}/review/prepare")
async def prepare_video_review(
    vid: str,
    project_id: str = Query(..., description="Project ID"),
    mode: str = Query("light", description="Review mode: light (4fps) or deep (8fps)"),
    orientation: Optional[str] = Query(None, description="Orientation: VERTICAL or HORIZONTAL (auto-detected if omitted)"),
    scene_ids: Optional[str] = Query(None, description="Comma-separated scene IDs to prepare (omit for all)"),
):
    """Contact sheets + prompt for every scene with a video, for the caller's own agent to analyse."""
    _check_mode_orientation(mode, orientation)
    await auth.require_project(project_id)
    video = await auth.require_video(vid)
    orientation = await _resolve_orientation(vid, video, orientation)
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    wanted = {s.strip() for s in scene_ids.split(",") if s.strip()} if scene_ids else None

    jobs, skipped = [], []
    for scene in sorted(await list_scenes(vid), key=lambda s: s.get("display_order") or 0):
        if wanted and scene["id"] not in wanted:
            continue
        if not scene.get(f"{prefix}_video_url"):
            skipped.append({"scene_id": scene["id"], "reason": f"no {orientation} video"})
            continue
        try:
            job = await video_reviewer.prepare_scene_review(scene, vid, project_id, mode=mode, orientation=orientation)
            jobs.append(_job_view(vid, job))
        except Exception as e:
            logger.error("Could not prepare review for scene %s: %s", scene["id"], e)
            skipped.append({"scene_id": scene["id"], "reason": str(e)[:300]})
    return {"video_id": vid, "mode": mode, "orientation": orientation, "reviews": jobs, "skipped": skipped}


@router.post("/{vid}/scenes/{sid}/review/prepare")
async def prepare_scene_review(
    vid: str,
    sid: str,
    project_id: str = Query(..., description="Project ID"),
    mode: str = Query("light", description="Review mode: light (4fps) or deep (8fps)"),
    orientation: Optional[str] = Query(None, description="Orientation: VERTICAL or HORIZONTAL (auto-detected if omitted)"),
):
    """Contact sheets + prompt for one scene, for the caller's own agent to analyse."""
    _check_mode_orientation(mode, orientation)
    await auth.require_project(project_id)
    scene = await auth.require_scene(sid)
    if scene.get("video_id") != vid:
        raise HTTPException(404, "Scene does not belong to this video")
    orientation = await _resolve_orientation(vid, await get_video(vid), orientation)
    try:
        job = await video_reviewer.prepare_scene_review(scene, vid, project_id, mode=mode, orientation=orientation)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Preparing review failed for scene %s: %s", sid, e)
        raise HTTPException(500, f"Preparing review failed: {e}")
    return _job_view(vid, job)


async def _own_job(vid: str, review_id: str) -> dict:
    await auth.require_video(vid)
    job = video_reviewer.load_review_job(review_id)
    if not job or job.get("video_id") != vid:
        raise HTTPException(404, "Review not found or expired. Prepare it again.")
    return job


@router.get("/{vid}/reviews/{review_id}/sheets/{index}.jpg")
async def review_sheet(vid: str, review_id: str, index: int):
    """One contact sheet of a prepared review (1 is the earliest)."""
    await _own_job(vid, review_id)
    path = video_reviewer.review_job_sheet(review_id, index)
    if not path:
        raise HTTPException(404, "No such sheet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{vid}/reviews/{review_id}/result", response_model=SceneReview)
async def submit_review_result(vid: str, review_id: str, analysis: Any = Body(...)):
    """Score the agent's analysis: the JSON object the prompt asks for, or {"raw": "<its text reply>"}."""
    job = await _own_job(vid, review_id)
    if isinstance(analysis, dict) and set(analysis) == {"raw"}:
        analysis = analysis["raw"]
    try:
        return video_reviewer.finish_scene_review(job, analysis)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, f"Could not read the analysis: {e}")


async def _detect_orientation(video_id: str) -> str:
    """Auto-detect orientation from scene video status fields."""
    scenes = await list_scenes(video_id)
    for scene in scenes:
        if scene.get("horizontal_video_status") == "COMPLETED" and scene.get("horizontal_video_url"):
            return "HORIZONTAL"
        if scene.get("vertical_video_status") == "COMPLETED" and scene.get("vertical_video_url"):
            return "VERTICAL"
    # Fallback: check image status
    for scene in scenes:
        if scene.get("horizontal_image_status") == "COMPLETED":
            return "HORIZONTAL"
        if scene.get("vertical_image_status") == "COMPLETED":
            return "VERTICAL"
    return "VERTICAL"

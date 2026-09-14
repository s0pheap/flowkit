from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent.models.request import Request, RequestCreate
from agent.models.enums import StatusType
from agent import auth
from agent.db import crud
from agent.models.look_feel import parse_look_feel

router = APIRouter(prefix="/requests", tags=["requests"])

_VEO_VIDEO_TYPES = {"GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS"}


async def _ffmpeg_scene_ids(items: list[RequestCreate]) -> list[str]:
    """Scenes in a video request whose look & feel says to render with ffmpeg instead of Veo."""
    blocked = []
    for item in items:
        if item.type not in _VEO_VIDEO_TYPES or not item.scene_id:
            continue
        scene = await crud.get_scene(item.scene_id)
        look = parse_look_feel(scene.get("look_feel")) if scene else None
        if look and look.mode == "ffmpeg":
            blocked.append(item.scene_id)
    return blocked


def _ffmpeg_scene_error(scene_ids: list[str]) -> HTTPException:
    short = ", ".join(sid[:8] for sid in scene_ids)
    return HTTPException(
        400,
        f"Scene(s) {short} are set to ffmpeg look & feel, so Veo would bill for a clip that is never used. "
        f"Render them with POST /api/scenes/{{sid}}/motion, or set look_feel.mode to 'generate'.",
    )


async def _check_targets(items: list[RequestCreate]) -> None:
    """A non-admin may only queue work on their own project, and every id must sit inside it.

    The worker generates into `project_id`'s Flow project, so a scene or character
    from someone else's project must not ride along with a project that is yours.
    """
    principal = auth.current_principal()
    if principal.is_admin:
        return
    for item in items:
        if not item.project_id:
            raise HTTPException(400, "project_id is required")
        await auth.require_project(item.project_id)
        if item.video_id:
            video = await auth.require_video(item.video_id)
            if video["project_id"] != item.project_id:
                raise HTTPException(400, f"Video {item.video_id[:8]} is not in project {item.project_id[:8]}")
        if item.scene_id:
            scene = await auth.require_scene(item.scene_id)
            video = await crud.get_video(scene["video_id"])
            if video["project_id"] != item.project_id or (item.video_id and scene["video_id"] != item.video_id):
                raise HTTPException(400, f"Scene {item.scene_id[:8]} is not in that project/video")
        if item.character_id:
            await auth.require_character(item.character_id)
        if item.source_media_id:
            await auth.require_media(item.source_media_id)


async def _visible(rows: list[dict]) -> list[dict]:
    allowed = await auth.allowed_project_ids()
    return rows if allowed is None else [r for r in rows if r.get("project_id") in allowed]


async def _request_or_404(rid: str) -> dict:
    r = await crud.get_request(rid)
    if not r or not await auth.can_access_project(r.get("project_id")):
        raise HTTPException(404, "Request not found")
    return r


class RequestUpdate(BaseModel):
    status: Optional[StatusType] = None
    media_id: Optional[str] = None
    output_url: Optional[str] = None
    error_message: Optional[str] = None
    request_id: Optional[str] = None


class BatchRequestCreate(BaseModel):
    requests: list[RequestCreate]


class BatchStatus(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    done: bool
    all_succeeded: bool
    orientation: Optional[str] = None


@router.post("", response_model=Request)
async def create(body: RequestCreate):
    await _check_targets([body])
    blocked = await _ffmpeg_scene_ids([body])
    if blocked:
        raise _ffmpeg_scene_error(blocked)
    data = body.model_dump(exclude_none=True)
    data["req_type"] = data.pop("type")

    # Reject if there's already an active request for the same scene + type
    scene_id = data.get("scene_id")
    req_type = data.get("req_type")
    if scene_id and req_type:
        existing = await crud.list_requests(scene_id=scene_id)
        active = [r for r in existing
                  if r.get("type") == req_type
                  and r.get("status") in ("PENDING", "PROCESSING")]
        if active:
            raise HTTPException(
                409,
                f"Active {req_type} request already exists for scene {scene_id[:8]} "
                f"(status={active[0]['status']}, id={active[0]['id'][:8]})"
            )

    # Auto-set video orientation (symmetric with batch endpoint)
    vid = data.get("video_id")
    orient = data.get("orientation")
    if vid and orient:
        await crud.update_video(vid, orientation=orient)

    return await crud.create_request(**data)


@router.post("/batch", response_model=list[Request])
async def create_batch(body: BatchRequestCreate):
    """Submit multiple requests atomically. Server handles throttling (max 5 concurrent, 10s cooldown).
    Duplicate active requests for the same scene+type are skipped (not errors)."""
    await _check_targets(body.requests)
    blocked = await _ffmpeg_scene_ids(body.requests)
    if blocked:
        raise _ffmpeg_scene_error(blocked)
    # Auto-set video orientation from the batch (tracks current active orientation)
    _seen_vids: set[str] = set()
    for item in body.requests:
        vid = item.video_id
        orient = item.orientation
        if vid and orient and vid not in _seen_vids:
            _seen_vids.add(vid)
            await crud.update_video(vid, orientation=orient)
    results = []
    for item in body.requests:
        data = item.model_dump(exclude_none=True)
        data["req_type"] = data.pop("type")
        scene_id = data.get("scene_id")
        character_id = data.get("character_id")
        req_type = data.get("req_type")
        # Idempotent: skip if active request already exists
        if scene_id and req_type:
            existing = await crud.list_requests(scene_id=scene_id)
            active = [r for r in existing
                      if r.get("type") == req_type
                      and r.get("status") in ("PENDING", "PROCESSING")]
            if active:
                results.append(active[0])
                continue
        if character_id and req_type:
            existing = await crud.list_requests(project_id=data.get("project_id"))
            active = [r for r in existing
                      if r.get("character_id") == character_id
                      and r.get("type") == req_type
                      and r.get("status") in ("PENDING", "PROCESSING")]
            if active:
                results.append(active[0])
                continue
        results.append(await crud.create_request(**data))
    return results


@router.get("", response_model=list[Request])
async def list_all(scene_id: str = None, status: str = None,
                   video_id: str = None, project_id: str = None):
    return await _visible(await crud.list_requests(scene_id=scene_id, status=status,
                                                   video_id=video_id, project_id=project_id))


@router.get("/pending", response_model=list[Request])
async def list_pending():
    return await _visible(await crud.list_pending_requests())


@router.get("/batch-status", response_model=BatchStatus)
async def batch_status(video_id: str = None, project_id: str = None,
                       type: str = None, orientation: str = None):
    """Aggregate status for all requests matching the filter.
    Poll this instead of polling N individual request IDs."""
    rows = await _visible(await crud.list_requests(video_id=video_id, project_id=project_id))
    if type:
        rows = [r for r in rows if r.get("type") == type]
    if orientation:
        rows = [r for r in rows if r.get("orientation") == orientation]
    counts = {"PENDING": 0, "PROCESSING": 0, "COMPLETED": 0, "FAILED": 0}
    for r in rows:
        s = r.get("status", "PENDING")
        counts[s] = counts.get(s, 0) + 1
    total = len(rows)
    return BatchStatus(
        total=total,
        pending=counts["PENDING"],
        processing=counts["PROCESSING"],
        orientation=orientation,
        completed=counts["COMPLETED"],
        failed=counts["FAILED"],
        done=(counts["PENDING"] == 0 and counts["PROCESSING"] == 0),
        all_succeeded=(counts["COMPLETED"] == total and total > 0),
    )


@router.get("/{rid}", response_model=Request)
async def get(rid: str):
    return await _request_or_404(rid)


@router.patch("/{rid}", response_model=Request)
async def update(rid: str, body: RequestUpdate):
    await _request_or_404(rid)
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    r = await crud.update_request(rid, **data)
    if not r:
        raise HTTPException(404, "Request not found")
    return r

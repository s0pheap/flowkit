"""Active project API — get/set the currently active project."""
import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agent import auth
from agent.db import crud

router = APIRouter(prefix="/api/active-project", tags=["active-project"])
logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent.parent / "active_project.json"


def _read_file() -> dict:
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt active_project.json, clearing: %s", e)
            _STATE_FILE.unlink()
    return {}


def _read_state() -> dict | None:
    """The caller's choice. Admins share the top-level entry (what the statusline reads); users get their own."""
    data = _read_file()
    principal = auth.current_principal()
    if principal.is_admin:
        return data if data.get("project_id") else None
    return (data.get("users") or {}).get(principal.id)


def _set_state(state: dict | None):
    data = _read_file()
    principal = auth.current_principal()
    if principal.is_admin:
        users = data.get("users")
        data = dict(state or {})
        if users:
            data["users"] = users
    else:
        users = data.setdefault("users", {})
        if state:
            users[principal.id] = state
        else:
            users.pop(principal.id, None)
    if data:
        _write_state(data)
    elif _STATE_FILE.exists():
        _STATE_FILE.unlink()


def _write_state(data: dict):
    """Atomic write — temp file + os.replace to avoid partial reads."""
    content = json.dumps(data, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=_STATE_FILE.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.replace(tmp, _STATE_FILE)
    except BaseException:
        os.close(fd)
        os.unlink(tmp)
        raise


def _clear_state():
    _set_state(None)


@router.get("")
async def get_active_project():
    """Return the active project. Falls back to most recently created if none set."""
    state = _read_state()

    if state and state.get("project_id"):
        project = await crud.get_project(state["project_id"])
        if project and await auth.can_access_project(project["id"]):
            # Enrich with video info
            videos = await crud.list_videos(project_id=project["id"])
            video = videos[0] if videos else None
            return {
                "project_id": project["id"],
                "project_name": project["name"],
                "video_id": video["id"] if video else None,
                "orientation": video.get("orientation") if video else None,
                "material": project.get("material"),
                "status": project.get("status"),
                "source": "explicit",
            }
        else:
            # Stale reference — clear and fall back
            _clear_state()

    # Fall back to most recent project
    projects = await crud.list_projects()
    allowed = await auth.allowed_project_ids()
    if allowed is not None:
        projects = [p for p in projects if p["id"] in allowed]
    if not projects:
        return {"project_id": None, "project_name": None, "source": "none"}

    project = projects[0]  # list is ORDER BY created_at DESC, [0] = most recent
    videos = await crud.list_videos(project_id=project["id"])
    video = videos[0] if videos else None
    return {
        "project_id": project["id"],
        "project_name": project["name"],
        "video_id": video["id"] if video else None,
        "orientation": video.get("orientation") if video else None,
        "material": project.get("material"),
        "status": project.get("status"),
        "source": "fallback_most_recent",
    }


@router.put("")
async def set_active_project(body: dict):
    """Set the active project by project_id."""
    project_id = body.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    project = await auth.require_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    _set_state({"project_id": project_id})
    logger.info("Active project set: %s (%s)", project["name"], project_id[:8])

    videos = await crud.list_videos(project_id=project_id)
    video = videos[0] if videos else None
    return {
        "project_id": project["id"],
        "project_name": project["name"],
        "video_id": video["id"] if video else None,
        "orientation": video.get("orientation") if video else None,
        "material": project.get("material"),
        "status": project.get("status"),
        "source": "explicit",
    }


@router.delete("")
async def clear_active_project():
    """Clear the active project (revert to fallback behavior)."""
    _clear_state()
    return {"status": "cleared", "message": "Active project cleared. Will use most recent project as fallback."}

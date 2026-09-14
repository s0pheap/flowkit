"""API keys, and what each caller is allowed to touch.

With AUTH_ENABLED=0 (the default) every caller is the local admin and nothing
here changes behaviour. With AUTH_ENABLED=1, `AuthMiddleware` resolves the key
on every /api and /ws call into a `Principal`, and routers ask the `require_*`
helpers whether that principal may use a given project, video, scene,
character or media id.

Access follows the Flow project: a user is granted Flow project uuids
(`user_project`), and since a local project's id *is* its Flow uuid, the videos,
scenes and requests under a granted project are theirs. Characters are shared
M:N, so a user may use one they created or one linked to a granted project.
Anything a user may not see answers 404, not 403, so ids can't be probed.
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

from fastapi import HTTPException

from agent import config
from agent.db import crud
from agent.utils.slugify import slugify

logger = logging.getLogger(__name__)

KEY_PREFIX = "fk_"

# Paths that answer without a key. Each one guards itself if it needs to.
PUBLIC_PATHS = frozenset({
    "/api/ext/callback",    # the extension has no key; restricted to loopback in main.py
    "/api/music/callback",  # Suno's webhook; only logs
})


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    is_admin: bool


LOCAL_ADMIN = Principal(id="local", name="local", is_admin=True)
BOOTSTRAP_ADMIN = Principal(id="admin", name="admin", is_admin=True)

_principal: contextvars.ContextVar[Optional[Principal]] = contextvars.ContextVar("fk_principal", default=None)


# ─── Keys ────────────────────────────────────────────────────

def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    # Keys are 256 random bits, so a plain sha256 is enough; no need for a slow KDF.
    return hashlib.sha256(key.encode()).hexdigest()


def key_prefix(key: str) -> str:
    return key[:10]


async def authenticate(key: Optional[str]) -> Optional[Principal]:
    if not key:
        return None
    if config.ADMIN_API_KEY and hmac.compare_digest(key, config.ADMIN_API_KEY):
        return BOOTSTRAP_ADMIN
    user = await crud.get_api_user_by_key_hash(hash_key(key))
    if not user or user["disabled"]:
        return None
    await _touch(user)
    return Principal(id=user["id"], name=user["name"], is_admin=bool(user["is_admin"]))


async def _touch(user: dict) -> None:
    """Record last use, at most every few minutes so reads don't all become writes."""
    now = datetime.now(timezone.utc)
    last = user.get("last_used_at")
    if last:
        try:
            if now - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < timedelta(minutes=5):
                return
        except ValueError:
            pass
    await crud.update_api_user(user["id"], last_used_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"))


# ─── Media tokens ────────────────────────────────────────────
# <video>, <img> and download links can't send a header, so the dashboard asks
# for a short-lived token and puts it in the URL. A token only works for GET on
# the file routes below, and the route still checks project ownership.

MEDIA_TOKEN_TTL = 6 * 3600
MEDIA_PATHS = re.compile(
    r"^/api/(scenes/[^/]+/(motion|clip)\.mp4"
    r"|videos/[^/]+/(final\.mp4|captions\.srt|music/[^/]+))$"
)
_media_secret = secrets.token_bytes(32)


def _media_key() -> bytes:
    # Tied to the admin key when there is one, so tokens survive a restart and
    # rotating the admin key revokes them.
    if config.ADMIN_API_KEY:
        return hashlib.sha256(b"flowkit-media:" + config.ADMIN_API_KEY.encode()).digest()
    return _media_secret


def sign_media_token(p: Principal, ttl: int = MEDIA_TOKEN_TTL) -> tuple[str, int]:
    expires = int(time.time()) + ttl
    payload = f"{p.id}.{expires}"
    sig = hmac.new(_media_key(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", expires


async def principal_from_media_token(token: Optional[str]) -> Optional[Principal]:
    try:
        uid, expires, sig = (token or "").rsplit(".", 2)
        expected = hmac.new(_media_key(), f"{uid}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected) or int(expires) < time.time():
            return None
    except ValueError:
        return None
    if uid == BOOTSTRAP_ADMIN.id:
        return BOOTSTRAP_ADMIN if config.ADMIN_API_KEY else None
    user = await crud.get_api_user(uid)
    if not user or user["disabled"]:
        return None
    return Principal(id=user["id"], name=user["name"], is_admin=bool(user["is_admin"]))


def _query_value(scope, name: str) -> Optional[str]:
    values = parse_qs(scope.get("query_string", b"").decode()).get(name)
    return values[0] if values else None


def _key_from_scope(scope) -> Optional[str]:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    if headers.get("x-api-key"):
        return headers["x-api-key"].strip()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if scope["type"] == "websocket":
        # Browsers can't set headers on a WebSocket, so the dashboard passes ?api_key=.
        return _query_value(scope, "api_key")
    return None


# ─── Middleware ──────────────────────────────────────────────

class AuthMiddleware:
    """Pure ASGI, so it covers WebSockets too and the principal is visible to handlers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not config.AUTH_ENABLED:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        protected = (path.startswith("/api") or path.startswith("/ws")) and path not in PUBLIC_PATHS
        if not protected or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        principal = await authenticate(_key_from_scope(scope))
        if (principal is None and scope["type"] == "http" and scope.get("method") in ("GET", "HEAD")
                and MEDIA_PATHS.match(path)):
            principal = await principal_from_media_token(_query_value(scope, "token"))
        if principal is None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401, "reason": "Missing or invalid API key"})
                return
            body = json.dumps({"detail": "Missing or invalid API key. Send it as the X-API-Key header."}).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": body})
            return

        token = _principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _principal.reset(token)


# ─── Who is calling ──────────────────────────────────────────

def current_principal() -> Principal:
    p = _principal.get()
    if p is not None:
        return p
    if not config.AUTH_ENABLED:
        return LOCAL_ADMIN
    raise HTTPException(401, "Missing or invalid API key")


def require_admin() -> Principal:
    p = current_principal()
    if not p.is_admin:
        raise HTTPException(403, "Admin only")
    return p


async def allowed_project_ids(p: Optional[Principal] = None) -> Optional[set[str]]:
    """Project ids the caller may use, or None for all of them."""
    p = p or current_principal()
    if p.is_admin:
        return None
    return set(await crud.list_granted_project_ids(p.id))


async def can_access_project(project_id: Optional[str], p: Optional[Principal] = None) -> bool:
    allowed = await allowed_project_ids(p)
    return allowed is None or (project_id is not None and project_id in allowed)


# ─── Guards: return the row, or raise 404 ────────────────────

async def require_project(project_id: str) -> Optional[dict]:
    """The project row (None if an admin asks for one that doesn't exist)."""
    if not await can_access_project(project_id):
        raise HTTPException(404, "Project not found")
    return await crud.get_project(project_id)


async def require_video(video_id: str) -> dict:
    video = await crud.get_video(video_id)
    if not video or not await can_access_project(video["project_id"]):
        raise HTTPException(404, "Video not found")
    return video


async def require_scene(scene_id: str) -> dict:
    scene = await crud.get_scene(scene_id)
    if not scene:
        raise HTTPException(404, "Scene not found")
    if current_principal().is_admin:
        return scene
    video = await crud.get_video(scene["video_id"])
    if not video or not await can_access_project(video["project_id"]):
        raise HTTPException(404, "Scene not found")
    return scene


async def can_access_character(character: dict, p: Optional[Principal] = None) -> bool:
    p = p or current_principal()
    if p.is_admin or character.get("owner_user_id") == p.id:
        return True
    allowed = await allowed_project_ids(p)
    return any(pid in allowed for pid in await crud.list_character_project_ids(character["id"]))


async def require_character(character_id: str) -> dict:
    character = await crud.get_character(character_id)
    if not character or not await can_access_character(character):
        raise HTTPException(404, "Character not found")
    return character


async def require_media(media_id: str) -> None:
    """A Flow media id is the caller's if it belongs to one of their scenes or characters."""
    p = current_principal()
    if p.is_admin:
        return
    allowed = await allowed_project_ids(p)
    for scene in await crud.list_scenes_by_media_id(media_id):
        video = await crud.get_video(scene["video_id"])
        if video and video["project_id"] in allowed:
            return
    for character in await crud.list_characters_by_media_id(media_id):
        if await can_access_character(character, p):
            return
    raise HTTPException(404, "Media not found")


async def require_output_path(path: str) -> None:
    """Non-admins may only write or read files under their own projects' output folders."""
    p = current_principal()
    if p.is_admin:
        return
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else config.BASE_DIR / candidate).resolve()
    for pid in await allowed_project_ids(p):
        project = await crud.get_project(pid)
        if project and resolved.is_relative_to((config.OUTPUT_DIR / slugify(project["name"])).resolve()):
            return
    raise HTTPException(403, "Path must be inside one of your projects' output folders")

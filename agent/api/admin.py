"""User and API key management (admin), and `GET /api/auth/me` for any caller."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import auth, config
from agent.db import crud
from agent.users import UserError, check_project_id, create_user, public_user, rotate_key

router = APIRouter(tags=["admin"])


class UserCreate(BaseModel):
    name: str
    is_admin: bool = False
    project_ids: list[str] = []


class UserUpdate(BaseModel):
    is_admin: Optional[bool] = None
    disabled: Optional[bool] = None


class ProjectGrant(BaseModel):
    project_id: str


async def _user_or_404(uid: str) -> dict:
    user = await crud.get_api_user(uid)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.get("/auth/me")
async def me():
    """Who the key belongs to and which Flow projects it may use."""
    p = auth.current_principal()
    allowed = await auth.allowed_project_ids(p)
    return {
        "auth_enabled": config.AUTH_ENABLED,
        "name": p.name,
        "is_admin": p.is_admin,
        "project_ids": None if allowed is None else sorted(allowed),
    }


@router.get("/auth/media-token")
async def media_token():
    """A short-lived token for ?token= on video/caption URLs, which can't carry a header."""
    token, expires = auth.sign_media_token(auth.current_principal())
    return {"token": token, "expires_at": expires}


@router.get("/admin/users")
async def list_users():
    auth.require_admin()
    return [await public_user(u) for u in await crud.list_api_users()]


@router.post("/admin/users", status_code=201)
async def create(body: UserCreate):
    """Create a user. The response carries the API key; it is not retrievable later."""
    auth.require_admin()
    try:
        user, key = await create_user(body.name, is_admin=body.is_admin, project_ids=body.project_ids)
    except UserError as e:
        raise HTTPException(400, str(e))
    return {"user": await public_user(user), "api_key": key}


@router.patch("/admin/users/{uid}")
async def update(uid: str, body: UserUpdate):
    auth.require_admin()
    await _user_or_404(uid)
    changes = {k: int(v) for k, v in body.model_dump(exclude_none=True).items()}
    return await public_user(await crud.update_api_user(uid, **changes))


@router.post("/admin/users/{uid}/rotate-key")
async def rotate(uid: str):
    auth.require_admin()
    await _user_or_404(uid)
    return {"api_key": await rotate_key(uid)}


@router.delete("/admin/users/{uid}")
async def delete(uid: str):
    auth.require_admin()
    if not await crud.delete_api_user(uid):
        raise HTTPException(404, "User not found")
    return {"ok": True}


@router.post("/admin/users/{uid}/projects")
async def grant(uid: str, body: ProjectGrant):
    auth.require_admin()
    await _user_or_404(uid)
    try:
        project_id = check_project_id(body.project_id)
    except UserError as e:
        raise HTTPException(400, str(e))
    await crud.grant_project(uid, project_id)
    return await public_user(await crud.get_api_user(uid))


@router.delete("/admin/users/{uid}/projects/{project_id}")
async def revoke(uid: str, project_id: str):
    auth.require_admin()
    await _user_or_404(uid)
    if not await crud.revoke_project(uid, project_id):
        raise HTTPException(404, "Grant not found")
    return await public_user(await crud.get_api_user(uid))

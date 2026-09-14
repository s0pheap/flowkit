from fastapi import APIRouter, HTTPException
from agent.models.character import Character, CharacterCreate, CharacterUpdate
from agent.sdk.persistence.sqlite_repository import SQLiteRepository
from agent.utils.slugify import slugify
from agent import auth
from agent.db import crud

router = APIRouter(prefix="/characters", tags=["characters"])


def _get_repo() -> SQLiteRepository:
    return SQLiteRepository()


@router.post("", response_model=Character)
async def create(body: CharacterCreate):
    principal = auth.current_principal()
    repo = _get_repo()
    character = await repo.create_character(**body.model_dump(exclude_none=True))
    if not principal.is_admin:
        await crud.set_character_owner(character.id, principal.id)
    return character


@router.get("", response_model=list[Character])
async def list_all():
    repo = _get_repo()
    rows = await repo.list("character", order_by="created_at DESC")
    principal = auth.current_principal()
    if not principal.is_admin:
        rows = [r for r in rows if await auth.can_access_character(r, principal)]
    return [repo._row_to_character(r) for r in rows]


@router.get("/{cid}", response_model=Character)
async def get(cid: str):
    await auth.require_character(cid)
    repo = _get_repo()
    c = await repo.get_character(cid)
    if not c:
        raise HTTPException(404, "Character not found")
    return c


@router.patch("/{cid}", response_model=Character)
async def update(cid: str, body: CharacterUpdate):
    await auth.require_character(cid)
    repo = _get_repo()
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates:
        updates["slug"] = slugify(updates["name"])
    row = await repo.update("character", cid, **updates)
    if not row:
        raise HTTPException(404, "Character not found")
    return repo._row_to_character(row)


@router.delete("/{cid}")
async def delete(cid: str):
    await auth.require_character(cid)
    repo = _get_repo()
    if not await repo.delete_character(cid):
        raise HTTPException(404, "Character not found")
    return {"ok": True}

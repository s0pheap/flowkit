"""Manage API users from the command line.

    python -m agent.users create alice --project <flow-project-uuid>
    python -m agent.users list
    python -m agent.users grant alice <flow-project-uuid>
    python -m agent.users revoke alice <flow-project-uuid>
    python -m agent.users rotate-key alice
    python -m agent.users disable alice      # or: enable, delete

A key is printed once, when it is created or rotated. Only its hash is stored.
The same operations are available over HTTP at /api/admin/users.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

from agent import auth
from agent.db import crud

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


class UserError(ValueError):
    pass


def check_project_id(project_id: str) -> str:
    if not _UUID_RE.match(project_id or ""):
        raise UserError(f"Not a Flow project uuid: {project_id!r}")
    return project_id


async def create_user(name: str, is_admin: bool = False, project_ids: list[str] | None = None) -> tuple[dict, str]:
    if not _NAME_RE.match(name or ""):
        raise UserError("Name must be 1-64 letters, digits or _ . @ -")
    if await crud.get_api_user_by_name(name):
        raise UserError(f"User {name!r} already exists")
    project_ids = [check_project_id(pid) for pid in project_ids or []]
    key = auth.generate_key()
    user = await crud.create_api_user(name, auth.hash_key(key), auth.key_prefix(key), is_admin=is_admin)
    for pid in project_ids:
        await crud.grant_project(user["id"], pid)
    return user, key


async def rotate_key(user_id: str) -> str:
    key = auth.generate_key()
    await crud.update_api_user(user_id, key_hash=auth.hash_key(key), key_prefix=auth.key_prefix(key))
    return key


async def public_user(user: dict) -> dict:
    """A user as the API shows it: no key hash, plus granted projects."""
    return {
        "id": user["id"],
        "name": user["name"],
        "key_prefix": user["key_prefix"],
        "is_admin": bool(user["is_admin"]),
        "disabled": bool(user["disabled"]),
        "project_ids": await crud.list_granted_project_ids(user["id"]),
        "created_at": user["created_at"],
        "last_used_at": user["last_used_at"],
    }


# ─── CLI ─────────────────────────────────────────────────────

async def _lookup(name: str) -> dict:
    user = await crud.get_api_user_by_name(name)
    if not user:
        raise UserError(f"No user named {name!r}")
    return user


async def _run(args) -> None:
    from agent.db.schema import init_db, close_db
    await init_db()
    try:
        if args.cmd == "create":
            user, key = await create_user(args.name, is_admin=args.admin, project_ids=args.project)
            info = await public_user(user)
            print(f"Created {info['name']} (admin={info['is_admin']}, projects={info['project_ids'] or 'none'})")
            print(f"API key (shown once): {key}")
        elif args.cmd == "list":
            for user in await crud.list_api_users():
                info = await public_user(user)
                flags = ",".join(f for f, on in (("admin", info["is_admin"]), ("disabled", info["disabled"])) if on)
                print(f"{info['name']:<20} {info['key_prefix']}…  {flags or '-':<15} "
                      f"last used {info['last_used_at'] or 'never':<21} projects: {', '.join(info['project_ids']) or '-'}")
        elif args.cmd == "grant":
            user = await _lookup(args.name)
            await crud.grant_project(user["id"], check_project_id(args.project_id))
            print(f"Granted {args.project_id} to {args.name}")
        elif args.cmd == "revoke":
            user = await _lookup(args.name)
            if not await crud.revoke_project(user["id"], check_project_id(args.project_id)):
                raise UserError(f"{args.name} had no grant for {args.project_id}")
            print(f"Revoked {args.project_id} from {args.name}")
        elif args.cmd == "rotate-key":
            user = await _lookup(args.name)
            print(f"New API key for {args.name} (shown once; the old key stops working now): {await rotate_key(user['id'])}")
        elif args.cmd in ("disable", "enable"):
            user = await _lookup(args.name)
            await crud.update_api_user(user["id"], disabled=int(args.cmd == "disable"))
            print(f"{args.name} {args.cmd}d")
        elif args.cmd == "delete":
            user = await _lookup(args.name)
            await crud.delete_api_user(user["id"])
            print(f"Deleted {args.name} (their projects are kept)")
    finally:
        await close_db()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent.users", description="Manage Flow Kit API users")
    sub = parser.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create", help="create a user and print their API key")
    create.add_argument("name")
    create.add_argument("--project", action="append", default=[], metavar="FLOW_PROJECT_UUID",
                        help="grant a Flow project (repeatable)")
    create.add_argument("--admin", action="store_true", help="full access, including server settings")
    sub.add_parser("list", help="list users")
    for cmd in ("grant", "revoke"):
        p = sub.add_parser(cmd, help=f"{cmd} a Flow project")
        p.add_argument("name")
        p.add_argument("project_id")
    for cmd in ("rotate-key", "disable", "enable", "delete"):
        sub.add_parser(cmd).add_argument("name")

    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

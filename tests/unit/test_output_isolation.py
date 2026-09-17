"""Keeping one project's output folder out of another project's reach.

A project's files live in a flat ``output/<name slug>/``, so the slug is the whole
of the separation between two owners on a shared server. These tests pin the three
things that keeps true: no two projects may slugify alike, a rename takes the folder
with it, and a slug is never empty (which would name the output root itself).
"""
import pytest
from fastapi import HTTPException

from agent import auth, config
from agent.api import active_project, look_feel, projects as projects_api
from agent.db import crud, schema
from agent.main import app
from agent.utils import paths
from agent.utils.slugify import slugify

import httpx

ADMIN_KEY = "admin-isolation-key"
PROJECT = "cccccccc-0000-4000-8000-00000000aaaa"
OTHER = "dddddddd-0000-4000-8000-00000000bbbb"
KOREAN = "한국어 프로젝트"


@pytest.fixture
async def env(tmp_path, monkeypatch):
    await schema.close_db()
    out = tmp_path / "output"
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "isolation.db")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "OUTPUT_DIR", out)
    monkeypatch.setattr(paths, "OUTPUT_DIR", out)
    monkeypatch.setattr(look_feel, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setattr(active_project, "_STATE_FILE", tmp_path / "active.json")
    await schema.init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100") as client:
        yield out, client


def as_user(uid: str, is_admin: bool = False):
    """Run the next auth call as this principal, the way AuthMiddleware would."""
    return auth._principal.set(auth.Principal(id=uid, name=uid, is_admin=is_admin))


class TestSlugUniqueness:
    async def test_a_second_flow_project_cannot_take_an_existing_name(self, env):
        """The check that guards this used to filter itself down to an empty list."""
        await crud.create_project(name="Moon Base", id=PROJECT)
        with pytest.raises(HTTPException) as e:
            await projects_api._require_unique_slug("moon base!")
        assert e.value.status_code == 409
        assert "moon_base" in e.value.detail

    async def test_a_project_may_keep_its_own_name(self, env):
        await crud.create_project(name="Moon Base", id=PROJECT)
        await projects_api._require_unique_slug("Moon Base", project_id=PROJECT)

    async def test_rename_to_a_taken_name_is_refused(self, env):
        _out, client = env
        await crud.create_project(name="Moon Base", id=PROJECT)
        other = await crud.create_project(name="Other", id=OTHER)
        r = await client.patch(f"/api/projects/{other['id']}", headers={"X-API-Key": ADMIN_KEY},
                               json={"name": "moon base"})
        assert r.status_code == 409


class TestRenameMovesFiles:
    async def test_rename_takes_the_output_folder_with_it(self, env):
        out, client = env
        await crud.create_project(name="Moon Base", id=PROJECT)
        (out / "moon_base" / "tts").mkdir(parents=True)
        (out / "moon_base" / "tts" / "scene_001.wav").write_bytes(b"audio")

        r = await client.patch(f"/api/projects/{PROJECT}", headers={"X-API-Key": ADMIN_KEY},
                               json={"name": "Mars Base"})
        assert r.status_code == 200, r.text
        # The old folder must not survive: the next project to take that name
        # would inherit these files, and the right to read them.
        assert not (out / "moon_base").exists()
        assert (out / "mars_base" / "tts" / "scene_001.wav").read_bytes() == b"audio"

    async def test_rename_onto_an_occupied_folder_is_refused_and_changes_nothing(self, env):
        out, client = env
        await crud.create_project(name="Moon Base", id=PROJECT)
        (out / "moon_base").mkdir(parents=True)
        (out / "mars_base").mkdir(parents=True)  # left behind by some earlier project

        r = await client.patch(f"/api/projects/{PROJECT}", headers={"X-API-Key": ADMIN_KEY},
                               json={"name": "Mars Base"})
        assert r.status_code == 409
        assert (out / "moon_base").is_dir()
        assert (await crud.get_project(PROJECT))["name"] == "Moon Base"

    async def test_rename_without_files_on_disk_still_works(self, env):
        _out, client = env
        await crud.create_project(name="Moon Base", id=PROJECT)
        r = await client.patch(f"/api/projects/{PROJECT}", headers={"X-API-Key": ADMIN_KEY},
                               json={"name": "Mars Base"})
        assert r.status_code == 200, r.text


class TestSlugIsNeverEmpty:
    def test_a_name_with_no_ascii_still_gets_a_folder_of_its_own(self):
        assert slugify(KOREAN) not in ("", None)
        assert slugify(KOREAN) != slugify("ភ្នំស្រី")
        assert slugify("!!!") != ""

    def test_the_fallback_is_stable_across_calls(self):
        assert slugify(KOREAN) == slugify(KOREAN)


class TestOutputPathGuard:
    async def test_a_non_ascii_project_does_not_unlock_the_whole_output_root(self, env):
        """An empty slug made OUTPUT_DIR / slug == OUTPUT_DIR, which matched every path."""
        out, _client = env
        await crud.create_project(name=KOREAN, id=PROJECT)
        await crud.create_project(name="Victim", id=OTHER)
        user = await crud.create_api_user(name="mallory", key_hash="x", key_prefix="fk_mallory", is_admin=False)
        await crud.grant_project(user["id"], PROJECT)

        token = as_user(user["id"])
        try:
            with pytest.raises(HTTPException) as e:
                await auth.require_output_path(str(out / "victim" / "tts" / "secret.wav"))
            assert e.value.status_code == 403
            with pytest.raises(HTTPException):
                await auth.require_output_path(str(out))
            # Their own folder is still reachable.
            await auth.require_output_path(str(out / slugify(KOREAN) / "tts" / "mine.wav"))
        finally:
            auth._principal.reset(token)

    async def test_a_user_cannot_reach_another_projects_folder(self, env):
        out, _client = env
        await crud.create_project(name="Mine", id=PROJECT)
        await crud.create_project(name="Yours", id=OTHER)
        user = await crud.create_api_user(name="alice", key_hash="y", key_prefix="fk_alice", is_admin=False)
        await crud.grant_project(user["id"], PROJECT)

        token = as_user(user["id"])
        try:
            await auth.require_output_path(str(out / "mine" / "render.mp4"))
            with pytest.raises(HTTPException) as e:
                await auth.require_output_path(str(out / "yours" / "render.mp4"))
            assert e.value.status_code == 403
        finally:
            auth._principal.reset(token)

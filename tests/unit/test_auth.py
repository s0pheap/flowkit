"""API keys and per-user project access (agent/auth.py and the routers that use it).

Runs the real FastAPI app over ASGI (no lifespan, so no worker or extension
socket) against a throwaway SQLite file.
"""
import json

import httpx
import pytest

from agent import auth, config
from agent.api import active_project
from agent.db import crud, schema
from agent import main as agent_main
from agent.main import _event_visible, app

ADMIN_KEY = "admin-test-key"
PROJECT_A = "aaaaaaaa-0000-4000-8000-000000000001"
PROJECT_B = "bbbbbbbb-0000-4000-8000-000000000002"
PROJECT_A2 = "aaaaaaaa-0000-4000-8000-000000000003"


@pytest.fixture
async def db(tmp_path, monkeypatch):
    await schema.close_db()
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "auth_test.db")
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setattr(active_project, "_STATE_FILE", tmp_path / "active_project.json")
    await schema.init_db()
    yield tmp_path
    await schema.close_db()


@pytest.fixture
async def http(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8100") as client:
        yield client


def as_key(key):
    return {"X-API-Key": key}


async def make_user(http, name, projects):
    r = await http.post("/api/admin/users", headers=as_key(ADMIN_KEY), json={"name": name, "project_ids": projects})
    assert r.status_code == 201, r.text
    return r.json()


async def seed_project(pid, name):
    project = await crud.create_project(name=name, id=pid)
    video = await crud.create_video(project_id=pid, title=f"{name} video")
    scene = await crud.create_scene(video_id=video["id"], display_order=0, prompt="a scene")
    character = await crud.create_character(name=f"{name} hero")
    await crud.link_character_to_project(pid, character["id"])
    return project, video, scene, character


@pytest.fixture
async def world(http):
    """Alice owns project A, Bob owns project B."""
    a = await seed_project(PROJECT_A, "Alpha")
    b = await seed_project(PROJECT_B, "Bravo")
    alice = await make_user(http, "alice", [PROJECT_A])
    bob = await make_user(http, "bob", [PROJECT_B])
    return {"a": a, "b": b, "alice": alice["api_key"], "bob": bob["api_key"],
            "alice_id": alice["user"]["id"]}


# ─── Keys ────────────────────────────────────────────────────

class TestKeys:
    async def test_no_key_is_rejected(self, http):
        r = await http.get("/api/projects")
        assert r.status_code == 401

    async def test_wrong_key_is_rejected(self, http):
        r = await http.get("/api/projects", headers=as_key("fk_nope"))
        assert r.status_code == 401

    async def test_health_needs_no_key(self, http):
        r = await http.get("/health")
        assert r.status_code == 200

    async def test_bearer_header_works(self, http, world):
        r = await http.get("/api/auth/me", headers={"Authorization": f"Bearer {world['alice']}"})
        assert r.json() == {"auth_enabled": True, "name": "alice", "is_admin": False, "project_ids": [PROJECT_A]}

    async def test_auth_disabled_trusts_everyone(self, http, monkeypatch):
        monkeypatch.setattr(config, "AUTH_ENABLED", False)
        r = await http.get("/api/projects")
        assert r.status_code == 200

    async def test_only_the_hash_is_stored(self, http, world):
        rows = await crud.list_api_users()
        stored = json.dumps(rows)
        assert world["alice"] not in stored
        assert auth.hash_key(world["alice"]) in stored

    async def test_disabled_user_is_rejected(self, http, world):
        r = await http.patch(f"/api/admin/users/{world['alice_id']}", headers=as_key(ADMIN_KEY), json={"disabled": True})
        assert r.status_code == 200
        assert (await http.get("/api/projects", headers=as_key(world["alice"]))).status_code == 401

    async def test_rotated_key_replaces_the_old_one(self, http, world):
        r = await http.post(f"/api/admin/users/{world['alice_id']}/rotate-key", headers=as_key(ADMIN_KEY))
        new_key = r.json()["api_key"]
        assert (await http.get("/api/projects", headers=as_key(world["alice"]))).status_code == 401
        assert (await http.get("/api/projects", headers=as_key(new_key))).status_code == 200

    async def test_users_cannot_manage_users(self, http, world):
        r = await http.get("/api/admin/users", headers=as_key(world["alice"]))
        assert r.status_code == 403


# ─── Project isolation ───────────────────────────────────────

class TestIsolation:
    async def test_project_list_shows_only_grants(self, http, world):
        r = await http.get("/api/projects", headers=as_key(world["alice"]))
        assert [p["id"] for p in r.json()] == [PROJECT_A]

    async def test_admin_sees_everything(self, http, world):
        r = await http.get("/api/projects", headers=as_key(ADMIN_KEY))
        assert {p["id"] for p in r.json()} == {PROJECT_A, PROJECT_B}

    async def test_other_users_rows_are_404(self, http, world):
        _, video_b, scene_b, char_b = world["b"]
        key = as_key(world["alice"])
        for path in (f"/api/projects/{PROJECT_B}", f"/api/videos/{video_b['id']}", f"/api/scenes/{scene_b['id']}",
                     f"/api/characters/{char_b['id']}", f"/api/videos?project_id={PROJECT_B}",
                     f"/api/scenes?video_id={video_b['id']}", f"/api/videos/{video_b['id']}/assembly-plan"):
            assert (await http.get(path, headers=key)).status_code == 404, path

    async def test_cannot_edit_or_delete_other_users_rows(self, http, world):
        _, video_b, scene_b, _ = world["b"]
        key = as_key(world["alice"])
        assert (await http.patch(f"/api/scenes/{scene_b['id']}", headers=key, json={"prompt": "x"})).status_code == 404
        assert (await http.delete(f"/api/videos/{video_b['id']}", headers=key)).status_code == 404
        assert (await crud.get_scene(scene_b["id"]))["prompt"] == "a scene"

    async def test_own_rows_work(self, http, world):
        _, video_a, scene_a, _ = world["a"]
        key = as_key(world["alice"])
        assert (await http.get(f"/api/scenes/{scene_a['id']}", headers=key)).status_code == 200
        r = await http.post("/api/scenes", headers=key, json={"video_id": video_a["id"], "prompt": "new"})
        assert r.status_code == 200

    async def test_cannot_add_scene_to_other_users_video(self, http, world):
        _, video_b, _, _ = world["b"]
        r = await http.post("/api/scenes", headers=as_key(world["alice"]), json={"video_id": video_b["id"], "prompt": "x"})
        assert r.status_code == 404

    async def test_characters_list_is_scoped_and_created_ones_are_owned(self, http, world):
        key = as_key(world["alice"])
        r = await http.post("/api/characters", headers=key, json={"name": "Loner"})
        assert r.status_code == 200
        loner = r.json()["id"]
        names = {c["name"] for c in (await http.get("/api/characters", headers=key)).json()}
        assert names == {"Alpha hero", "Loner"}
        assert (await http.get(f"/api/characters/{loner}", headers=as_key(world["bob"]))).status_code == 404

    async def test_cannot_link_other_users_character(self, http, world):
        _, _, _, char_b = world["b"]
        r = await http.post(f"/api/projects/{PROJECT_A}/characters/{char_b['id']}", headers=as_key(world["alice"]))
        assert r.status_code == 404


# ─── Generation requests ─────────────────────────────────────

class TestRequests:
    def image_request(self, project, video, scene):
        return {"type": "GENERATE_IMAGE", "project_id": project, "video_id": video["id"],
                "scene_id": scene["id"], "orientation": "VERTICAL"}

    async def test_own_request_is_queued(self, http, world):
        _, video_a, scene_a, _ = world["a"]
        r = await http.post("/api/requests", headers=as_key(world["alice"]),
                            json=self.image_request(PROJECT_A, video_a, scene_a))
        assert r.status_code == 200, r.text

    async def test_other_users_project_is_refused(self, http, world):
        _, video_b, scene_b, _ = world["b"]
        r = await http.post("/api/requests", headers=as_key(world["alice"]),
                            json=self.image_request(PROJECT_B, video_b, scene_b))
        assert r.status_code == 404

    async def test_other_users_scene_under_own_project_is_refused(self, http, world):
        _, video_a, _, _ = world["a"]
        _, _, scene_b, _ = world["b"]
        r = await http.post("/api/requests/batch", headers=as_key(world["alice"]),
                            json={"requests": [self.image_request(PROJECT_A, video_a, scene_b)]})
        assert r.status_code == 404
        assert await crud.list_requests() == []

    async def test_other_users_character_is_refused(self, http, world):
        _, _, _, char_b = world["b"]
        r = await http.post("/api/requests", headers=as_key(world["alice"]), json={
            "type": "GENERATE_CHARACTER_IMAGE", "project_id": PROJECT_A, "character_id": char_b["id"]})
        assert r.status_code == 404

    async def test_request_listing_is_scoped(self, http, world):
        _, video_a, scene_a, _ = world["a"]
        _, video_b, scene_b, _ = world["b"]
        await crud.create_request("GENERATE_IMAGE", project_id=PROJECT_A, video_id=video_a["id"], scene_id=scene_a["id"])
        other = await crud.create_request("GENERATE_IMAGE", project_id=PROJECT_B, video_id=video_b["id"], scene_id=scene_b["id"])
        key = as_key(world["alice"])
        assert {r["project_id"] for r in (await http.get("/api/requests", headers=key)).json()} == {PROJECT_A}
        assert {r["project_id"] for r in (await http.get("/api/requests/pending", headers=key)).json()} == {PROJECT_A}
        assert (await http.get(f"/api/requests/batch-status?project_id={PROJECT_B}", headers=key)).json()["total"] == 0
        assert (await http.get(f"/api/requests/{other['id']}", headers=key)).status_code == 404


# ─── Creating a project ──────────────────────────────────────

class TestProjectCreate:
    async def test_ungranted_flow_project_is_refused(self, http, world):
        r = await http.post("/api/projects", headers=as_key(world["alice"]),
                            json={"name": "Stolen", "flow_project_id": PROJECT_B})
        assert r.status_code == 403

    async def test_no_unused_grant_asks_for_one(self, http, world):
        r = await http.post("/api/projects", headers=as_key(world["alice"]), json={"name": "Another"})
        assert r.status_code == 400
        assert "flow_project_id" in r.json()["detail"]

    async def test_single_unused_grant_is_picked(self, http, world, monkeypatch):
        await http.post(f"/api/admin/users/{world['alice_id']}/projects", headers=as_key(ADMIN_KEY),
                        json={"project_id": PROJECT_A2})
        seen = {}

        async def fake_granted(requested):
            seen["picked"] = await original(requested)
            return seen["picked"]

        from agent.api import projects
        original = projects._granted_flow_project
        monkeypatch.setattr(projects, "_granted_flow_project", fake_granted)
        # The extension isn't connected here, so creation stops right after the grant is resolved.
        r = await http.post("/api/projects", headers=as_key(world["alice"]), json={"name": "Second"})
        assert r.status_code == 503
        assert seen["picked"] == PROJECT_A2


# ─── Server-wide settings ────────────────────────────────────

class TestAdminOnly:
    @pytest.mark.parametrize("method,path,body", [
        ("PATCH", "/api/models", {"default_image_model": "X"}),
        ("PATCH", "/api/providers", {"active": "claude"}),
        ("POST", "/api/materials", {"id": "mine", "name": "Mine", "style_instruction": "flat pastel shapes"}),
        ("POST", "/api/flow/generate-image", {"prompt": "p", "project_id": PROJECT_A}),
        ("POST", "/api/flow/upload-image", {"file_path": ".env", "project_id": PROJECT_A}),
        ("GET", "/api/flow/credits", None),
        ("POST", "/api/tts/templates", {"name": "v", "text": "hello", "instruct": "calm"}),
    ])
    async def test_users_get_403(self, http, world, method, path, body):
        r = await http.request(method, path, headers=as_key(world["alice"]), json=body)
        assert r.status_code == 403, r.text

    async def test_models_and_providers_stay_readable(self, http, world):
        key = as_key(world["alice"])
        assert (await http.get("/api/models", headers=key)).status_code == 200
        assert (await http.get("/api/materials", headers=key)).status_code == 200

    async def test_flow_status_hides_the_server_project(self, http, world, monkeypatch):
        from agent.api import flow
        monkeypatch.setattr(flow, "FLOW_PROJECT_ID", PROJECT_B)
        r = await http.get("/api/flow/status", headers=as_key(world["alice"]))
        assert r.json()["flow_project_id"] == PROJECT_A

    async def test_tts_output_must_be_in_own_project(self, http, world):
        r = await http.post("/api/tts/generate", headers=as_key(world["alice"]),
                            json={"text": "hi", "output_path": "output/bravo/tts/x.wav"})
        assert r.status_code == 403


# ─── Active project ──────────────────────────────────────────

class TestActiveProject:
    async def test_each_user_has_their_own(self, http, world):
        assert (await http.put("/api/active-project", headers=as_key(world["alice"]),
                               json={"project_id": PROJECT_A})).status_code == 200
        assert (await http.put("/api/active-project", headers=as_key(world["alice"]),
                               json={"project_id": PROJECT_B})).status_code == 404
        bob = (await http.get("/api/active-project", headers=as_key(world["bob"]))).json()
        assert bob["project_id"] == PROJECT_B
        alice = (await http.get("/api/active-project", headers=as_key(world["alice"]))).json()
        assert (alice["project_id"], alice["source"]) == (PROJECT_A, "explicit")

    async def test_admin_entry_keeps_its_old_shape(self, http, world, db):
        await http.put("/api/active-project", headers=as_key(ADMIN_KEY), json={"project_id": PROJECT_B})
        await http.put("/api/active-project", headers=as_key(world["alice"]), json={"project_id": PROJECT_A})
        state = json.loads((db / "active_project.json").read_text())
        assert state["project_id"] == PROJECT_B
        assert state["users"][world["alice_id"]] == {"project_id": PROJECT_A}


# ─── Extension callback + dashboard events ───────────────────

class TestLocalOnly:
    async def test_proxied_callback_is_refused(self, http):
        r = await http.post("/api/ext/callback", json={"id": "x"}, headers={
            "X-Forwarded-For": "203.0.113.9", "X-Callback-Secret": agent_main._CALLBACK_SECRET})
        assert r.status_code == 403

    async def test_callback_without_the_secret_is_refused(self, http):
        r = await http.post("/api/ext/callback", json={"id": "x"}, headers={"X-Callback-Secret": "guess"})
        assert r.status_code == 403

    async def test_local_callback_with_secret_needs_no_key(self, http):
        r = await http.post("/api/ext/callback", json={"id": "x"}, headers={"X-Callback-Secret": agent_main._CALLBACK_SECRET})
        assert r.status_code == 200

    async def test_dashboard_events_are_filtered(self, world):
        _, video_a, scene_a, _ = world["a"]
        _, video_b, scene_b, _ = world["b"]
        mine = await crud.create_request("GENERATE_IMAGE", project_id=PROJECT_A, video_id=video_a["id"], scene_id=scene_a["id"])
        theirs = await crud.create_request("GENERATE_IMAGE", project_id=PROJECT_B, video_id=video_b["id"], scene_id=scene_b["id"])

        def event(kind, data):
            return json.dumps({"type": kind, "data": data})

        allowed = {PROJECT_A}
        assert await _event_visible(event("request_update", {"id": mine["id"]}), allowed)
        assert not await _event_visible(event("request_update", {"id": theirs["id"]}), allowed)
        assert await _event_visible(event("worker_tick", {}), allowed)
        assert not await _event_visible(event("something_new", {}), allowed)


# ─── CLI ─────────────────────────────────────────────────────

def test_cli_creates_user_and_prints_key_once(tmp_path, monkeypatch, capsys):
    from agent import users
    monkeypatch.setattr(schema, "DB_PATH", tmp_path / "cli.db")
    assert users.main(["create", "carol", "--project", PROJECT_A]) == 0
    out = capsys.readouterr().out
    key = out.split("API key (shown once): ")[1].strip()
    assert key.startswith("fk_")
    assert users.main(["list"]) == 0
    listing = capsys.readouterr().out
    assert "carol" in listing and PROJECT_A in listing and key not in listing
    assert users.main(["create", "carol"]) == 1
    assert users.main(["grant", "carol", "not-a-uuid"]) == 1

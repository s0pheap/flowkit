"""Public skill installer (agent/api/install.py) and the built dashboard served at /."""
import re

import httpx
import pytest

from agent import config
from agent.api import install
from agent.main import app


@pytest.fixture
async def http(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://flowkit.example.com") as client:
        yield client


class TestInstaller:
    async def test_needs_no_key(self, http):
        for path in ("/install.sh", "/install.ps1", "/install/skills.json", "/install/skills/fk-status/SKILL.md"):
            assert (await http.get(path)).status_code == 200, path

    async def test_scripts_point_at_this_server(self, http):
        sh = (await http.get("/install.sh")).text
        ps1 = (await http.get("/install.ps1")).text
        assert 'BASE="https://flowkit.example.com"' in sh
        assert "$Base = 'https://flowkit.example.com'" in ps1
        for skill in install.REMOTE_SKILLS:
            assert skill in sh and f"'{skill}'" in ps1
        assert "__" not in sh and "__BASE__" not in ps1

    async def test_public_url_overrides_the_request_host(self, http, monkeypatch):
        monkeypatch.setattr(config, "PUBLIC_URL", "https://videos.example.org/")
        assert 'BASE="https://videos.example.org"' in (await http.get("/install.sh")).text

    async def test_skill_has_frontmatter(self, http):
        text = (await http.get("/install/skills/fk-gen-refs/SKILL.md")).text
        assert text.startswith("---\nname: fk-gen-refs\ndescription: \"Generate reference images")
        assert "\r" not in text

    async def test_only_remote_skills_are_offered(self, http):
        names = [s["name"] for s in (await http.get("/install/skills.json")).json()]
        assert names == list(install.REMOTE_SKILLS)
        assert (await http.get("/install/skills/fk-youtube-upload/SKILL.md")).status_code == 404
        assert (await http.get("/install/skills/..%2F.env/SKILL.md")).status_code == 404

    def test_remote_skills_never_hardcode_localhost(self):
        for name in install.REMOTE_SKILLS:
            body = install.render_skill(name)
            for line in body.splitlines():
                # An API call, not an error message that happens to quote the address.
                if re.search(r"curl\s[^|]*http://127\.0\.0\.1:8100", line):
                    pytest.fail(f"{name}: {line.strip()}")
            assert "meta.json" not in body, name


class TestDashboard:
    @pytest.fixture
    def dist(self, tmp_path, monkeypatch):
        (tmp_path / "assets").mkdir()
        (tmp_path / "index.html").write_text("<div id=root>", encoding="utf-8")
        (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")
        monkeypatch.setattr(config, "DASHBOARD_DIST", tmp_path)
        return tmp_path

    async def test_serves_index_and_client_routes(self, http, dist):
        for path in ("/", "/projects/abc", "/guide"):
            r = await http.get(path)
            assert r.status_code == 200 and "root" in r.text, path

    async def test_serves_assets(self, http, dist):
        assert (await http.get("/assets/app.js")).text == "console.log(1)"

    async def test_api_paths_stay_api(self, http, dist):
        assert (await http.get("/api/nope")).status_code == 401  # still behind the key check
        assert (await http.get("/health")).json()["status"] == "ok"

    async def test_no_path_traversal(self, http, dist):
        r = await http.get("/assets/..%2F..%2Fsecret.txt")
        assert "nope" not in r.text

    async def test_missing_build_is_404(self, http, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "DASHBOARD_DIST", tmp_path / "missing")
        assert (await http.get("/guide")).status_code == 404

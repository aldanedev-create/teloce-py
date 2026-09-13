"""Checks for the real Flask + Teloce GitHub-style example."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "github-clone-flask"


def _load_app_module():
    spec = importlib.util.spec_from_file_location("github_clone_example_app", EXAMPLE / "app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_github_clone_flask_api_and_admin(tmp_path: Path):
    module = _load_app_module()
    app = module.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "ADMIN_PASSWORD": "test-password",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.sqlite3'}",
        }
    )
    client = app.test_client()

    assert client.get("/api/health").get_json() == {"ok": True, "service": "forgehub"}
    listing = client.get("/api/repositories").get_json()
    assert listing["total"] == 3
    repository_id = listing["items"][0]["id"]
    detail = client.get(f"/api/repositories/{repository_id}").get_json()
    assert detail["issues"]

    response = client.post(
        f"/api/repositories/{repository_id}/issues",
        json={"title": "Test issue", "body": "Created through the public API."},
    )
    assert response.status_code == 201
    assert response.get_json()["title"] == "Test issue"
    assert client.get("/admin/").status_code == 302

    login = client.post(
        "/admin-login?next=/admin/",
        data={"password": "test-password", "next": "/admin/"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/admin/")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/repository/edit/?id=1").status_code == 200
    assert client.get("/admin/issue/new/").status_code == 200


def test_github_clone_build_generates_router_and_valid_components(tmp_path: Path):
    project = tmp_path / "github-clone-flask"
    shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("dist", "instance", "__pycache__"))
    completed = subprocess.run(
        [sys.executable, "build.py"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    router = project / "dist" / "static" / "js" / "router.js"
    app = project / "dist" / "static" / "js" / "App.js"
    assert router.exists()
    assert app.exists()
    assert "HomePage" in router.read_text(encoding="utf-8")
    assert "RepoPage" in router.read_text(encoding="utf-8")

    node = shutil.which("node")
    if node:
        for script in (project / "dist" / "static" / "js").rglob("*.js"):
            checked = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, check=False)
            assert checked.returncode == 0, f"{script}: {checked.stderr}"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is not installed")
def test_documented_example_is_listed():
    readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    assert "github-clone-flask" in readme

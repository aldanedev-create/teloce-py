"""Optional in-memory builds."""

import asyncio
import shutil
from pathlib import Path

import pytest
from werkzeug.test import Client

from teloce.build import build_project
from teloce.build.memory import MemoryBuild, build_in_memory

APP = "<template><p>{{ n }}</p></template>\n<script>\nexport default { data() { return { n: 1 }; } };\n</script>\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "static" / "js" / "App.vel").write_text(APP, encoding="utf-8")
    return tmp_path


def test_nothing_is_written_to_the_project(project):
    build = build_in_memory(project)
    assert not (project / "dist").exists()
    assert "static/js/App.js" in build.files and "manifest.json" in build.files
    assert build.manifest["version"]


def test_memory_and_disk_builds_are_identical(project, tmp_path_factory):
    disk = tmp_path_factory.mktemp("disk")
    build_project(project, out_dir=disk, options={"clean": True})
    on_disk = {p.relative_to(disk).as_posix(): p.read_bytes() for p in disk.rglob("*") if p.is_file()}
    in_memory = build_in_memory(project).files
    assert set(in_memory) == set(on_disk)
    # manifest.json carries a build timestamp; every other byte must match
    import json

    def without_timestamp(data):
        return {k: v for k, v in json.loads(data).items() if k != "timestamp"}

    assert without_timestamp(in_memory.pop("manifest.json")) == without_timestamp(on_disk.pop("manifest.json"))
    assert in_memory == on_disk


def test_a_broken_component_fails_the_build(project):
    (project / "static" / "js" / "Bad.vel").write_text("<template><p>{{ </template>", encoding="utf-8")
    with pytest.raises(RuntimeError):
        build_in_memory(project)


def test_wsgi_app_serves_known_files_only(project):
    client = Client(build_in_memory(project).wsgi_app("static"))
    response = client.get("/js/App.js")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/javascript")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/js/App.js", headers={"If-None-Match": response.headers["ETag"]}).status_code == 304
    assert client.head("/js/App.js").data == b""
    assert client.get("/nope.js").status_code == 404
    assert client.get("/../manifest.json").status_code == 404
    assert client.get("/%2e%2e/manifest.json").status_code == 404
    assert client.post("/js/App.js").status_code == 405


def run_asgi(app, path, method="GET", headers=()):
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    asyncio.run(app({"type": "http", "path": path, "method": method, "headers": list(headers)}, receive, send))
    return sent


def test_asgi_app_matches_the_wsgi_behavior(project):
    build = build_in_memory(project)
    app = build.asgi_app("static", max_age=3600)
    ok = run_asgi(app, "/js/App.js")
    assert ok[0]["status"] == 200 and ok[1]["body"] == build.files["static/js/App.js"]
    headers = dict(ok[0]["headers"])
    assert headers[b"cache-control"] == b"public, max-age=3600"
    assert run_asgi(app, "/js/App.js", headers=[(b"if-none-match", headers[b"etag"])])[0]["status"] == 304
    assert run_asgi(app, "/../manifest.json")[0]["status"] == 404
    assert run_asgi(app, "/js/App.js", method="POST")[0]["status"] == 405


def test_memory_build_is_a_plain_value_object():
    build = MemoryBuild({"manifest.json": b'{"version": 1}', "static/a.css": b"a{}"})
    assert build.manifest == {"version": 1} and build.read("static/a.css") == b"a{}" and build.read("x") is None

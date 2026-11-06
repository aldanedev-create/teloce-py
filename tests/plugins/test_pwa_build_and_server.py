"""PWA build output (manifest, placeholder icons) and the framework-agnostic file server."""
import asyncio
import json
import struct
import zlib
from pathlib import Path

import pytest

from teloce.build import build_project
from teloce.plugins.builtin import placeholder_icon
from teloce.plugins.pwa_server import PwaFiles


def build(tmp_path: Path, **pwa):
    js = tmp_path / "static" / "js"
    js.mkdir(parents=True, exist_ok=True)
    (js / "App.vel").write_text("<template><main>hi</main></template>\n<script>export default {}</script>\n")
    options = {"plugins": {"pwa": {"name": "Demo", **pwa}}, "public_path": "/static/"}
    options.update(pwa.pop("_options", {}))
    return build_project(str(tmp_path), str(tmp_path / "dist"), options=options)


def decode_png(data: bytes):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height, depth, color = struct.unpack(">IIBB", data[16:26])
    pos, idat = 8, b""
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        payload = data[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        assert crc == zlib.crc32(kind + payload) & 0xFFFFFFFF
        idat += payload if kind == b"IDAT" else b""
        pos += 12 + length
    raw = zlib.decompress(idat)
    return width, height, depth, color, raw


# ---------------------------------------------------------------- icons and manifest
def test_placeholder_icons_are_valid_pngs_of_the_right_size_and_color():
    for size in (192, 512):
        width, height, depth, color, raw = decode_png(placeholder_icon(size, (15, 23, 42)))
        assert (width, height, depth, color) == (size, size, 8, 6)
        assert len(raw) == size * (1 + size * 4)
        assert raw[1:5] == bytes((15, 23, 42, 255))  # corner pixel is the theme colour
        assert any(raw[1 + y * (1 + size * 4) + x * 4] > 200 for y in (size // 2,) for x in range(size))  # the mark


def test_icon_mark_stays_visible_on_light_theme_colors():
    _, _, _, _, raw = decode_png(placeholder_icon(192, (250, 250, 250)))
    centre = 96 * (1 + 192 * 4) + 1 + 96 * 4
    assert raw[centre] < 100  # dark mark on a light background


def test_default_build_is_installable_by_chrome_rules(tmp_path):
    result = build(tmp_path)
    manifest = json.loads((tmp_path / "dist/teloce-plugins/manifest.webmanifest").read_text())
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes and manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        file = tmp_path / "dist/teloce-plugins" / icon["src"]
        width, height, *_ = decode_png(file.read_bytes())
        assert f"{width}x{height}" == icon["sizes"] and icon["type"] == "image/png"
    assert any("placeholder" in warning for warning in result["plugins"]["warnings"])
    assert manifest["scope"] == "/" and manifest["start_url"] == "/"


def test_user_icons_are_kept_and_no_placeholders_or_warnings_are_added(tmp_path):
    icons = [{"src": "/static/i-192.png", "sizes": "192x192", "type": "image/png"}]
    result = build(tmp_path, icons=icons)
    manifest = json.loads((tmp_path / "dist/teloce-plugins/manifest.webmanifest").read_text())
    assert manifest["icons"] == icons
    assert not (tmp_path / "dist/teloce-plugins/icons").exists()
    assert "warnings" not in result["plugins"]


def test_registration_scope_defaults_to_the_manifest_scope(tmp_path):
    build(tmp_path, scope="/app/")
    index = (tmp_path / "dist/teloce-plugins/index.js").read_text()
    assert '"scope": "/app/"' in index
    build(tmp_path)
    assert '"scope": "/"' in (tmp_path / "dist/teloce-plugins/index.js").read_text()


def test_dev_builds_skip_the_worker_unless_explicitly_enabled(tmp_path):
    build(tmp_path, _options={"dev": True})
    assert '"enabled": false' in (tmp_path / "dist/teloce-plugins/index.js").read_text()
    build(tmp_path, enabled=True, _options={"dev": True})
    assert '"enabled": true' in (tmp_path / "dist/teloce-plugins/index.js").read_text()


def test_bootstrap_logs_registration_failures(tmp_path):
    build(tmp_path)
    assert "console.error(error)" in (tmp_path / "dist/teloce-plugins/index.js").read_text()


# ---------------------------------------------------------------- file server
@pytest.fixture()
def files(tmp_path):
    build(tmp_path, scope="/")
    (tmp_path / "secret.js").write_text("secret")
    (tmp_path / "dist/teloce-plugins/.hidden.js").write_text("x")
    return PwaFiles(tmp_path / "dist"), tmp_path


def headers(response):
    return {k.lower(): v for k, v in response.headers}


def test_worker_is_served_with_service_worker_allowed_and_no_cache(files):
    pwa, _ = files
    response = pwa.get("/sw.js")
    assert response.status == 200 and b"addEventListener" in response.body
    h = headers(response)
    assert h["service-worker-allowed"] == "/" and h["cache-control"] == "no-cache"
    assert h["content-type"].startswith("text/javascript") and h["x-content-type-options"] == "nosniff"


def test_other_files_have_correct_types_and_no_worker_header(files):
    pwa, _ = files
    cases = {"/manifest.webmanifest": "application/manifest+json", "/offline.html": "text/html",
             "/icons/icon-192.png": "image/png", "/index.js": "text/javascript", "/pwa.js": "text/javascript"}
    for path, ctype in cases.items():
        response = pwa.get(path)
        assert response.status == 200 and headers(response)["content-type"].startswith(ctype), path
        assert "service-worker-allowed" not in headers(response)
    assert pwa.get("/teloce-plugins/sw.js").status == 200  # the folder name in the URL is accepted too


def test_scope_comes_from_the_manifest_or_the_argument(tmp_path):
    build(tmp_path, scope="/app/")
    assert PwaFiles(tmp_path / "dist").scope == "/app/"
    assert headers(PwaFiles(tmp_path / "dist").get("/sw.js"))["service-worker-allowed"] == "/app/"
    assert PwaFiles(tmp_path / "dist", scope="/x/").scope == "/x/"
    assert PwaFiles(tmp_path / "nowhere").scope == "/"


def test_path_traversal_hidden_files_symlinks_and_unknown_types_are_refused(files):
    pwa, tmp_path = files
    outside = tmp_path / "outside.js"
    outside.write_text("nope")
    (tmp_path / "dist/teloce-plugins/link.js").symlink_to(outside)
    for path in ("/../secret.js", "/..%2Fsecret.js", "/icons/../../secret.js", "/.hidden.js", "/link.js",
                 "/sw.js.map", "/missing.js", "/", "", "/icons", "/\x00sw.js", "\\..\\secret.js", "/sw.js/../../secret.js"):
        assert pwa.get(path).status == 404, path


def test_only_get_and_head(files):
    pwa, _ = files
    assert pwa.get("/sw.js", "POST").status == 405 and headers(pwa.get("/sw.js", "DELETE"))["allow"] == "GET, HEAD"
    head = pwa.get("/sw.js", "HEAD")
    assert head.status == 200 and head.body == b"" and int(headers(head)["content-length"]) > 0


def test_wsgi_and_asgi_apps(files):
    pwa, _ = files
    captured = {}
    body = b"".join(pwa.wsgi_app({"PATH_INFO": "/sw.js", "REQUEST_METHOD": "GET"}, lambda s, h: captured.update(status=s, headers=dict(h))))
    assert captured["status"] == "200 OK" and captured["headers"]["Service-Worker-Allowed"] == "/" and b"fetch" in body

    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(pwa.asgi_app({"type": "http", "method": "GET", "path": "/static/teloce-plugins/sw.js", "root_path": "/static/teloce-plugins"}, receive, send))
    start = sent[0]
    assert start["status"] == 200 and (b"service-worker-allowed", b"/") in start["headers"] and b"fetch" in sent[1]["body"]


# ---------------------------------------------------------------- mounting in real frameworks
def test_flask_mounts_pwa_files_ahead_of_its_own_static_route(tmp_path):
    flask = pytest.importorskip("flask")
    from werkzeug.middleware.dispatcher import DispatcherMiddleware

    build(tmp_path)
    app = flask.Flask(__name__, static_folder=str(tmp_path / "dist"), static_url_path="/static")
    # The mount is checked before Flask's /static route, so the worker gets its headers.
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/static/teloce-plugins": PwaFiles(tmp_path / "dist").wsgi_app})
    client = app.test_client()
    worker = client.get("/static/teloce-plugins/sw.js")
    assert worker.status_code == 200 and worker.headers["Service-Worker-Allowed"] == "/"
    assert client.get("/static/static/js/App.js").status_code == 200       # everything else is still Flask's
    plain = client.get("/static/teloce-plugins/pwa.js")
    assert plain.status_code == 200 and plain.headers["Cache-Control"] == "no-cache"


def test_fastapi_mounts_pwa_files_before_the_static_mount(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.testclient import TestClient

    build(tmp_path)
    app = FastAPI()
    app.mount("/static/teloce-plugins", PwaFiles(tmp_path / "dist").asgi_app)   # first: more specific
    app.mount("/static", StaticFiles(directory=tmp_path / "dist"))
    client = TestClient(app)
    worker = client.get("/static/teloce-plugins/sw.js")
    assert worker.status_code == 200 and worker.headers["service-worker-allowed"] == "/"
    assert client.get("/static/static/js/App.js").status_code == 200
    # Mounted after the static mount, the generic handler would shadow it and the header would be lost:
    shadowed = FastAPI()
    shadowed.mount("/static", StaticFiles(directory=tmp_path / "dist"))
    shadowed.mount("/static/teloce-plugins", PwaFiles(tmp_path / "dist").asgi_app)
    assert "service-worker-allowed" not in TestClient(shadowed).get("/static/teloce-plugins/sw.js").headers

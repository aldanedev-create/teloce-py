"""Real-browser PWA test: installability, service worker registration, offline page and updates.

Runs only with ``TELOCE_BROWSER_TESTS=1`` and Playwright's Chromium, like the other browser tests.
"""
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from teloce.build import build_project
from teloce.plugins.pwa_server import PwaFiles

pytestmark = pytest.mark.skipif(
    os.getenv("TELOCE_BROWSER_TESTS") != "1", reason="set TELOCE_BROWSER_TESTS=1 to run browser tests"
)
sync_api = pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PWA test</title></head>
<body><h1 id="shell">app shell</h1>
<script type="module">
  window.__events = [];
  for (const name of ['teloce:pwa-error', 'teloce:pwa-update'])
    document.addEventListener(name, event => window.__events.push([name, String(event.detail?.message ?? '')]));
  import {installPlugins} from "/static/teloce-plugins/index.js";
  window.__plugins = await installPlugins();
  window.__ready = true;
</script></body></html>"""


def build(project: Path, name: str = "PWA Test", **pwa):
    app = project / "static" / "js"
    app.mkdir(parents=True, exist_ok=True)
    (app / "App.vel").write_text("<template><main>hi</main></template>\n<script>export default {}</script>\n")
    result = build_project(str(project), str(project / "dist"), options={
        "plugins": {"pwa": {"name": name, "short_name": "PWA", "scope": "/", "theme_color": "#0f172a", **pwa}},
        "public_path": "/static/",
    })
    assert result["failed"] == 0
    return result


def serve(dist: Path, *, with_pwa_files: bool):
    pwa = PwaFiles(dist) if with_pwa_files else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, ctype, headers=()):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/page2"):
                return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
            if pwa and path.startswith("/static/teloce-plugins/"):
                response = pwa.get(path[len("/static/teloce-plugins"):])
                headers = [(k, v) for k, v in response.headers if k not in ("Content-Type", "Content-Length")]
                return self.send(response.status, response.body, dict(response.headers).get("Content-Type", "text/plain"), headers)
            file = dist / path[len("/static/"):] if path.startswith("/static/") else None
            if file and file.is_file():
                ctype = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(str(file))[0] or "application/octet-stream"
                return self.send(200, file.read_bytes(), ctype)
            self.send(404, b"not found", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def open_page(playwright, origin):
    browser = playwright.chromium.launch(args=["--no-sandbox"])
    context = browser.new_context()
    page = context.new_page()
    page.goto(origin + "/", wait_until="load")
    page.wait_for_function("window.__ready === true", timeout=15000)
    return browser, context, page


def installability_errors(context, page):
    cdp = context.new_cdp_session(page)
    cdp.send("Page.enable")
    return [e["errorId"] for e in cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]]


def poll(page, script, timeout=15.0):
    """Re-run an async page script until it returns something truthy (evaluate awaits promises)."""
    import time

    deadline = time.time() + timeout
    while True:
        value = page.evaluate(script)
        if value:
            return value
        assert time.time() < deadline, f"timed out waiting for: {script}"
        page.wait_for_timeout(100)


def wait_active(page):
    poll(page, "async () => { const r = await navigator.serviceWorker.getRegistrations(); return r.length > 0 && r[0].active?.state === 'activated'; }")


def test_installable_and_registered_when_served_with_service_worker_headers(tmp_path):
    result = build(tmp_path)
    assert any("placeholder" in warning for warning in result["plugins"]["warnings"])
    server, origin = serve(tmp_path / "dist", with_pwa_files=True)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            wait_active(page)
            assert page.evaluate("document.querySelector('link[rel=manifest]')?.href").endswith("/teloce-plugins/manifest.webmanifest")
            assert page.evaluate("document.querySelector('meta[name=theme-color]')?.content") == "#0f172a"
            assert installability_errors(context, page) == []  # Chrome would offer "Install"
            registration = page.evaluate("navigator.serviceWorker.getRegistrations().then(r => ({scope: r[0].scope, script: r[0].active.scriptURL}))")
            assert registration["scope"] == origin + "/" and registration["script"].endswith("/teloce-plugins/sw.js")
            assert page.evaluate("window.__events") == []  # no bogus "update available" on first install
            browser.close()
    finally:
        server.shutdown()


def test_plain_static_host_reports_a_clear_actionable_error(tmp_path):
    build(tmp_path)
    server, origin = serve(tmp_path / "dist", with_pwa_files=False)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            events = page.evaluate("window.__events")
            assert events and events[0][0] == "teloce:pwa-error"
            assert "Service-Worker-Allowed" in events[0][1] and "pwa_server" in events[0][1]
            assert page.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.length)") == 0
            # The manifest is still linked, so the app is installable even without a worker.
            assert installability_errors(context, page) == []
            browser.close()
    finally:
        server.shutdown()


def test_offline_navigation_shows_the_offline_page(tmp_path):
    build(tmp_path)
    server, origin = serve(tmp_path / "dist", with_pwa_files=True)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            wait_active(page)
            # context.set_offline() does not reach a service worker's own requests, so take the
            # server away instead: the worker's fetch now fails exactly as it would offline.
            server.shutdown()
            server.server_close()
            page.goto(origin + "/page2", wait_until="load")
            content = page.content()
            assert "You are offline" in content and "PWA Test" in content
            assert page.evaluate("document.querySelector('#shell')") is None  # not the real page
            browser.close()
    finally:
        server.shutdown()


def test_update_flow_announces_only_real_updates_and_activates_explicitly(tmp_path):
    build(tmp_path, name="Version One")
    server, origin = serve(tmp_path / "dist", with_pwa_files=True)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            wait_active(page)
            page.reload(wait_until="load")                      # now a worker controls the page
            page.wait_for_function("window.__ready === true && navigator.serviceWorker.controller !== null")
            assert page.evaluate("window.__events") == []
            old_caches = page.evaluate("caches.keys()")
            build(tmp_path, name="Version Two")                 # deploy a new build
            page.evaluate("window.__plugins.pwa.then(p => p.checkForUpdate())")
            page.wait_for_function("window.__events.some(e => e[0] === 'teloce:pwa-update')", timeout=15000)
            assert page.evaluate("window.__plugins.pwa.then(p => p.updateAvailable)") is True
            page.evaluate("window.__plugins.pwa.then(p => p.activateUpdate())")  # explicit, never automatic
            poll(page, "async () => { const keys = await caches.keys(); return keys.length === 1 && keys[0] !== %r; }" % old_caches[0])
            assert page.evaluate("window.__plugins.pwa.then(p => p.updateAvailable)") is False
            browser.close()
    finally:
        server.shutdown()


def test_development_builds_do_not_register_unless_enabled(tmp_path):
    build(tmp_path)
    for options, expected in (({"dev": True}, "false"), ({"dev": True, "pwa_enabled": True}, "true")):
        pwa = {"name": "Dev", "scope": "/"}
        if options.get("pwa_enabled"):
            pwa["enabled"] = True
        build_project(str(tmp_path), str(tmp_path / "dist"), options={"plugins": {"pwa": pwa}, "public_path": "/static/", "dev": True})
        index = (tmp_path / "dist" / "teloce-plugins" / "index.js").read_text()
        assert f'"enabled": {expected}' in index


def test_a_missing_optional_asset_does_not_break_the_worker(tmp_path):
    build(tmp_path)
    (tmp_path / "dist" / "static" / "js" / "App.js").unlink()           # a precached app file goes missing
    server, origin = serve(tmp_path / "dist", with_pwa_files=True)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            wait_active(page)
            assert page.evaluate("window.__events") == []
            cached = page.evaluate("caches.keys().then(async keys => (await (await caches.open(keys[0])).keys()).map(r => new URL(r.url).pathname))")
            assert "/static/teloce-plugins/offline.html" in cached and "/static/teloce-plugins/pwa.js" in cached
            assert not any(path.endswith("App.js") for path in cached)
            browser.close()
    finally:
        server.shutdown()


def test_a_missing_offline_page_fails_loudly(tmp_path):
    build(tmp_path)
    (tmp_path / "dist" / "teloce-plugins" / "offline.html").unlink()    # the one required file
    server, origin = serve(tmp_path / "dist", with_pwa_files=True)
    try:
        with sync_api.sync_playwright() as playwright:
            browser, context, page = open_page(playwright, origin)
            poll(page, "window.__events.some(e => e[0] === 'teloce:pwa-error')")
            message = next(m for name, m in page.evaluate("window.__events") if name == "teloce:pwa-error")
            assert "failed to install" in message and "public_path" in message
            assert page.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.filter(x => x.active).length)") == 0
            browser.close()
    finally:
        server.shutdown()

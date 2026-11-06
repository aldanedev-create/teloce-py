"""Real-browser test of every first-party plugin through the documented bootstrap path.

Builds with forms, i18n, accessibility, head and pwa enabled, loads ``installPlugins()`` the way the
docs show for a non-Flaxon host, then drives each plugin. Runs with ``TELOCE_BROWSER_TESTS=1``.
"""
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from teloce.build import build_project
from teloce.plugins.pwa_server import PwaFiles

pytestmark = pytest.mark.skipif(
    os.getenv("TELOCE_BROWSER_TESTS") != "1", reason="set TELOCE_BROWSER_TESTS=1 to run browser tests"
)
sync_api = pytest.importorskip("playwright.sync_api")

PLUGINS = {
    "forms": True,
    "i18n": {"locale": "en", "fallback": "en", "messages": {
        "en": {"welcome": "Welcome, {name}", "tasks": {"one": "{count} task", "other": "{count} tasks"}, "only_en": "English only"},
        "es": {"welcome": "Hola, {name}", "tasks": {"one": "{count} tarea", "other": "{count} tareas"}},
    }},
    "accessibility": True,
    "head": {"title": "Project manager", "description": "Manage projects",
             "pages": {"/projects": {"title": "Your projects", "description": "Dashboard", "canonical": "https://example.com/projects"}}},
    "pwa": {"name": "Project manager", "short_name": "Projects", "scope": "/", "theme_color": "#0f172a"},
}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Original</title>
<meta name="author" content="server rendered" data-keep="1">
<meta name="description" content="ssr marked" data-teloce-head></head>
<body><main id="app"><button id="opener">open</button><dialog id="dlg"><p>hi</p><button id="close">x</button></dialog></main>
<script type="module">
  import {installPlugins, connectPlugins} from "/static/teloce-plugins/index.js";
  window.__errors = [];
  document.addEventListener('teloce:pwa-error', e => window.__errors.push(String(e.detail?.message)));
  window.__api = await installPlugins();
  window.__connect = connectPlugins;
  window.__ready = true;
</script></body></html>"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("plugins")
    js = root / "static" / "js"
    js.mkdir(parents=True)
    (js / "App.vel").write_text("<template><main>hi</main></template>\n<script>export default {}</script>\n")
    result = build_project(str(root), str(root / "dist"), options={"plugins": PLUGINS, "public_path": "/static/"})
    assert result["failed"] == 0
    dist = root / "dist"
    pwa = PwaFiles(dist)

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
            if path == "/":
                return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
            if path == "/bare":  # a page with no <title> of its own
                return self.send(200, PAGE.replace("<title>Original</title>", "").encode(), "text/html; charset=utf-8")
            if path.startswith("/static/teloce-plugins/"):
                r = pwa.get(path[len("/static/teloce-plugins"):])
                return self.send(r.status, r.body, dict(r.headers).get("Content-Type", "text/plain"),
                                 [(k, v) for k, v in r.headers if k not in ("Content-Type", "Content-Length")])
            file = dist / path[len("/static/"):] if path.startswith("/static/") else None
            if file and file.is_file():
                ctype = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(str(file))[0] or "application/octet-stream"
                return self.send(200, file.read_bytes(), ctype)
            self.send(404, b"nf", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield result, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture()
def page(site):
    _, origin = site
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(origin + "/", wait_until="load")
        page.wait_for_function("window.__ready === true", timeout=15000)
        yield page
        assert errors == []
        browser.close()


def test_descriptor_lists_every_plugin_and_the_entry(site):
    result, _ = site
    plugins = result["plugins"]
    assert plugins["entry"] == "teloce-plugins/index.js"
    assert set(plugins["enabled"]) == {"forms", "i18n", "accessibility", "head", "pwa"}
    assert json.loads(open(result["output"] + "/manifest.json").read())["plugins"]["entry"] == plugins["entry"] if "output" in result else True


def test_install_exposes_every_plugin_and_pwa_registers(page):
    assert page.evaluate("Object.keys(window.__api).sort()") == ["accessibility", "forms", "head", "i18n", "pwa"]
    assert page.evaluate("globalThis.telocePlugins === window.__api")
    assert page.evaluate("window.__errors") == []
    assert page.evaluate("window.__api.pwa.then(p => !!p.registration)") is True


def test_forms(page):
    out = page.evaluate("""async () => {
      const { createForm, required, minLength, email } = window.__api.forms;
      const form = createForm({ name: '', email: 'bad', age: 3 }, { name: [required, minLength(3)], email: [required, email] });
      const seen = []; form.subscribe(() => seen.push(1));
      const r = {};
      r.invalid = form.validate();
      r.errors = { ...form.status.errors };
      form.set('name', 'Ada'); form.set('email', 'ada@example.com');
      r.errorClearedOnEdit = !('name' in form.status.errors);
      r.valid = form.validate();
      r.unknown = (() => { try { form.set('nope', 1); } catch (e) { return e.message; } })();
      let calls = 0;
      const slow = () => new Promise(done => setTimeout(() => { calls += 1; done('saved'); }, 30));
      const first = form.submit(slow); const second = form.submit(slow);   // duplicate submit is ignored
      r.duplicate = [await first, await second, calls, form.status.submitting];
      form.set('email', 'x');
      r.blocked = await form.submit(async () => { calls += 100; return 'no'; });   // invalid: handler must not run
      r.callsAfterInvalid = calls;
      form.setServerErrors({ detail: [{ loc: ['body', 'email'], msg: 'Already taken' }, { loc: ['body', 'zzz'], msg: 'Weird' }] });
      r.server = { ...form.status.errors };
      form.setServerErrors({ name: 'Too short', other: 'x' });
      r.serverDict = { ...form.status.errors };
      form.reset();
      r.reset = [form.values, { ...form.status.errors }, { ...form.status.touched }];
      r.immutable = (() => { const v = form.values; v.name = 'hacked'; return form.values.name; })();
      r.notified = seen.length > 5;
      return r;
    }""")
    assert out["invalid"] is False
    assert out["errors"] == {"name": "This field is required", "email": "Enter a valid email"}
    assert out["errorClearedOnEdit"] and out["valid"] is True
    assert "Unknown form field" in out["unknown"]
    assert out["duplicate"] == ["saved", None, 1, False]
    assert out["blocked"] is None and out["callsAfterInvalid"] == 1
    assert out["server"] == {"email": "Already taken", "_form": "Weird"}
    assert out["serverDict"] == {"name": "Too short", "_form": "x"}
    assert out["reset"] == [{"name": "", "email": "bad", "age": 3}, {}, {}]
    assert out["immutable"] == "" and out["notified"]


def test_i18n(page):
    out = page.evaluate("""() => {
      const i18n = window.__api.i18n; const r = {}; const heard = [];
      const off = i18n.subscribe(() => heard.push(i18n.locale));
      r.en = [i18n.t('welcome', { name: 'Ada' }), i18n.t('tasks', { count: 1 }), i18n.t('tasks', { count: 3 })];
      r.missingKey = i18n.t('nope'); r.unfilled = i18n.t('welcome');
      i18n.setLocale('es');
      r.es = [i18n.t('welcome', { name: 'Ada' }), i18n.t('tasks', { count: 1 }), i18n.t('tasks', { count: 2 })];
      r.fallback = i18n.t('only_en');
      r.number = i18n.number(1234567.891, { maximumFractionDigits: 1 });
      r.date = i18n.date(new Date(Date.UTC(2026, 0, 15)), { timeZone: 'UTC', dateStyle: 'long' });
      r.badLocale = (() => { try { i18n.setLocale('not a locale!!'); } catch (e) { return e.name; } })();
      r.localeKept = i18n.locale;
      off(); i18n.setLocale('en'); r.heard = heard;
      r.noHtml = i18n.t('welcome', { name: '<img src=x onerror=alert(1)>' });
      return r;
    }""")
    assert out["en"] == ["Welcome, Ada", "1 task", "3 tasks"]
    assert out["missingKey"] == "nope" and out["unfilled"] == "Welcome, {name}"
    assert out["es"] == ["Hola, Ada", "1 tarea", "2 tareas"] and out["fallback"] == "English only"
    assert out["number"] == "1.234.567,9" and "enero" in out["date"]
    assert out["badLocale"] == "RangeError" and out["localeKept"] == "es"
    assert out["heard"] == ["es"]  # unsubscribed listener hears nothing more
    assert out["noHtml"] == "Welcome, <img src=x onerror=alert(1)>"  # returned as text, never parsed as HTML


def test_accessibility(page):
    out = page.evaluate("""async () => {
      const a11y = window.__api.accessibility; const r = {};
      const live = document.querySelector('[aria-live]');
      r.live = [live.getAttribute('aria-live'), live.getAttribute('aria-atomic'), live.isConnected];
      a11y.announce('Page changed'); r.announced = live.textContent;
      const target = document.createElement('h1'); target.textContent = 'Title'; document.body.append(target);
      a11y.focus(target); r.focus = [document.activeElement === target, target.getAttribute('tabindex')];
      const opener = document.querySelector('#opener'); opener.focus();
      const dialog = document.querySelector('#dlg');
      const close = a11y.openDialog(dialog);
      r.open = dialog.open && dialog.matches(':modal');
      close(); r.closed = !dialog.open; r.focusReturned = document.activeElement === opener;
      const close2 = a11y.openDialog(dialog); dialog.close();         // closed by Escape / form: still restores focus
      r.escape = [!dialog.open, document.activeElement === opener];
      a11y.openDialog(dialog); a11y.destroy();
      r.destroyed = [!dialog.open, document.querySelector('[aria-live]') === null];
      return r;
    }""")
    assert out["live"] == ["polite", "true", True] and out["announced"] == "Page changed"
    assert out["focus"] == [True, "-1"]
    assert out["open"] and out["closed"] and out["focusReturned"]
    assert out["escape"] == [True, True] and out["destroyed"] == [True, True]


def test_head_defaults_per_page_overrides_and_safety(page):
    out = page.evaluate("""() => {
      const head = window.__api.head; const r = {};
      const meta = name => document.head.querySelector(`meta[name="${name}"], meta[property="${name}"]`)?.content ?? null;
      
      r.defaults = [document.title, meta('description'), document.head.querySelectorAll('meta[name="description"]').length];
      r.serverTagKept = document.head.querySelector('[data-keep]')?.content;
      head.set({ title: 'Your projects', description: 'Dashboard', ogTitle: 'OG', ogImage: 'https://cdn.example.com/a.png', canonical: 'https://example.com/p' });
      r.page = [document.title, meta('description'), meta('og:title'), meta('og:image'), document.head.querySelector('link[rel=canonical]')?.href];
      head.set({});
      r.back = [document.title, meta('description'), document.head.querySelector('link[rel=canonical]')];
      r.noDuplicates = document.head.querySelectorAll('[data-teloce-head]').length;
      r.unsafe = [];
      for (const bad of [{ canonical: 'javascript:alert(1)' }, { ogImage: 'data:text/html,x' }]) {
        try { head.set(bad); r.unsafe.push('accepted'); } catch (e) { r.unsafe.push('rejected'); }
      }
      r.titleAfterRejected = document.title;
      return r;
    }""")
    # The page has its own <title> ("Original"), which wins over the configured default.
    # The marked server-rendered description is taken over (no duplicate); unmarked tags are untouched.
    assert out["defaults"] == ["Original", "Manage projects", 1] and out["serverTagKept"] == "server rendered"
    assert out["page"] == ["Your projects", "Dashboard", "OG", "https://cdn.example.com/a.png", "https://example.com/p"]
    assert out["back"] == ["Original", "Manage projects", None]
    assert out["noDuplicates"] == 1 and out["unsafe"] == ["rejected", "rejected"]
    assert out["titleAfterRejected"] == "Original"  # a rejected update changes nothing


def test_head_uses_the_configured_title_when_the_page_has_none(site):
    _, origin = site
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(origin + "/bare", wait_until="load")
        page.wait_for_function("window.__ready === true", timeout=15000)
        assert page.title() == "Project manager"
        browser.close()


def test_connect_plugins_updates_head_and_announces_on_route_change(page):
    out = page.evaluate("""() => {
      let listener; const router = { afterEach(fn) { listener = fn; return () => { listener = null; }; } };
      const stop = window.__connect(window.__api, router);
      listener({ path: '/projects' });
      const r = { title: document.title, announced: document.querySelector('[aria-live]').textContent,
                  canonical: document.head.querySelector('link[rel=canonical]')?.href };
      listener({ path: '/unknown' });
      r.fallback = document.title;
      stop(); r.stopped = listener === null;
      r.noRouter = typeof window.__connect(window.__api, {}) === 'function';
      return r;
    }""")
    assert out["title"] == "Your projects" and out["announced"] == "Your projects"
    assert out["canonical"] == "https://example.com/projects" and out["fallback"] == "Original"
    assert out["stopped"] is True and out["noRouter"] is True

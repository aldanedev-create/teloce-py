"""Directives bound before their children exist: late v-for steps and late <option> rows.

These run in a real browser, so they are skipped when Playwright or Chromium is not installed.
"""

import functools
import http.server
import threading
from pathlib import Path

import pytest

from teloce.build import build_project

sync_api = pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html><body><div id="app"></div>
<script type="module">import { mount } from "/static/js/App.js"; mount("#app");</script></body></html>"""

SCROLLY = """<template><main>
  <section id="stage" v-scrolly @step="active = $event.detail.name">
    <article v-for="item in items" :key="item.id" :data-v-step="item.name" tabindex="0">{{ item.name }}</article>
  </section>
  <p id="active">{{ active }}</p>
</main></template>
<script>
export default {
  data() { return { items: [], active: "" }; },
  mounted() { setTimeout(() => { this.items = [{ id: 1, name: "one" }, { id: 2, name: "two" }]; }, 50); }
};
</script>"""

SELECT = """<template><main>
  <select id="level" v-model="level">
    <option :value="-1">None</option>
    <option v-for="(row, i) in rows" :key="row" :value="i">{{ row }}</option>
  </select>
</main></template>
<script>
export default {
  data() { return { level: 2, rows: [] }; },
  mounted() { setTimeout(() => { this.rows = ["a", "b", "c", "d"]; }, 50); }
};
</script>"""


BARE_IMPORT = """<template><p id="kind">{{ kind }}</p></template>
<script>
import { http, action, createScope } from "teloce/runtime";
export default {
  data() { return { kind: "" }; },
  mounted() { this.kind = [typeof http.get, typeof action.call, typeof createScope].join(","); }
};
</script>"""


@pytest.fixture
def serve(tmp_path: Path):
    servers = []

    def start(component: str) -> str:
        (tmp_path / "static" / "js").mkdir(parents=True, exist_ok=True)
        (tmp_path / "static" / "js" / "App.vel").write_text(component, encoding="utf-8")
        build_project(tmp_path, options={"dev": True})
        (tmp_path / "dist" / "page.html").write_text(PAGE, encoding="utf-8")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "dist"))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/page.html"

    yield start
    for server in servers:
        server.shutdown()


@pytest.fixture
def page():
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # Chromium is not installed
            pytest.skip(f"Chromium is not available: {error}")
        yield browser.new_page()
        browser.close()


def test_scrolly_binds_steps_that_render_after_mount(serve, page):
    page.goto(serve(SCROLLY))
    page.wait_for_function("document.querySelector('#stage').dataset.teloceActiveStep === 'one'", timeout=3000)
    assert page.locator("#active").inner_text() == "one"


def test_select_model_picks_up_options_that_render_after_mount(serve, page):
    page.goto(serve(SELECT))
    page.wait_for_function("document.querySelector('#level').options.length === 5", timeout=3000)
    page.wait_for_function("document.querySelector('#level').selectedIndex === 3", timeout=3000)
    assert page.locator("#level").evaluate("s => s.options[s.selectedIndex].textContent.trim()") == "c"


def test_bare_teloce_runtime_import_works_in_the_browser(serve, page):
    page.goto(serve(BARE_IMPORT))
    page.wait_for_function("document.querySelector('#kind').textContent === 'function,function,function'", timeout=3000)

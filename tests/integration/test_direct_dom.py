import re
import shutil
import time
from pathlib import Path

import pytest

from teloce.build import build_project
from teloce.cli.server import start_dev_server
from tests.integration.test_browser_e2e import _chrome, _dump_dom


SOURCE = '''<template>
  <main>
    <h1 id="count">{{ count }}</h1>
    <p id="name">{{ user.name }}</p>
    <div id="tone" :class="theme">Stable</div>
    <button @click="increment">Increase</button>
  </main>
</template>
<script>
export default {
  data() { return { count: 0, user: { name: "Ada" }, theme: "calm" }; },
  methods: { increment() { this.count++; } }
};
</script>'''


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_direct_dom_updates_preserve_unaffected_nodes_and_bindings(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    (source_dir / "App.vel").write_text(SOURCE, encoding="utf-8")
    result = build_project(
        tmp_path,
        options={
            "dev": True,
            "source_maps": False,
            "shared_runtime": True,
            "direct_dom_updates": True,
        },
    )
    assert result["failed"] == 0, result["errors"]
    generated = (tmp_path / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")
    assert "direct: __directPlan.enabled" in generated
    assert "teloce-text:t0" in generated
    assert '"dependencies": ["count"]' in generated or '"dependencies": ["count"]' in generated.replace(" ", "")

    (tmp_path / "dist" / "index.html").write_text(
        '<div id="app"></div><script type="module">'
        'import { mount } from "/static/js/App.js"; const app = mount("#app"); '
        'setTimeout(() => { const count = document.querySelector("#count"); '
        'const name = document.querySelector("#name"); const tone = document.querySelector("#tone"); '
        'const countBefore = count; const nameBefore = name; app.state.user.name = "Grace"; '
        'app.state.theme = "bright"; app.state.count = 4; document.querySelector("button").click(); setTimeout(() => {'
        'document.title = [countBefore === document.querySelector("#count"), '
        'nameBefore === document.querySelector("#name"), document.querySelector("#count").textContent, '
        'document.querySelector("#name").textContent, document.querySelector("#tone").className].join(":");'
        '}, 80); }, 80);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        time.sleep(0.1)
        browser = _dump_dom(f"http://127.0.0.1:{server.server_port}/?no_hmr=1", 1600)
        assert browser.returncode == 0, browser.stderr
        title = re.search(r"<title>([^<]*)</title>", browser.stdout)
        assert title and title.group(1) == "true:true:5:Grace:bright"
    finally:
        server.shutdown()
        server.server_close()


def test_direct_dom_plan_falls_back_for_structural_templates(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    path = source_dir / "App.vel"
    path.write_text(
        '<template><ul><li v-for="item in items" :key="item.id">{{ item.name }}</li></ul></template>'
        '<script>export default { data() { return { items: [{ id: 1, name: "A" }] }; } };</script>',
        encoding="utf-8",
    )
    result = build_project(
        tmp_path,
        options={
            "dev": True,
            "source_maps": False,
            "shared_runtime": True,
            "direct_dom_updates": True,
        },
    )
    assert result["failed"] == 0, result["errors"]
    generated = (tmp_path / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")
    assert '"structural": true' in generated
    assert "<for" in generated


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_direct_dom_structural_fallback_preserves_keyed_identity(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    (source_dir / "App.vel").write_text(
        '<template><button @click="swap">Swap</button><ul>'
        '<li v-for="item in items" :key="item.id">{{ item.name }}</li>'
        '</ul></template>'
        '<script>export default { data() { return { items: [{id: "a", name: "A"}, {id: "b", name: "B"}] }; }, '
        'methods: { swap() { this.items = [this.items[1], this.items[0]]; } } };</script>',
        encoding="utf-8",
    )
    result = build_project(
        tmp_path,
        options={
            "dev": True,
            "source_maps": False,
            "shared_runtime": True,
            "direct_dom_updates": True,
        },
    )
    assert result["failed"] == 0, result["errors"]
    (tmp_path / "dist" / "index.html").write_text(
        '<div id="app"></div><script type="module">'
        'import { mount } from "/static/js/App.js"; mount("#app"); '
        'setTimeout(() => { const first = document.querySelector("li"); first.dataset.keep = "yes"; '
        'document.querySelector("button").click(); setTimeout(() => document.title = '
        'document.querySelectorAll("li")[1].dataset.keep + ":" + document.querySelector("ul").textContent, 70); }, 70);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        time.sleep(0.1)
        browser = _dump_dom(f"http://127.0.0.1:{server.server_port}/?no_hmr=1", 1500)
        assert browser.returncode == 0, browser.stderr
        assert "<title>yes:BA</title>" in browser.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_direct_dom_updates_preserve_imported_component_slots(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    (source_dir / "Child.vel").write_text(
        '<template><button @click="$emit(\'press\', $event)"><slot></slot></button></template>'
        '<script>export default {};</script>',
        encoding="utf-8",
    )
    (source_dir / "App.vel").write_text(
        '<template><Child @press="count++">Clicked {{ count }} times</Child></template>'
        '<script>import Child from "./Child.vel"; export default { components: { Child }, '
        'data() { return { count: 0 }; } };</script>',
        encoding="utf-8",
    )
    result = build_project(
        tmp_path,
        options={
            "dev": True,
            "source_maps": False,
            "shared_runtime": True,
            "direct_dom_updates": True,
        },
    )
    assert result["failed"] == 0, result["errors"]
    (tmp_path / "dist" / "index.html").write_text(
        '<div id="app"></div><script type="module">'
        'import { mount } from "/static/js/App.js"; mount("#app"); '
        'setTimeout(() => { document.querySelector("button").click(); '
        'setTimeout(() => document.title = document.querySelector("button").textContent, 100); }, 100);'
        '</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        time.sleep(0.1)
        browser = _dump_dom(f"http://127.0.0.1:{server.server_port}/?no_hmr=1", 1600)
        assert browser.returncode == 0, browser.stderr
        assert "<title>Clicked 1 times</title>" in browser.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_direct_dom_updates_computed_properties_and_model_bindings(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    (source_dir / "App.vel").write_text(
        '<template><input id="name" v-model="name"><p id="display">{{ displayName }}</p>'
        '<div id="meta" :title="name">Meta</div></template>'
        '<script>export default { data() { return { name: "Ada" }; }, '
        'computed: { displayName() { return this.name.toUpperCase(); } } };</script>',
        encoding="utf-8",
    )
    result = build_project(
        tmp_path,
        options={
            "dev": True,
            "source_maps": False,
            "shared_runtime": True,
            "direct_dom_updates": True,
        },
    )
    assert result["failed"] == 0, result["errors"]
    (tmp_path / "dist" / "index.html").write_text(
        '<div id="app"></div><script type="module">'
        'import { mount } from "/static/js/App.js"; mount("#app"); '
        'setTimeout(() => { const input = document.querySelector("#name"); const display = document.querySelector("#display"); '
        'input.value = "Grace"; input.dispatchEvent(new Event("input", { bubbles: true })); '
        'setTimeout(() => document.title = [display.textContent, document.querySelector("#meta").title, '
        'input === document.querySelector("#name")].join(":"), 80); }, 80);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        time.sleep(0.1)
        browser = _dump_dom(f"http://127.0.0.1:{server.server_port}/?no_hmr=1", 1600)
        assert browser.returncode == 0, browser.stderr
        title = re.search(r"<title>([^<]*)</title>", browser.stdout)
        assert title and title.group(1) == "GRACE:Grace:true"
    finally:
        server.shutdown()
        server.server_close()

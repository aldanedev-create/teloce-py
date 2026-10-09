"""Execute generated and optimized HTML components in a real browser."""
from pathlib import Path
import os
import pytest
from teloce.build import build_project
from teloce.cli.server import start_dev_server

pytestmark = pytest.mark.skipif(os.environ.get("TELOCE_BROWSER_TESTS") != "1", reason="Set TELOCE_BROWSER_TESTS=1 to run browser regressions")

SOURCE = '''<template><main>
<input id="editor" v-model="title"><p id="title">{{ title }}</p>
<p v-if="visible" id="conditional">{{ heading }}</p>
<ul><li v-for="item in items" :key="item.id"><input :value="item.name"><button @click="select(item.id); clicks++">{{ item.name }}</button></li></ul>
<p id="selected">{{ selected }}</p>
</main></template><script lang="ts">
export default { data() { return { title: "Hello", visible: true, message: "Welcome", selected: "", clicks: 0, items: [{id: "a", name: "Alpha"}, {id: "b", name: "Beta"}] }; }, computed: { heading() {return this.message;} }, methods: { select(id: string) { this.selected = id; } } };
</script><style scoped>main { color: navy; }</style>'''


@pytest.mark.parametrize('production', [False, True])
def test_regions_focus_events_cleanup_and_minifyjs(tmp_path: Path, production):
    playwright = pytest.importorskip('playwright.sync_api')
    source = tmp_path / 'static'; source.mkdir()
    (source / 'App.html').write_text(SOURCE)
    result = build_project(tmp_path, options={
        'dev': not production, 'production': production, 'html_mode': True,
        'direct_dom_updates': True, 'source_maps': production,
        'hash_assets': False, 'extract_css': False, 'minifier': 'minifyjs',
    })
    assert result['failed'] == 0
    (tmp_path / 'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/static/App.js"; window.app = mount("#app");</script>')
    server = start_dev_server('127.0.0.1', 0, tmp_path / 'dist', hmr=False)
    try:
        with playwright.sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1')
            page.wait_for_function('window.app && document.querySelectorAll("li").length === 2')
            page.evaluate('''() => {
              window.rows = Array.from(document.querySelectorAll('li'));
              window.conditional = document.querySelector('#conditional');
              window.patches = 0; const original = document.createElement.bind(document);
              document.createElement = (...args) => { if (args[0] === 'template') window.patches++; return original(...args); };
            }''')
            page.locator('#editor').fill('Typed')
            page.wait_for_function('document.querySelector("#title").textContent === "Typed"')
            assert page.evaluate('window.patches') == 0  # no structural patch for unrelated text input
            assert page.evaluate('window.conditional === document.querySelector("#conditional")')
            page.evaluate('window.app.state.visible = false')
            page.wait_for_function('!document.querySelector("#conditional")')
            assert page.evaluate('window.patches') == 1
            assert page.evaluate('window.rows[0] === document.querySelectorAll("li")[0]')
            page.evaluate('window.app.state.visible = true; window.app.state.message = "Changed"')
            page.wait_for_function('document.querySelector("#conditional")?.textContent === "Changed"')
            page.locator('li input').nth(1).focus()
            page.evaluate('document.activeElement.setSelectionRange(1, 3); window.focused = document.activeElement; window.app.state.items.reverse()')
            page.wait_for_function('document.querySelector("li button").textContent === "Beta"')
            assert page.evaluate('window.rows[1] === document.querySelectorAll("li")[0]')
            assert page.evaluate('document.activeElement === window.focused && document.activeElement.selectionStart === 1'), page.evaluate('({active:document.activeElement.outerHTML, focused:window.focused.outerHTML, start:window.focused.selectionStart, connected:window.focused.isConnected})')
            page.locator('li button').first.click()
            page.wait_for_function('document.querySelector("#selected").textContent === "b"')
            page.locator('li button').first.click()
            assert page.evaluate('window.app.state.clicks') == 2
            # Repeated region updates replace event scopes without retaining old rows.
            page.evaluate('window.app.state.items = [{id:"c", name:"Gamma"}]')
            page.wait_for_function('document.querySelectorAll("li").length === 1')
            page.locator('li button').click()
            page.wait_for_function('document.querySelector("#selected").textContent === "c"')
            page.evaluate('window.oldButton = document.querySelector("li button"); window.app.unmount(); window.oldButton.click()')
            assert page.locator('#app').inner_html() == ''
            assert page.evaluate('window.app.state.selected') == 'c'
            assert errors == []
            browser.close()
    finally:
        server.shutdown(); server.server_close()


def test_modular_signal_helpers_reuse_nodes_and_cancel_updates():
    playwright = pytest.importorskip('playwright.sync_api')
    runtime = Path(__file__).parents[2] / 'src/teloce/runtime'
    server = start_dev_server('127.0.0.1', 0, runtime, hmr=False)
    try:
        with playwright.sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page(); page.goto(f'http://127.0.0.1:{server.server_port}/')
            result = page.evaluate('''async () => {
              const {createSignal} = await import('/signals.js');
              const {createFor, createIf} = await import('/dom.js');
              const list = document.createElement('div'); document.body.append(list);
              const source = createSignal([{id:'a'},{id:'b'}]); let disposed = 0;
              const loop = createFor(list, source, item => {
                const node = document.createElement('input'); node.value = item.id;
                return {node, unmount() {disposed++;}};
              }, item => item.id);
              const old = Array.from(list.childNodes); old[1].focus(); old[1].setSelectionRange(0, 1);
              source.set([{id:'b'},{id:'a'}]); await Promise.resolve();
              const moved = list.firstChild === old[1] && document.activeElement === old[1] && old[1].selectionEnd === 1;
              source.set([{id:'b'}]); await Promise.resolve(); const removed = disposed === 1;
              source.set([{id:'c'}]); loop.unmount(); await Promise.resolve();
              const stopped = list.childNodes.length === 0 && disposed === 2;
              const host = document.createElement('div'); document.body.append(host);
              const condition = createSignal(true); let renders = 0;
              const section = createIf(host, condition, () => {renders++; return document.createElement('p');});
              condition.set(1); await Promise.resolve(); const preserved = renders === 1;
              condition.set(false); await Promise.resolve(); const hidden = !host.firstChild;
              condition.set(true); section.unmount(); await Promise.resolve();
              return {moved, removed, stopped, preserved, hidden, empty: !host.firstChild};
            }''')
            assert all(result.values()), result
            browser.close()
    finally:
        server.shutdown(); server.server_close()


def test_direct_checkbox_array_and_radio_models(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    source = tmp_path / 'static'; source.mkdir()
    (source / 'App.html').write_text('''<template><main>
<input id="check" type="checkbox" value="a" v-model="choices">
<input id="radio-a" type="radio" value="a" v-model="choice">
<input id="radio-b" type="radio" value="b" v-model="choice">
</main></template><script>export default {data(){return {choices: [], choice: "a"};}};</script>''')
    build_project(tmp_path, options={'dev': True, 'html_mode': True, 'direct_dom_updates': True, 'source_maps': False})
    (tmp_path / 'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/static/App.js";window.app=mount("#app");</script>')
    server = start_dev_server('127.0.0.1', 0, tmp_path / 'dist', hmr=False)
    try:
        with playwright.sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page(); page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('window.app')
            assert not page.locator('#check').is_checked()
            page.evaluate('app.state.choices = ["a"]; app.state.choice = "b"')
            page.wait_for_function('document.querySelector("#check").checked && document.querySelector("#radio-b").checked')
            assert not page.locator('#radio-a').is_checked()
            page.evaluate('app.state.choices = []')
            page.wait_for_function('!document.querySelector("#check").checked')
            browser.close()
    finally:
        server.shutdown(); server.server_close()

"""Native v-model state/DOM parity across direct, region and fallback rendering."""
import os
import pytest
from teloce.build.builder import Builder
from teloce.cli.server import start_dev_server

pytestmark = pytest.mark.skipif(os.environ.get("TELOCE_BROWSER_TESTS") != "1", reason="Set TELOCE_BROWSER_TESTS=1")

SOURCE = '''<template><main>
<input id="signal" v-model="label.value"><input id="flat" v-model="name"><textarea id="nested" v-model="user.name"></textarea>
<input id="trim" v-model.trim="trimmed"><input id="number" v-model.number="number">
<input id="lazy" v-model.lazy="lazy"><input id="unknown" value="keep" v-model="missing">
<input id="boolean" type="checkbox" v-model="checked">
<input id="check-a" type="checkbox" value="a" v-model="selected">
<input id="check-b" type="checkbox" value="b" v-model="selected">
<input id="radio-a" type="radio" value="a" v-model="choice">
<input id="radio-b" type="radio" value="b" v-model="choice">
<select id="single" v-model="choice"><option value="a">A</option><option value="b">B</option></select>
<select id="multiple" multiple v-model="selected"><option value="a">A</option><option value="b">B</option></select>
<p>{{ tick }}</p>STRUCTURE
</main></template><script>IMPORT
export default {COMPONENTS data(){return {label:signal('signal'),name:'start',user:{name:'nested'},trimmed:'hello',number:12,lazy:'old',checked:true,selected:['a'],choice:'b',open:true,tick:0,items:[{id:1,name:'one'},{id:2,name:'two'}]}}};
</script>'''


def settle(page):
    page.evaluate("new Promise(resolve => setTimeout(resolve, 30))")


@pytest.mark.parametrize("mode", ["direct", "fallback", "regions", "children-production"])
def test_model_state_sync_native_controls_modifiers_scope_and_composition(tmp_path, mode):
    from playwright.sync_api import sync_playwright
    structural = mode in {"regions", "children-production"}
    children = mode == "children-production"
    ui = tmp_path / "ui"
    ui.mkdir()
    structure = '<p v-if="open">Open</p><div v-for="item in items" :key="item.id"><input class="row" v-model="item.name"></div>' if structural else ''
    if children:
        (ui / "Child.html").write_text('<template><aside>Child</aside></template>')
        structure += '<Child />'
    (ui / "App.html").write_text(SOURCE.replace('STRUCTURE', structure).replace('IMPORT', 'import Child from "./Child.html";' if children else '').replace('COMPONENTS', 'components:{Child},' if children else ''))
    options = {"html_mode": True, "source_roots": ["ui"], "dev": not children, "mode": "production" if children else "development"}
    if mode == "fallback":
        options["direct_dom_updates"] = False
    result = Builder(options).build(tmp_path)
    assert not result['failed'], result['errors']
    (tmp_path / "dist/index.html").write_text('<div id="app"></div><script type="module">import {mount} from "/ui/App.js";window.app=mount("#app");</script>')
    server = start_dev_server('127.0.0.1', 0, tmp_path / 'dist', hmr=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=['--no-sandbox'])
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('window.app')
            assert page.locator('#signal').input_value() == 'signal'
            page.locator('#signal').fill('changed')
            settle(page)
            assert page.evaluate('app.state.label.value') == 'changed'
            assert page.locator('#flat').input_value() == 'start'
            assert page.locator('#nested').input_value() == 'nested'
            assert page.locator('#unknown').input_value() == 'keep'
            assert page.locator('#boolean').is_checked()
            assert page.locator('#check-a').is_checked()
            assert not page.locator('#check-b').is_checked()
            assert page.locator('#radio-b').is_checked()
            assert page.locator('#multiple').evaluate('el=>[...el.selectedOptions].map(o=>o.value)') == ['a']
            if structural:
                assert page.locator('.row').evaluate_all('els=>els.map(el=>el.value)') == ['one', 'two']
                page.locator('.row').first.fill('edited')
                page.evaluate('app.state.tick++')
                settle(page)
                assert page.locator('.row').first.input_value() == 'edited'
                page.evaluate("app.state.items.reverse();app.state.items[0].name='reset'")
                settle(page)
                assert page.locator('.row').evaluate_all('els=>els.map(el=>el.value)') == ['reset', 'edited']
            page.locator('#trim').fill('hello ')
            page.evaluate('app.state.tick++')
            settle(page)
            assert page.locator('#trim').input_value() == 'hello '
            assert page.evaluate('app.state.trimmed') == 'hello'
            page.locator('#number').fill('0012')
            settle(page)
            assert page.locator('#number').input_value() == '0012'
            assert page.evaluate('app.state.number') == 12
            page.locator('#lazy').fill('uncommitted')
            page.evaluate('app.state.tick++')
            settle(page)
            assert page.locator('#lazy').input_value() == 'uncommitted'
            assert page.evaluate('app.state.lazy') == 'old'
            page.locator('#lazy').dispatch_event('change')
            assert page.evaluate('app.state.lazy') == 'uncommitted'
            page.locator('#check-b').check()
            settle(page)
            assert page.evaluate('[...app.state.selected]') == ['a', 'b']
            page.locator('#multiple').select_option(['b'])
            settle(page)
            assert page.evaluate('[...app.state.selected]') == ['b']
            assert not page.locator('#check-a').is_checked()
            page.locator('#radio-a').check()
            settle(page)
            assert page.locator('#single').input_value() == 'a'
            page.locator('#flat').fill('caret')
            page.evaluate("window.retained=document.querySelector('#flat');retained.focus();retained.setSelectionRange(1,3);app.state.tick++")
            settle(page)
            assert page.evaluate("retained===document.querySelector('#flat') && retained.selectionStart===1 && retained.selectionEnd===3")
            page.locator('#flat').focus()
            page.evaluate("window.input=document.querySelector('#flat');input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));input.value='composing';input.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));app.state.name='server';app.state.tick++")
            settle(page)
            assert page.locator('#flat').input_value() == 'composing'
            assert page.evaluate('app.state.name') == 'server'
            page.evaluate("input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
            settle(page)
            assert page.evaluate('app.state.name') == 'composing'
            page.evaluate("app.state.label.value='';app.state.name='';app.state.user.name='';app.state.trimmed='';app.state.number=0;app.state.checked=false;app.state.selected=[];app.state.choice='';app.state.lazy='reset'")
            settle(page)
            assert [page.locator('#'+name).input_value() for name in ('signal','flat','nested','trim','number','lazy')] == ['', '', '', '', '0', 'reset']
            assert not page.locator('#boolean').is_checked()
            assert not page.locator('#radio-a').is_checked()
            assert page.locator('#multiple').evaluate('el=>el.selectedOptions.length') == 0
            assert not page.locator('#check-b').is_checked()
            page.evaluate("app.unmount();input.value='after';input.dispatchEvent(new CompositionEvent('compositionstart'));input.dispatchEvent(new CompositionEvent('compositionend'));input.dispatchEvent(new Event('input'))")
            assert page.evaluate('app.state.name') == ''
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

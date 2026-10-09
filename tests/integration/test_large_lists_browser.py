"""Large-list behavior under the default renderer and production bundler."""
import os
from pathlib import Path
import pytest
from teloce.build import build_project
from teloce.cli.server import start_dev_server

pytestmark = pytest.mark.skipif(os.environ.get('TELOCE_BROWSER_TESTS') != '1', reason='requires Playwright Chromium')

@pytest.mark.parametrize('production', [False, True])
def test_default_keyed_rows_minimize_moves_and_isolate_edits(tmp_path, production):
    from playwright.sync_api import sync_playwright
    source = tmp_path / 'static'; source.mkdir()
    (source / 'App.html').write_text('''<template><main><ul><li v-for="item in items" :key="item.id"><input :value="item.name"><span>{{ item.name }}</span><button @click="selected = item.id">Select</button></li></ul><p>{{ selected }}</p></main></template><script>export default {data(){return {items:Array.from({length:1000},(_,id)=>({id,name:'Row '+id})),selected:''}}};</script>''')
    result = build_project(tmp_path, options={'mode':'production' if production else 'development', 'dev':not production, 'html_mode':True, 'source_maps':production})
    assert result['failed'] == 0, result['errors']
    if production:
        assert result['bundler'] == 'minifyjs' and result['bundle_outputs']
    entry = result['bundle'] if production else 'static/App.js'
    (tmp_path / 'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/'+entry+'";window.app=mount("#app");</script>')
    server = start_dev_server('127.0.0.1', 0, tmp_path / 'dist', hmr=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=['--no-sandbox']); page = browser.new_page()
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.wait_for_function('window.app && document.querySelectorAll("li").length === 1000')
            measured = page.evaluate('''async () => {
              const rows = [...document.querySelectorAll('li')]; let moves=0, parses=0;
              const parent=rows[0].parentNode, insert=parent.insertBefore.bind(parent);
              parent.insertBefore=(...args)=>{moves++;return insert(...args)};
              const create=document.createElement.bind(document);
              document.createElement=(...args)=>{if(args[0]==='template')parses++;return create(...args)};
              rows[500].querySelector('input').focus();document.activeElement.setSelectionRange(1,3);
              app.state.items[500].name='Edited'; await Promise.resolve();
              const editParses=parses, editMoves=moves;
              const edited=rows[500].querySelector('span').textContent==='Edited';
              const unchanged=rows.every((node,index)=>node===document.querySelectorAll('li')[index]);
              moves=0;parses=0; const list=[...app.state.items];app.state.items=[list.at(-1),...list.slice(0,-1)];await Promise.resolve();
              const rotateMoves=moves, rotateParses=parses;
              const focused=document.activeElement===rows[500].querySelector('input') && document.activeElement.selectionStart===1;
              app.state.items.reverse();await Promise.resolve();
              const reversePreserved=[...document.querySelectorAll('li')].every(node=>rows.includes(node));
              app.state.items.splice(4,1); await Promise.resolve();
              app.state.items.push({id:1001,name:'New'});await Promise.resolve();
              const newButton=[...document.querySelectorAll('li')].at(-1).querySelector('button');newButton.click();await Promise.resolve();
              const selected=app.state.selected===1001;
              app.unmount();newButton.click();await Promise.resolve();
              return {editParses,editMoves,edited,unchanged,rotateMoves,rotateParses,focused,reversePreserved,selected,empty:!document.querySelector('li')};
            }''')
            assert measured['editParses'] == 1, measured
            assert measured['editMoves'] == 0, measured
            assert measured['rotateMoves'] == 1 and measured['rotateParses'] == 0, measured
            assert all(measured[k] for k in ['edited','unchanged','focused','reversePreserved','selected','empty']), measured
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown();server.server_close()


@pytest.mark.parametrize('production', [False, True])
def test_virtual_rows_reuse_visible_nodes_and_cancel_scroll(tmp_path, production):
    from playwright.sync_api import sync_playwright
    source=tmp_path/'static';source.mkdir()
    (source/'App.html').write_text('''<template><main><div v-virtual-for="item in items" :key="item.id" item-height="40" overscan="2" min-height="160"><input :value="item.name"><span>{{ item.name }}</span></div></main></template><script>export default {data(){return {items:Array.from({length:10000},(_,id)=>({id,name:'Row '+id}))}}};</script><style scoped>.teloce-virtual-list{height:160px;overflow:auto}.teloce-virtual-content>div{height:40px}</style>''')
    result=build_project(tmp_path,options={'mode':'production' if production else 'development','dev':not production,'html_mode':True,'source_maps':False});assert result['failed']==0,result['errors']
    entry=result['bundle'] if production else 'static/App.js'
    css_paths={path.relative_to(tmp_path/'dist').as_posix() for path in (tmp_path/'dist').rglob('*.css')}
    styles=''.join('<link rel="stylesheet" href="/'+path+'">' for path in sorted(css_paths))
    (tmp_path/'dist/index.html').write_text(styles+'<div id="app"></div><script type="module">import {mount} from "/'+entry+'";window.app=mount("#app");</script>')
    server=start_dev_server('127.0.0.1',0,tmp_path/'dist',hmr=False)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.wait_for_selector('.teloce-virtual-content input')
            page.evaluate('window.host=document.querySelector(".teloce-virtual-list");window.row=document.querySelector(".teloce-virtual-content>div");window.host.scrollTop=40;window.host.dispatchEvent(new Event("scroll"))')
            page.wait_for_timeout(60)
            assert page.evaluate('window.row === document.querySelector(".teloce-virtual-content>div")')
            assert page.locator('.teloce-virtual-content input').count() <= 8
            assert page.evaluate('window.host.clientHeight === 160')
            assert page.evaluate('window.row.getBoundingClientRect().height === 40')
            assert page.locator('.teloce-virtual-content input').nth(1).is_visible()
            page.evaluate('window.host.scrollTop=10000;window.host.dispatchEvent(new Event("scroll"));window.app.unmount()')
            page.wait_for_timeout(60)
            assert page.locator('#app').inner_html()==''
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown();server.server_close()


def test_cached_rows_refresh_shared_values_indexes_and_source_type(tmp_path):
    from playwright.sync_api import sync_playwright
    source=tmp_path/'static';source.mkdir()
    (source/'App.html').write_text('''<template><main :class="theme.color" :title="theme.color" :style="theme.styles"><ul><li v-for="item in items" :key="item.id"><span>{{ prefix }}:{{ index }}:{{ item.name }}</span><button @click="selected = item.id">Select</button></li></ul></main></template><script>export default {data(){return {items:[{id:'a',name:'A'},{id:'b',name:'B'}],prefix:'Old',selected:'',theme:{color:'blue',styles:{color:'blue'},other:0}}}};</script>''')
    result=build_project(tmp_path,options={'dev':True,'html_mode':True,'source_maps':False});assert result['failed']==0,result['errors']
    (tmp_path/'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/static/App.js";window.app=mount("#app");</script>')
    server=start_dev_server('127.0.0.1',0,tmp_path/'dist',hmr=False)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.wait_for_function('window.app')
            writes=page.evaluate("""async () => {
              const records=[];const observer=new MutationObserver(items=>records.push(...items));
              observer.observe(document.querySelector('main'),{attributes:true});
              app.state.theme.other++;await Promise.resolve();await Promise.resolve();
              observer.disconnect();return records.length;
            }""")
            assert writes == 0
            page.evaluate("window.app.state.prefix='New';window.app.state.items.reverse()")
            page.wait_for_function('document.querySelector("li span").textContent === "New:0:B"')
            page.evaluate("window.app.state.items={a:{id:'a',name:'A'}}")
            page.wait_for_function('document.querySelectorAll("li").length === 1')
            page.evaluate("window.app.state.items=[{id:'a',name:'A'},{id:'b',name:'B'}]")
            page.wait_for_function('document.querySelectorAll("li").length === 2')
            page.locator('li button').nth(1).click();assert page.evaluate('window.app.state.selected')=='b'
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()


def test_default_production_bundles_bootstrap_and_preserves_alias(tmp_path):
    from playwright.sync_api import sync_playwright
    js=tmp_path/'static/js';js.mkdir(parents=True)
    (js/'App.html').write_text('<template><h1>Bundled bootstrap</h1></template>')
    (js/'Lazy.js').write_text('export const value=42;')
    (js/'main.js').write_text('import {mount} from "./App.js";mount("#app");window.loadChunk=()=>import("./Lazy.js");')
    result=build_project(tmp_path,options={'mode':'production','html_mode':True,'source_maps':True})
    assert result['failed']==0,result['errors']
    assert 'main.' in result['bundle']
    assert any('/chunks/' in item['output'] for item in result['bundle_outputs'])
    alias=tmp_path/'dist/static/js/main.js';assert alias.is_file()
    assert 'export { default }' not in alias.read_text()
    (tmp_path/'dist/index.html').write_text('<div id="app"></div><script type="module" src="/static/js/main.js"></script>')
    server=start_dev_server('127.0.0.1',0,tmp_path/'dist',hmr=False)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.get_by_role('heading',name='Bundled bootstrap').wait_for()
            assert page.evaluate('window.loadChunk().then(module=>module.value)')==42
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()

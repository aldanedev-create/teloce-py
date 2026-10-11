"""Optional plugin assets and browser contracts."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from teloce.plugins.builtin import emit_plugins, normalize_plugins

ROOT = Path(__file__).parents[2]


def test_plugins_disabled_emit_nothing(tmp_path):
    results = {"files": [], "total_bytes": 0}
    assert emit_plugins(tmp_path, results, {}) is None
    assert not (tmp_path / 'teloce-plugins').exists()
    for invalid in (True, ['forms'], {'unknown': True}, {'forms': 1}):
        with pytest.raises(ValueError):
            normalize_plugins(invalid)


def test_selected_assets_and_pwa_safe_allowlist(tmp_path):
    (tmp_path / 'app.js').write_text('export default {}')
    results = {'files': [{'output': 'app.js'}], 'total_bytes': 0}
    selected = emit_plugins(tmp_path, results, {'plugins': {'forms': True, 'pwa': {'name': 'Tasks', 'workerURL': '/teloce-sw.js'}}, 'public_path': '/_flaxon/'})
    assert selected['enabled'] == ['forms', 'pwa']
    assert not (tmp_path / 'teloce-plugins/i18n.js').exists()
    worker = (tmp_path / 'teloce-plugins/sw.js').read_text()
    assert '/_flaxon/app.js' in worker
    assert '/api/' not in worker
    assert "request.method!=='GET'" in worker
    assert "url.search||!ASSETS.includes" in worker
    assert 'fetch(request).catch' in worker
    assert json.loads((tmp_path / 'teloce-plugins/manifest.webmanifest').read_text())['name'] == 'Tasks'
    assert emit_plugins(tmp_path, results, {'plugins': {'forms': False}}) is None
    assert not (tmp_path / 'teloce-plugins').exists()


@pytest.mark.parametrize("optimized", [False, True])
def test_plugin_runtime_contracts(tmp_path, optimized):
    if not shutil.which('node') or not (ROOT / 'node_modules/jsdom').exists():
        pytest.skip('Node and jsdom required')
    result = {'files': [], 'total_bytes': 0}
    from teloce.build.minifyjs import TeloceMinifyJSAdapter
    transform = (lambda source: TeloceMinifyJSAdapter().transform(source).code) if optimized else None
    emit_plugins(tmp_path, result, {'plugins': {name: True for name in ('forms','i18n','accessibility','head','pwa')}, 'dev': True}, transform)
    script = tmp_path / 'check.mjs'
    script.write_text(f"""
import assert from 'node:assert/strict';
import {{JSDOM}} from {json.dumps((ROOT / 'node_modules/jsdom/lib/api.js').as_uri())};
const dom = new JSDOM('<title>Server title</title><meta data-teloce-head name="description" content="old"><button id="before">Open</button><dialog></dialog>',{{url:'https://example.test/'}});
for (const key of ['window','document','location','HTMLElement','CustomEvent']) globalThis[key]=dom.window[key];
Object.defineProperty(globalThis,'navigator',{{value:dom.window.navigator,configurable:true}});
const {{installPlugins,connectPlugins}} = await import('./teloce-plugins/index.js');
const api=await installPlugins();assert.equal(await api.pwa,null);assert.equal(globalThis.telocePlugins,api);
const form=api.forms.createForm({{email:''}},{{email:[api.forms.required,api.forms.email]}});
let sends=0;await form.submit(async()=>sends++);assert.equal(sends,0);assert.equal(form.status.touched.email,true);
form.set('email','a@example.test');let release;const pending=form.submit(()=>new Promise(resolve=>release=resolve));await form.submit(async()=>sends++);assert.equal(sends,0);release(1);await pending;assert.equal(form.status.submitting,false);
form.setServerErrors({{detail:[{{loc:['body','email'],msg:'Already used'}}]}});assert.equal(form.status.errors.email,'Already used');
await assert.rejects(form.submit(async()=>{{throw Error('network')}}),/network/);assert.equal(form.status.submitting,false);
const {{createI18n}}=await import('./teloce-plugins/i18n.js');const tr=createI18n({{locale:'en',messages:{{en:{{tasks:{{one:'{{count}} task',other:'{{count}} tasks'}},hello:'Hi {{name}}'}}}}}});
assert.equal(tr.t('tasks',{{count:1}}),'1 task');assert.equal(tr.t('tasks',{{count:2}}),'2 tasks');assert.equal(tr.t('hello',{{name:'A'}}),'Hi A');assert.equal(tr.t('missing'),'missing');tr.setLocale('fr');assert.equal(tr.t('hello',{{name:'B'}}),'Hi B');assert.ok(tr.number(1234));assert.ok(tr.date(0));
api.head.set({{title:'Tasks',description:'Current',canonical:'/tasks'}});assert.equal(document.title,'Tasks');assert.equal(document.querySelectorAll('meta[name="description"]').length,1);assert.equal(document.querySelector('link[rel="canonical"]').href,'https://example.test/tasks');assert.throws(()=>api.head.set({{canonical:'javascript:alert(1)'}}));assert.equal(document.title,'Tasks');
const before=document.querySelector('button'),dialog=document.querySelector('dialog');before.focus();dialog.showModal=()=>{{dialog.open=true;dialog.focus()}};dialog.close=()=>{{dialog.open=false;dialog.dispatchEvent(new dom.window.Event('close'))}};const close=api.accessibility.openDialog(dialog);close();assert.equal(document.activeElement,before);
let hook;const disconnect=connectPlugins(api,{{afterEach(fn){{hook=fn;return()=>{{hook=null}}}}}});hook({{path:'/tasks'}});assert.ok(document.querySelector('[aria-live]').textContent);disconnect();assert.equal(hook,null);
const {{registerPwa}}=await import('./teloce-plugins/pwa.js');let activated=false,checks=0;
const registration=new dom.window.EventTarget();registration.waiting={{postMessage(message){{activated=message.type==='TELOCE_SKIP_WAITING'}}}};registration.installing=null;registration.update=async()=>{{checks++}};
Object.defineProperty(navigator,'serviceWorker',{{value:{{register:async(url,settings)=>{{assert.equal(url,'https://example.test/sw.js');assert.equal(settings.scope,'/');return registration}}}}}});
const pwa=await registerPwa({{workerURL:'https://example.test/sw.js',scope:'/'}});assert.equal(pwa.updateAvailable,true);pwa.activateUpdate();assert.equal(activated,true);await pwa.checkForUpdate();assert.equal(checks,1);pwa.destroy();
api.head.destroy();api.accessibility.destroy();assert.equal(document.querySelector('[aria-live]'),null);
""")
    process = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def test_real_build_includes_optional_manifest(tmp_path):
    from teloce.build import build_project
    source = tmp_path / 'ui'
    source.mkdir()
    (source / 'app.html').write_text('<template><h1>Hello</h1></template><script>export default {}</script>')
    result = build_project(tmp_path, tmp_path / 'dist', options={
        'source_roots': ['ui'], 'html_mode': True, 'plugins': {'forms': True, 'i18n': True, 'pwa': {'name': 'Built app'}},
        'minify': True, 'public_path': '/static/',
    })
    assert result['failed'] == 0
    manifest = json.loads((tmp_path / 'dist/manifest.json').read_text())
    assert manifest['plugins']['enabled'] == ['forms', 'i18n', 'pwa']
    assert (tmp_path / 'dist' / manifest['plugins']['entry']).is_file()
    for path in manifest['plugins']['assets']:
        assert (tmp_path / 'dist' / path).is_file()


def test_worker_only_intercepts_static_assets_and_offline_navigation(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node required')
    results = {'files': [], 'total_bytes': 0}
    emit_plugins(tmp_path, results, {'plugins': {'pwa': True}, 'public_path': '/static/'})
    worker = (tmp_path / 'teloce-plugins/sw.js').read_text()
    script = tmp_path / 'worker.mjs'
    script.write_text("""
import assert from 'node:assert/strict';
import vm from 'node:vm';
const handlers={};let response;
const self={location:{origin:'https://example.test'},addEventListener(name,handler){handlers[name]=handler}};
const caches={open:async()=>({match:async()=>new Response('asset')}),match:async()=>new Response('offline')};
""" + f"vm.runInNewContext({json.dumps(worker)}, {{self,caches,URL,Response,fetch:async()=>{{throw Error('offline')}}}});\n" + """
function request(path,method='GET',mode='cors') { response=undefined; handlers.fetch({request:{url:'https://example.test'+path,method,mode},respondWith(value){response=value}}); }
request('/api/tasks');assert.equal(response,undefined);
request('/admin');assert.equal(response,undefined);
request('/static/teloce-plugins/index.js','POST');assert.equal(response,undefined);
request('/static/teloce-plugins/index.js?private=true');assert.equal(response,undefined);
request('/static/teloce-plugins/index.js');assert.equal(await (await response).text(),'asset');
request('/projects','GET','navigate');assert.equal(await (await response).text(),'offline');
""")
    process = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr

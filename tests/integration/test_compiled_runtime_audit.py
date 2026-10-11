"""Compiled renderer behavior using the actual generated helpers and a DOM."""
from pathlib import Path
import shutil
import subprocess

import pytest
from teloce.compiler.generator import SAFE_EXPRESSION_RUNTIME, SHARED_DOM_RUNTIME
from teloce.compiler.compiler import compile

ROOT = Path(__file__).parents[2]
CASES = {
    'adapter-destroy-context': """
let disposed=false; globalThis.__teloceLiveAdapters={demo(){return {token:42,destroy(){assert.equal(this.token,42);disposed=true}}}};
const component=create({}, {template:'<div live="demo"></div>'}); component.mount(host());component.unmount();assert.equal(disposed,true);
""",

    'websocket-stale-callbacks': """
let socket; globalThis.WebSocket=class {constructor(){socket=this}close(){}};
const component=create({data:()=>({result:null})}, {template:'<div live="/socket" live-target="result"></div>'});
component.mount(host()); const oldMessage=socket.onmessage; const oldClose=socket.onclose; component.unmount();
oldMessage({data:'{"stale":true}'}); oldClose(); await settle(); assert.equal(component.state.result,null); assert.equal(timers.size,0);
""",
    'poll-body-after-cleanup': """
let resolve; globalThis.fetch=async()=>({ok:true,json:()=>new Promise(done=>{resolve=done})});
const component=create({data:()=>({result:null})}, {template:'<div poll="/api" poll-target="result"></div>'});
component.mount(host()); await settle(); component.unmount(); resolve({stale:true}); await settle(); assert.equal(component.state.result,null);
""",

    'before-mount-order': """
const target=host(); let children;
const component=create({data:()=>({count:0}),beforeMount(){children=target.children.length;this.count=4}}, {template:'<p>{{ count }}</p>'});
component.mount(target); assert.equal(children,0); assert.equal(target.textContent,'4'); component.unmount();
""",
    'svg-url-sanitization': """
const component=create({data:()=>({html:'<svg><a xlink:href="javascript:alert(1)">Bad</a></svg>'})},{template:'<div data-teloce-bind-html="html"></div>'});
const target=host(); component.mount(target); assert.equal(target.querySelector('a').getAttribute('xlink:href'),null);component.unmount();
""",

    'keyed-list': """
const component=generatedMount(host()); const root=document.querySelector('main');
const first=root.querySelectorAll('li')[0]; const second=root.querySelectorAll('li')[1];
component.state.items.reverse(); await settle(); assert.equal(root.querySelectorAll('li')[0],second); assert.equal(root.querySelectorAll('li')[1],first);
component.state.items[0].label='Changed'; await settle(); assert.equal(root.querySelectorAll('li')[0].textContent,'Changed');
component.unmount();
""",
    'model-reset': """
const component=generatedMount(host()); const input=document.querySelector('input'); assert.equal(input.value,'start');
input.value='typed'; input.dispatchEvent(new window.Event('input')); await settle(); assert.equal(component.state.name,'typed');
component.state.name=''; await settle(); assert.equal(input.value,''); component.unmount();
""",
    'hydration': """
const target=host(); target.innerHTML='<p>0</p>'; target.setAttribute('data-teloce-ssr','1');
const paragraph=target.firstChild; const component=create({data:()=>({count:0})},{template:'<p>{{ count }}</p>',hydrate:true});
component.mount(target); assert.equal(target.firstChild,paragraph); component.state.count=1; await settle(); assert.equal(target.textContent,'1'); component.unmount();
""",

    'direct-text': """
const component=create({data:()=>({count:0})}, {template:'<p><!--teloce-text:t0-->{{ count }}</p>',direct:true,directPlan:{enabled:true,bindings:[{id:'t0',kind:'text',name:'',expression:'count',dependencies:['count'],read:s=>s.count}]}});
const target=host(); component.mount(target); const text=target.querySelector('p').lastChild;
component.state.count=3; await settle(); assert.equal(target.textContent,'3'); assert.equal(target.querySelector('p').lastChild,text);
component.unmount();
""",
    'events-cleanup': """
const component=create({data:()=>({count:0})}, {template:'<button data-teloce-event-click="count++">Run</button>'});
const target=host(); component.mount(target); const button=target.querySelector('button'); button.click(); await settle(); assert.equal(component.state.count,1);
component.unmount(); button.click(); await settle(); assert.equal(component.state.count,1);
""",
    'child-cleanup-error': """
const errors=[]; const unsubscribe=onTeloceError(error=>errors.push(error));
const component=create({}, {template:'<child-widget></child-widget><button>left</button>',components:{'child-widget':{mount:()=>({unmount(){throw Error('child cleanup')}})}}});
const target=host(); component.mount(target); component.unmount(); assert.equal(target.children.length,0);
assert.ok(errors.some(error=>error.phase==='child:unmount')); unsubscribe();
""",
    'cleanup-report': """
const errors=[]; const unsubscribe=onTeloceError(error=>errors.push(error));
globalThis.__teloceLiveAdapters={demo(){return ()=>{throw Error('adapter cleanup')}}};
const component=create({}, {template:'<div live="demo"></div>'}); const target=host(); component.mount(target); component.unmount();
assert.equal(target.children.length,0); assert.ok(errors.some(error=>error.phase==='live:cleanup')); unsubscribe();
""",
    'diagnostic-isolation': """
const reports=[]; const stopThrow=onTeloceError(()=>{throw Error('reporter')}); const stopGood=onTeloceError(error=>reports.push(error));
reportTeloceError({message:'cross-realm',stack:'source stack'},{phase:'event'}); assert.equal(reports[0].message,'cross-realm');
stopThrow(); stopGood(); reportTeloceError(Error('later')); assert.equal(reports.length,1);
""",

    'forwarded-attributes': """
const component=create({}, {template:'<a data-teloce-bind-attrs="$attrs">Link</a>',props:{$attrs:{HREF:'javascript:alert(1)',onmouseover:'alert(1)',title:'safe'}}});
const target=host(); component.mount(target); const link=target.querySelector('a');
assert.equal(link.getAttribute('href'),null); assert.equal(link.getAttribute('onmouseover'),null); assert.equal(link.title,'safe');
component.unmount();
""",

    'remount': """
const component = create({data:()=>({count:0})}, {template:'<p>{{ count }}</p>'});
const first=host(), second=host(); component.mount(first); component.mount(second);
assert.equal(first.children.length,0); assert.equal(second.textContent,'0');
component.state.count=2; await settle(); assert.equal(second.textContent,'2');
component.unmount();
""",
    'invalid-remount': """
const component=create({}, {template:'<p>kept</p>'}); const target=host(); component.mount(target);
assert.throws(()=>component.mount('#missing'), /not found/);
component.unmount(); assert.equal(target.children.length,0);
""",
    'hmr-before-mount': """
const component=create({}, {moduleUrl:'unused.html'});
assert.equal(globalThis.__teloce_hmr_instances.get('unused.html')?.size ?? 0,0);
component.unmount();
""",
    'lazy-retry': """
let loads=0; const lazy=__teloceLazy(async()=>{if(++loads===1)throw Error('offline');return {mount(t){t.textContent='ready';return {unmount(){t.replaceChildren()}}}}});
const target=host(); lazy.mount(target); await settle(); lazy.mount(target); await settle();
assert.equal(loads,2); assert.equal(target.textContent,'ready'); lazy.unmount();
""",
    'lazy-stale-handle': """
let stops=0; const lazy=__teloceLazy(()=>({mount(t){t.textContent='ready';return {unmount(){stops++;t.replaceChildren()}}}}));
const first=host(),second=host(); const old=lazy.mount(first); await settle();
const current=lazy.mount(second); await settle(); assert.equal(stops,1); assert.equal(first.textContent,'');
old.unmount(); assert.equal(second.textContent,'ready'); current.unmount(); assert.equal(stops,2);
""",
    'poll-after-cleanup': """
let resolve; globalThis.fetch=()=>new Promise(done=>{resolve=done});
const component=create({data:()=>({result:null})},{template:'<div poll="/api" poll-target="result"></div>'});
component.mount(host()); component.unmount(); resolve({ok:true,json:async()=>({secret:'stale'})}); await settle();
assert.equal(component.state.result,null); assert.equal(timers.size,0);
""",
    'poll-visibility': """
let resolve; let requests=0; globalThis.fetch=()=>{requests++;return new Promise(done=>{resolve=done})};
const component=create({}, {template:'<div poll="/api"></div>'}); component.mount(host());
document.dispatchEvent(new window.Event('visibilitychange')); document.dispatchEvent(new window.Event('visibilitychange'));
assert.equal(requests,1); resolve({ok:true,json:async()=>({})}); await settle(); assert.equal(timers.size,1);
document.dispatchEvent(new window.Event('visibilitychange')); assert.equal(requests,2); assert.equal(timers.size,0);
component.unmount();
""",
    'live-after-cleanup': """
let apply; globalThis.__teloceLiveAdapters={demo(callback){apply=callback;return ()=>{}}};
const component=create({data:()=>({result:null})}, {template:'<div live="demo" live-target="result"></div>'});
component.mount(host()); component.unmount(); apply({stale:true}); await settle(); assert.equal(component.state.result,null);
""",
    'live-visibility': """
let starts=0,stops=0; globalThis.__teloceLiveAdapters={demo(){starts++;return ()=>{stops++}}};
const component=create({}, {template:'<div live="demo"></div>'}); component.mount(host());
document.dispatchEvent(new window.Event('visibilitychange')); document.dispatchEvent(new window.Event('visibilitychange'));
assert.equal(starts,1); component.unmount(); assert.equal(stops,1);
""",
}


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('scenario', CASES)
def test_compiled_runtime_audit(tmp_path: Path, scenario: str, optimized: bool):
    jsdom = ROOT / 'node_modules/jsdom/lib/api.js'
    if not shutil.which('node') or not jsdom.exists():
        pytest.skip('Run npm ci for the Node DOM regression dependencies')
    runtime = tmp_path / 'compiled.mjs'
    source = SAFE_EXPRESSION_RUNTIME + SHARED_DOM_RUNTIME + (ROOT / 'src/teloce/runtime/compiled.js').read_text()
    if optimized:
        from minifyjs import Options
        from teloce.build import TeloceMinifyJSAdapter
        source = TeloceMinifyJSAdapter(Options(compress=True, mangle=True, format='esm')).transform(source, source_name='compiled.js').code
    runtime.write_text(source, encoding='utf-8')
    generated_import = ''
    sources = {
        'keyed-list': '<template><ul><li v-for="item in items" :key="item.id">{{ item.label }}</li></ul></template><script>export default {data(){return {items:[{id:1,label:"One"},{id:2,label:"Two"}]}}}</script>',
        'model-reset': '<template><div><input v-model="name"><p v-if="open">Open</p></div></template><script>export default {data(){return {name:"start",open:true}}}</script>',
    }
    if scenario in sources:
        result = compile(sources[scenario], 'Audit.html', shared_runtime_import=runtime.as_uri(), direct_dom_updates=True)
        assert result['success'], result['diagnostics']
        generated = tmp_path / 'component.mjs'
        generated.write_text(result['code'], encoding='utf-8')
        generated_import = f"import {{ mount as generatedMount }} from {generated.as_uri()!r};\n"
    script = tmp_path / 'audit.mjs' 
    script.write_text(
        "import assert from 'node:assert/strict';\n"
        f"import {{JSDOM}} from {jsdom.as_uri()!r};\n"
        f"import {{__teloceCreateCompiledComponent as create,__teloceLazy,onTeloceError,reportTeloceError}} from {runtime.as_uri()!r};\n"
        + generated_import + "const dom=new JSDOM('<!doctype html><body></body>',{url:'https://example.test/',pretendToBeVisual:true});\n"
        "for(const name of ['window','document','location','CustomEvent','Node','HTMLElement','getComputedStyle']) globalThis[name]=dom.window[name];\n"
        "const timers=new Map(); let nextTimer=0; globalThis.setTimeout=fn=>{timers.set(++nextTimer,fn);return nextTimer}; globalThis.clearTimeout=id=>timers.delete(id);\n"
        "function host(){const element=document.createElement('main');document.body.append(element);return element}\n"
        "async function settle(){for(let i=0;i<12;i++)await Promise.resolve()}\n"
        + CASES[scenario] + "\ndom.window.close();\n", encoding='utf-8',
    )
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr

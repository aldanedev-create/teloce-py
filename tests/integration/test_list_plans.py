"""Default switches and conservative row-plan boundaries."""
from pathlib import Path
import shutil
import subprocess
import pytest
from teloce.compiler.compiler import Compiler
from teloce.compiler.generator import SHARED_DOM_RUNTIME
from teloce.build.builder import Builder
from teloce.project.configuration import ProjectConfiguration


def test_defaults_and_explicit_compatibility_switches():
    compiler=Compiler({'shared_runtime_import':'./runtime.js'})
    source='<template><p>{{ title }}</p></template><script>export default {data(){return {title:"Hello"}}};</script>'
    assert compiler.compile(source)['direct_plan']['enabled']
    assert not Compiler({'direct_dom_updates':False}).compile(source)['direct_plan']['enabled']
    with Builder({'mode':'production'}) as builder:
        assert builder.options['direct_dom_updates'] and builder.options['bundle']
        assert builder.options['bundler']=='minifyjs' and builder.options['minify']
    with Builder({'mode':'production','bundle':False,'direct_dom_updates':False}) as builder:
        assert not builder.options['bundle'] and not builder.options['direct_dom_updates']
    config = ProjectConfiguration(); config.load()
    assert config.get_build_config()['direct_dom_updates']

@pytest.mark.parametrize('body,cached', [
    ('<span>{{ item.name }}</span>', True),
    ('<span>{{ format(item.name) }}</span>', False),
    ('<span v-if="item.visible">{{ item.name }}</span>', False),
    ('<span>{{ index }}</span>', True),
])
def test_row_cache_has_conservative_dependency_boundaries(body,cached):
    source='<template><ul><li v-for="item in items" :key="item.id">'+body+'</li></ul></template><script>export default {data(){return {items:[]}},methods:{format(value){return value}}};</script>'
    result=Compiler({'shared_runtime_import':'./runtime.js'}).compile(source)
    assert result['success'],result['diagnostics']
    assert bool(result['direct_plan']['regions'][0].get('rows')) is cached


def test_shared_proxy_identity_and_lis_optimal_length(tmp_path):
    if not shutil.which('node'):pytest.skip('Node unavailable')
    script=tmp_path/'check.mjs'
    script.write_text(SHARED_DOM_RUNTIME+'''
import assert from 'node:assert/strict';
let updates=0;const state=__createReactive({items:[{id:1},{id:2}]},()=>updates++);
const original=state.items[0];
for(let i=0;i<100;i++){state.items=[...state.items].reverse();}
assert.equal(state.items[0],original);original.id=3;assert.equal(state.items[0].id,3);
assert.equal(updates,101);
const fixtures=[[],[-1,-1],[4,0,1,2,3],[3,2,1,0],[0,2,1,3]];
for(let length=1;length<40;length++){
 const values=Array.from({length},(_,i)=>i).sort(()=>Math.random()-.5);fixtures.push(values);
}
for(const values of fixtures){
 const indices=[...__lis(values)].sort((a,b)=>a-b), sequence=indices.map(i=>values[i]);
 assert.ok(sequence.every((v,i)=>v>=0 && (!i || sequence[i-1]<v)));
 const lengths=values.map(()=>0);let optimum=0;
 values.forEach((v,i)=>{if(v<0)return;lengths[i]=1;for(let j=0;j<i;j++)if(values[j]>=0 && values[j]<v)lengths[i]=Math.max(lengths[i],lengths[j]+1);optimum=Math.max(optimum,lengths[i]);});
 assert.equal(indices.length,optimum);
}
''')
    result=subprocess.run(['node',str(script)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_empty_production_build_does_not_bundle_runtime_only(tmp_path):
    with Builder({'mode':'production'}) as builder:
        result=builder.build(tmp_path)
    assert result['failed'] == 0, result['errors']
    assert not result.get('bundle')

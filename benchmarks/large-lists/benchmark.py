"""Repeatable keyed-list microtask timings and DOM-work counts (not paint time)."""
import argparse
import json
import statistics
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from teloce.build import build_project
from teloce.cli.server import start_dev_server

SOURCE = '''<template><main><ul><li v-for="item in items" :key="item.id"><span>{{ item.name }}</span></li></ul></main></template><script>export default {data(){return {items:Array.from({length:SIZE},(_,id)=>({id,name:'Row '+id}))}}};</script>'''

def run(output, iterations_override=None, warmup=1):
    report={'sizes':{}, 'measurement':'microtask completion; excludes paint', 'warmup_updates':warmup}
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as pw:
        root=Path(directory);source=root/'static';source.mkdir()
        browser=pw.chromium.launch(args=['--no-sandbox']);report['browser']=browser.version
        for size in (100,1000,10000):
            (source/'App.html').write_text(SOURCE.replace('SIZE',str(size)))
            result=build_project(root,options={'dev':True,'html_mode':True,'direct_dom_updates':True,'clean':True,'source_maps':False})
            assert not result['failed'],result['errors']
            (root/'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/static/App.js";window.app=mount("#app");</script>')
            server=start_dev_server('127.0.0.1',0,root/'dist',hmr=False)
            try:
                page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.wait_for_function(f'window.app && document.querySelectorAll("li").length === {size}')
                data=page.evaluate('''async config=>{
                  const {size,warmup}=config;
                  const parent=document.querySelector('ul'),insert=parent.insertBefore.bind(parent),create=document.createElement.bind(document);
                  let moves=0,parses=0,serial=0;
                  parent.insertBefore=(...args)=>{moves++;return insert(...args)};
                  document.createElement=(...args)=>{if(args[0]==='template')parses++;return create(...args)};
                  const once=async kind=>{
                    if(kind==='edit') app.state.items[Math.floor(size/2)].name='Edit '+serial++;
                    if(kind==='rotate'){const rows=[...app.state.items];app.state.items=[rows.at(-1),...rows.slice(0,-1)]}
                    if(kind==='reverse')app.state.items=[...app.state.items].reverse();
                    if(kind==='insert-delete'){app.state.items.push({id:size+serial++,name:'New'});app.state.items.shift()}
                    await Promise.resolve();
                  };
                  const result={};const iterations=config.iterations || (size===10000?2:10);
                  for(const kind of ['edit','rotate','reverse','insert-delete']){
                    for(let i=0;i<warmup;i++)await once(kind);const samples=[];
                    for(let batch=0;batch<5;batch++){
                      moves=0;parses=0;const start=performance.now();
                      for(let i=0;i<iterations;i++)await once(kind);
                      samples.push({milliseconds:performance.now()-start,moves,parses,iterations});
                    }
                    result[kind]=samples;
                  }
                  return result;
                }''',{'size':size,'iterations':iterations_override,'warmup':warmup})
                assert not errors,errors
                report['sizes'][str(size)]={kind:{'median_ms':statistics.median(s['milliseconds'] for s in samples),'samples':samples} for kind,samples in data.items()}
                page.close()
            finally:
                server.shutdown();server.server_close()
        browser.close()
    Path(output).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--iterations',type=int);parser.add_argument('--warmup',type=int,default=1);args=parser.parse_args();run(args.output,args.iterations,args.warmup)

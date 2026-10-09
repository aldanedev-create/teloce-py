"""Production startup and requested JS bytes, five fresh pages per list size."""
import argparse,json,statistics,tempfile,gzip
from pathlib import Path
from playwright.sync_api import sync_playwright
from teloce.build import build_project
from teloce.cli.server import start_dev_server
from benchmark import SOURCE

def run(output):
    report={}
    with tempfile.TemporaryDirectory() as directory,sync_playwright() as pw:
        root=Path(directory);source=root/'static';source.mkdir()
        browser=pw.chromium.launch(args=['--no-sandbox'])
        for size in (100,1000,10000):
            (source/'App.html').write_text(SOURCE.replace('SIZE',str(size)))
            result=build_project(root,options={'mode':'production','html_mode':True,'direct_dom_updates':True,'source_maps':False,'spa':False})
            assert not result['failed'],result['errors']
            entry=result.get('bundle') or 'static/App.js'
            (root/'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/'+entry+'";const start=performance.now();window.app=mount("#app");window.mountMilliseconds=performance.now()-start;</script>')
            server=start_dev_server('127.0.0.1',0,root/'dist',hmr=False)
            try:
                samples=[];assets={}
                for sample in range(5):
                    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('response',lambda response:assets.setdefault(response.url.split('?')[0].split(f':{server.server_port}/')[-1],response.body()) if response.url.split('?')[0].endswith('.js') else None)
                    page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1');page.wait_for_function('window.mountMilliseconds !== undefined')
                    samples.append(page.evaluate('window.mountMilliseconds'));assert not errors,errors;page.close()
                report[str(size)]={'mount_samples_ms':samples,'median_mount_ms':statistics.median(samples),'requested_js_files':sorted(assets),'requested_js_bytes':sum(len(v) for v in assets.values()),'requested_js_gzip_bytes':sum(len(gzip.compress(v,mtime=0)) for v in assets.values()),'bundler':result.get('bundler')}
            finally:server.shutdown();server.server_close()
        browser.close()
    Path(output).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)

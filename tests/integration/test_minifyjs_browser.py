"""Real production output checked in Chromium; opt in via TELOCE_BROWSER_TESTS."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from threading import Thread

import pytest
from teloce.build import build_project
from teloce.router.compiler import RouterCompiler
from teloce.router.generator import RouterGenerator

pytestmark = pytest.mark.skipif(os.environ.get('TELOCE_BROWSER_TESTS') != '1',
                               reason='set TELOCE_BROWSER_TESTS=1 with Chromium installed')


@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('hashed', [False, True])
@pytest.mark.parametrize('splitting', [False, True])
def test_native_production_browser(tmp_path, shared, hashed, splitting):
    from playwright.sync_api import sync_playwright
    project = tmp_path / 'project';project.mkdir()
    js = project / 'static/js';js.mkdir(parents=True)
    (js / 'App.vel').write_text((Path(__file__).parents[2] / 'examples/flask/static/js/App.vel').read_text())
    (js / 'Lazy.js').write_text('export const value = "lazy-loaded";')
    config = RouterCompiler().compile({'routes':[
        {'path':'/','component':'Home'}, {'path':'/users/:id','component':'User'}]})
    (js / 'Router.js').write_text('const Home = "Home", User = "User";\n' + RouterGenerator().generate(config))
    (js / 'main.js').write_text('import {mount} from "./App.js"; import router from "./Router.js"; mount("#app"); window.testRouter=router; window.loadChunk=()=>import("./Lazy.js");')
    output = tmp_path / 'dist'
    result = build_project(project, output, options={'mode':'production',
        'bundle':True, 'bundle_entry':'static/js/main.js', 'shared_runtime':shared,
        'hash_assets':hashed, 'code_splitting':splitting, 'source_maps':True,
        'spa':False, 'report':'report.json'})
    (output / 'test.html').write_text('<div id="app"></div><script type="module" src="' + result['bundle'] + '"></script>')
    server = ThreadingHTTPServer(('127.0.0.1',0), partial(SimpleHTTPRequestHandler, directory=str(output)))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page()
                errors=[];page.on('pageerror', lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/test.html')
                page.get_by_role('heading', name='Flask dashboard').wait_for()
                page.get_by_role('button', name='Sign out', exact=True).click()
                page.get_by_role('button', name='Sign in', exact=True).wait_for()
                assert page.locator('.status').count() == 0
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.locator('.status').wait_for()
                assert page.evaluate('async () => { await window.testRouter.push("/users/42?tab=posts"); return [window.testRouter.params().id, window.testRouter.query().tab]; }') == ['42','posts']
                assert page.evaluate('async () => (await window.loadChunk()).value') == 'lazy-loaded'
                assert not errors,errors
                assert any('/chunks/' in item['output'] for item in result['bundle_outputs']) == splitting
            finally:
                browser.close()
    finally:
        server.shutdown();server.server_close()

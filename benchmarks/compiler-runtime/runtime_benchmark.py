"""Browser update workloads, run identically against each source checkout."""
import argparse
import json
import statistics
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from teloce.build import build_project
from teloce.cli.server import start_dev_server

SOURCES = {
    'counter': '<main><p>{{ count }}</p>' + ''.join(f'<span>{{{{ value{i} }}}}</span>' for i in range(200)) + '</main>',
    'typing': '<main><input id="editor" v-model="title"><p>{{ title }}</p></main>',
    'conditional': '<main><p>{{ count }}</p><div v-if="visible"><span>{{ title }}</span></div></main>',
    'keyed_list': '<main><p>{{ count }}</p><ul><li v-for="item in items" :key="item.id">{{ item.name }}</li></ul></main>',
}


def run(output):
    report = {}
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as manager:
        root = Path(directory); source = root / 'static'; source.mkdir()
        browser = manager.chromium.launch(headless=True, args=['--no-sandbox'])
        report['browser'] = browser.version
        for name, template in SOURCES.items():
            data = {'count': 0, 'title': 'Hello', 'visible': True,
                    'items': [{'id': str(i), 'name': f'Item {i}'} for i in range(1000)] if name == 'keyed_list' else [],
                    **({f'value{i}': i for i in range(200)} if name == 'counter' else {})}
            (source / 'App.html').write_text('<template>' + template + '</template><script>export default {data() {return ' + json.dumps(data) + ';}};</script>')
            build_project(root, options={'dev': True, 'html_mode': True, 'source_maps': False,
                                         'direct_dom_updates': True, 'clean': True})
            (root / 'dist/index.html').write_text('<div id="app"></div><script type="module">import {mount} from "/static/App.js";window.app=mount("#app");</script>')
            server = start_dev_server('127.0.0.1', 0, root / 'dist', hmr=False)
            try:
                page = browser.new_page(); errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/?no_hmr=1'); page.wait_for_function('window.app')
                result = page.evaluate('''async name => {
                  const measure = async (iterations, kind) => {
                    let patches = 0; const original = document.createElement.bind(document);
                    document.createElement = (...args) => { if(args[0] === 'template') patches++; return original(...args); };
                    const start = performance.now();
                    for (let i=0; i<iterations; i++) {
                      if(name === 'typing') {const input = document.querySelector('#editor');input.value = String(i);input.dispatchEvent(new Event('input'));}
                      else if(name === 'conditional' && kind === 'structure') app.state.visible = !app.state.visible;
                      else if(name === 'keyed_list' && kind === 'structure') app.state.items = [...app.state.items].reverse();
                      else app.state.count++;
                      await Promise.resolve();
                    }
                    const elapsed = performance.now()-start;
                    document.createElement = original;
                    return {milliseconds: elapsed, iterations, patches};
                  };
                  await measure(20, 'text');
                  const text = []; const structure = [];
                  for(let i=0;i<5;i++) text.push(await measure(name === 'keyed_list' ? 40 : 200, 'text'));
                  if(name === 'conditional' || name === 'keyed_list') for(let i=0;i<5;i++) structure.push(await measure(name==='keyed_list'?20:200,'structure'));
                  return {text, structure, count:app.state.count, rows:document.querySelectorAll('li').length};
                }''', name)
                assert not errors, errors
                if name == 'keyed_list': assert result['rows'] == 1000
                report[name] = result
                page.close()
            finally:
                server.shutdown(); server.server_close()
        browser.close()
    for name in SOURCES:
        result = report[name]
        result['median_ms'] = {kind: statistics.median(row['milliseconds'] for row in result[kind])
                               for kind in ('text', 'structure') if result[kind]}
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name:report[name]['median_ms'] for name in SOURCES}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    run(parser.parse_args().output)

"""Exercise standalone directive ownership and row scopes in a DOM runtime."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_standalone_directive_cleanup_and_scope(tmp_path):
    if not shutil.which('node') or not (ROOT / 'node_modules/jsdom').exists():
        pytest.skip('Node and jsdom required')
    script = tmp_path / 'directives.mjs'
    script.write_text(f"""
import assert from 'node:assert/strict';
import {{JSDOM}} from {json.dumps((ROOT / 'node_modules/jsdom/lib/api.js').as_uri())};
const dom = new JSDOM('<main><button @click="count++" v-mark.extra="count">Click</button><p v-for="item in items" v-row="item.name"></p></main>');
for (const key of ['window','document','CustomEvent','Node','HTMLElement']) globalThis[key] = dom.window[key];
await import({json.dumps((ROOT / 'src/teloce/runtime/standalone.js').as_uri())});
const log = [];
let destroyed = 0;
globalThis.teloce.use({{directives: {{
 mark: {{mounted(element, context) {{assert.deepEqual(context.modifiers, ['extra']); return {{id: 7, destroy() {{assert.equal(this.id, 7); destroyed++;}}}};}}}},
 row: {{mounted(element, context) {{log.push(context.value);}}}}
}}}});
const app = globalThis.teloce.createApp(document.querySelector('main'), {{count: 0, items: [{{name:'one'}}, {{name:'two'}}]}});
assert.deepEqual(log, ['one', 'two']);
const oldButton = document.querySelector('button');
app.state.count = 1;
assert.equal(destroyed, 1);
oldButton.click();
assert.equal(app.state.count, 1, 'detached listener must be removed');
app.unmount();
assert.equal(destroyed, 2);
app.unmount();
assert.equal(destroyed, 2);
""")
    result = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

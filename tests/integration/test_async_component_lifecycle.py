"""Regression checks for lazy component retries and remount cleanup."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which('node') is None, reason='Node is not installed')
@pytest.mark.parametrize('scenario', ['retry', 'retry-sync', 'remount', 'pending-unmount', 'pending-remount'])
def test_async_component_lifecycle(tmp_path: Path, scenario: str):
    runtime = Path(__file__).parents[2] / 'src/teloce/runtime/component.js'
    cases = {
        'pending-unmount': """
let resolve;
let mounts = 0;
const component = defineAsyncComponent(() => new Promise(done => { resolve = done; }));
const host = target(); const mounting = component.mount(host);
await Promise.resolve(); component.unmount();
resolve({ mounted() { mounts += 1; }, render: () => ({}) });
await mounting;
assert.equal(mounts, 0);
assert.equal(host.children.length, 0);
""",
        'pending-remount': """
let resolve; let loads = 0; let mounts = 0;
const component = defineAsyncComponent(() => { loads += 1; return new Promise(done => { resolve = done; }); });
const first = target(); const second = target();
const oldMount = component.mount(first);
await Promise.resolve();
const newMount = component.mount(second);
resolve({ mounted() { mounts += 1; }, render: () => ({}) });
await Promise.all([oldMount, newMount]);
assert.equal(loads, 1); assert.equal(mounts, 1);
assert.equal(first.children.length, 0); assert.equal(second.children.length, 1);
component.unmount();
""",
        'retry': """
let attempts = 0;
const component = defineAsyncComponent(async () => {
  if (++attempts === 1) throw new Error('temporary failure');
  return { render: () => ({}) };
});
await assert.rejects(component.mount(target()), /temporary failure/);
const recovered = target();
await component.mount(recovered);
assert.equal(attempts, 2);
assert.equal(recovered.children.length, 1);
component.unmount();
""",
        'remount': """
let unmounted = 0;
const component = defineAsyncComponent(async () => ({
  render: () => ({}), unmounted() { unmounted += 1; }
}));
const first = target(); const second = target();
await component.mount(first);
await component.mount(second);
assert.equal(unmounted, 1, 'old component lifecycle must be stopped');
assert.equal(first.children.length, 0, 'old mount target must be cleared');
assert.equal(second.children.length, 1);
component.unmount();
assert.equal(unmounted, 2);
""",
    }
    cases['retry-sync'] = cases['retry'].replace('async () =>', '() =>')
    script = tmp_path / 'async.mjs'
    script.write_text(
        "import assert from 'node:assert/strict';\n"
        f"import {{ defineAsyncComponent }} from {runtime.as_uri()!r};\n"
        "globalThis.document = { createComment: () => ({}) };\n"
        "function target() { return { children: [], replaceChildren(...nodes) { this.children = nodes; } }; }\n"
        + cases[scenario], encoding='utf-8',
    )
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

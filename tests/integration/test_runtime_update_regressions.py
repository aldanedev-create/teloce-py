"""Behavior regressions for queued effects and reactive collections."""
from pathlib import Path
import shutil
import subprocess
import pytest

RUNTIME = Path(__file__).parents[2] / 'src/teloce/runtime'


def run_js(tmp_path, source):
    if not shutil.which('node'):
        pytest.skip('Node is unavailable')
    script = tmp_path / 'check.mjs'
    script.write_text(f"import {{ reactive, createEffect, createSignal, batch }} from {(RUNTIME / 'signals.js').as_uri()!r};\n"
                      f"import {{ queueJob, flushJobs }} from {(RUNTIME / 'scheduler.js').as_uri()!r};\n"
                      "import assert from 'node:assert/strict';\n" + source)
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_array_growth_truncation_and_iteration(tmp_path):
    run_js(tmp_path, '''
const list = reactive([]); let length, keys, second;
createEffect(() => { length = list.length; });
createEffect(() => { keys = Object.keys(list).join(','); });
createEffect(() => { second = list[1]; });
list.push('a', 'b'); await Promise.resolve();
assert.equal(length, 2); assert.equal(keys, '0,1'); assert.equal(second, 'b');
list.length = 1; await Promise.resolve();
assert.equal(length, 1); assert.equal(keys, '0'); assert.equal(second, undefined);
list[4] = 'e'; await Promise.resolve(); assert.equal(length, 5);
list.splice(0, 1); await Promise.resolve(); assert.equal(length, 4);
''')


def test_objects_iteration_host_objects_and_proxy_identity(tmp_path):
    run_js(tmp_path, '''
const state = reactive({}); let keys, present;
createEffect(() => { keys = Object.keys(state).join(','); present = 'name' in state; });
state.name = 'Ada'; await Promise.resolve(); assert.equal(keys, 'name'); assert.equal(present, true);
delete state.name; await Promise.resolve(); assert.equal(keys, ''); assert.equal(present, false);
assert.equal(reactive(state), state);
const date = new Date(); assert.equal(reactive(date), date); assert.ok(reactive({date}).date.getTime());
''')


def test_scheduler_runs_later_jobs_and_reports_errors(tmp_path):
    run_js(tmp_path, '''
const seen = []; const first = new Error('first');
queueJob(() => { throw first; }); queueJob(() => seen.push('after'));
assert.throws(() => flushJobs(), error => error === first); assert.deepEqual(seen, ['after']);
queueJob(() => { throw new Error('a'); }); queueJob(() => { throw new Error('b'); });
assert.throws(() => flushJobs(), error => error instanceof AggregateError && error.errors.length === 2);
const nativeAggregateError = globalThis.AggregateError;
globalThis.AggregateError = undefined;
queueJob(() => { throw new Error('a'); }); queueJob(() => { throw new Error('b'); });
assert.throws(() => flushJobs(), error => error.errors.length === 2);
globalThis.AggregateError = nativeAggregateError;
await Promise.resolve();
''')


def test_subscription_value_batching_and_queued_cancellation(tmp_path):
    run_js(tmp_path, '''
const signal = createSignal(0); const seen = [];
const unsubscribe = signal.subscribe(value => seen.push(value));
batch(() => { signal.set(1); signal.set(2); }); await Promise.resolve();
assert.deepEqual(seen, [2]);
signal.set(3); unsubscribe(); await Promise.resolve(); assert.deepEqual(seen, [2]);
let context; const listener = { run(value) { context = this; seen.push(value); } };
signal.subscribe(listener); signal.set(4); await Promise.resolve();
assert.equal(context, listener); assert.deepEqual(seen, [2, 4]);
''')


def test_effect_stop_cancels_pending_execution(tmp_path):
    run_js(tmp_path, '''
const signal = createSignal(0); let calls = 0;
const effect = createEffect(() => { signal(); calls++; });
signal.set(1); effect.stop(); await Promise.resolve(); assert.equal(calls, 1);
''')

/** Runtime public API type regression fixtures. */
// This file is checked only; intentionally invalid calls are never executed.
import { createSignal, createEffect, createComputed, reactive, getValue, toSignal, untracked } from '../../src/teloce/runtime/signals.js';
import { queueJob, batch } from '../../src/teloce/runtime/scheduler.js';

const count = createSignal(1);
count.set(2);
count.value = 3;
count.update(value => value + 1);
count().toFixed();
count.peek().toFixed();
const unsubscribe = count.subscribe(value => value.toFixed());
unsubscribe();
const effect = createEffect(() => count());
effect.stop();
queueJob(effect.run);
createComputed(() => count() * 2).get().toFixed();
getValue(count).toFixed();
toSignal('hello').get().toUpperCase();
reactive({ name: 'Ada', completed: false }).name.toUpperCase();
batch(() => 42).toFixed();
untracked(() => 'hello').toUpperCase();

// @ts-expect-error Signals preserve their initial value type.
count.set('wrong');
// @ts-expect-error The .value API has the same type as the callable API.
count.value = 'wrong';
// @ts-expect-error Updaters must return the signal's value type.
count.update(value => String(value));
// @ts-expect-error Subscribers receive the signal's value type.
count.subscribe(value => value.toUpperCase());
// @ts-expect-error Jobs must be callable.
queueJob(42);
// @ts-expect-error Reactive objects preserve property names and value types.
reactive({ name: 'Ada' }).missing;
// @ts-expect-error Computed values preserve the callback's return type.
createComputed(() => 'hello').get().toFixed();

import { parseDelimited } from '../../src/teloce/runtime/data.js';
import { createDataTable } from '../../src/teloce/runtime/table.js';
import { createComponent } from '../../src/teloce/runtime/component.js';
import { batch as runtimeBatch } from '../../src/teloce/runtime/runtime.js';
parseDelimited('name\nAda', { headers: ['name'] });
runtimeBatch(() => 42).toFixed();
// @ts-expect-error CSV delimiters must be strings.
parseDelimited('name', { delimiter: 42 });
// @ts-expect-error Table pagination is numeric.
createDataTable(document.createElement('div'), { pageSize: 'ten' });
// @ts-expect-error Component render functions return DOM nodes.
createComponent({ render: () => 'not a node' });

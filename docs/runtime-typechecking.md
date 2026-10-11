# Runtime JavaScript type checking

The runtime remains JavaScript. JSDoc comments describe the types of signals,
effects, subscribers, dependency collections, scheduler jobs and lifecycle
callbacks. TypeScript checks these comments without emitting files or converting
sources to `.ts`.

## For contributors

```bash
npm ci --ignore-scripts
npm run typecheck
```

The lockfile pins the development checker. `tsconfig.runtime.json` enables
`allowJs`, `checkJs`, strict checking and `noEmit`. Editors can use the same
JSDoc comments for completion and inline errors.

```js
import { createSignal } from './src/teloce/runtime/signals.js';

const count = createSignal(0);
count.set(1);
count.value = 2;
// count.set('hello'); // Type error: this signal holds numbers.
```

## Current coverage

Every maintained `.js` file under `src/teloce/runtime/` is included: signals,
scheduler, lifecycle, components, compiled and standalone rendering, DOM helpers,
data, tables, props, slots, events, and re-export modules. New runtime files are
included automatically by the glob in `tsconfig.runtime.json`.

Contract fixtures under `tests/types/` check valid usage and intentionally invalid
examples. An unused `@ts-expect-error` fails the check, so negative examples also
verify that types have not silently become permissive.

`contracts.js` documents shared option types and intentional dynamic boundaries:
application state, evaluated expressions, plugin extensions, and renderer node
metadata. These boundaries still accept arbitrary values; checking does not make
user expressions or private DOM metadata fully type-safe. `compiler-globals.d.ts`
describes helpers prepended by the Python compiler; it emits no JavaScript and
does not check JavaScript source embedded in Python strings.

Browser and runtime behavior tests remain required. Types cannot prove correct
rendering, cleanup, focus handling or hydration.

## For application developers

No extra setup is required. `pip install teloce-py` continues to ship JavaScript
runtime files. Node and TypeScript are contributor/CI tools, not dependencies
for Python application users. Production compilation and MinifyJS optimization
are unchanged. This adds development checks, not a runtime speed improvement.

## Compiled renderer regression checks

Run `python -m pytest tests/integration/test_compiled_runtime_audit.py -q`
after `npm ci --ignore-scripts`. The pinned jsdom dependency is development-only.
The tests load the actual generated expression and DOM helpers with `compiled.js`,
and repeat checks after MinifyJS optimization. Generated HTML components also
exercise keyed lists and structural model bindings.

Checked areas include mount/remount ownership, lifecycle order, lazy imports,
HMR registration, polling, visibility changes, WebSocket and adapter cleanup,
direct text bindings, event removal, child cleanup failures, public diagnostics,
forwarded attribute safety, HTML URL sanitization, models and hydration.

Compiled contracts now describe binding/region plans, keyed row plans, props,
query descriptors, watchers, diagnostics and mounted children. Native sockets,
abort controllers and timers are typed independently of application state.

These DOM tests do not reproduce browser layout, IME or every hydration mismatch.
Chromium regressions remain a separate CI job. Application expressions and plugin
metadata retain explicit dynamic boundaries; passing type checks is not proof
that every runtime path is correct or that raw HTML is safe from every attack.

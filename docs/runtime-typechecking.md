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

Strict checking covers `signals.js`, `scheduler.js`, their `effects.js` and
`computed.js` exports, and `lifecycle.js`. Contract fixtures under `tests/types/`
check valid usage and intentionally invalid examples. An unused
`@ts-expect-error` fails the check, so the invalid examples also verify that
types have not silently become permissive.

The larger component, DOM renderer, router and integration modules are not yet
strictly checked. Expand coverage module by module as their contracts are
annotated. Browser and runtime behavior tests remain required; types cannot
prove correct rendering, cleanup, focus handling or hydration.

## For application developers

No extra setup is required. `pip install teloce-py` continues to ship JavaScript
runtime files. Node and TypeScript are contributor/CI tools, not dependencies
for Python application users. Production compilation and MinifyJS optimization
are unchanged. This adds development checks, not a runtime speed improvement.

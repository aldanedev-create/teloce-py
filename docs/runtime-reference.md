# Runtime API reference

Compiled `.vel` files normally import only the generated application runtime.
Use the explicit runtime modules when building a small standalone app or when
sharing state between independently compiled components.

| Module | Responsibility |
| --- | --- |
| `runtime.js` | Public runtime composition and shared runtime entry point. |
| `component.js` | Component mount, update, props, and teardown coordination. |
| `signals.js` | `createSignal`, `createComputed`, `createEffect`, batching, and subscriptions for explicit state. |
| `reactivity.js` | Dependency tracking and reactive effects. |
| `computed.js` | Derived values that update when dependencies change. |
| `effects.js` | Effects and disposer registration. |
| `scheduler.js` | Batched browser updates. |
| `dom.js` | Text, attributes, classes, styles, and DOM reconciliation helpers. |
| `events.js` | Event listeners and event cleanup. |
| `lifecycle.js` | Mount, update, unmount, and disposer lifecycle. |
| `props.js` | Prop defaults and validation. |
| `slots.js` | Slot content and component composition. |
| `standalone.js` | Small declarative runtime for a Jinax/Jinja page. |

## Explicit signal example

```js
import { createSignal, createEffect } from '/static/teloce/signals.js';

const count = createSignal(0);
const effect = createEffect(() => {
  document.querySelector('#count').textContent = String(count());
});

document.querySelector('#increment').addEventListener('click', () => {
  count.set(count() + 1);
});

window.addEventListener('pagehide', () => effect.stop(), { once: true });
```

`createEffect()` returns an effect object, not a callback. Use `effect.stop()`
when the feature is destroyed. By contrast, `signal.subscribe(listener)`
returns a callable unsubscribe function.

Generated components register their event listeners and effects with their
component scope. Third-party editors, canvases, and media players must be
destroyed from `beforeUnmount`/`unmounted` hooks so they do not retain DOM
nodes after router navigation.

Do not import a Python module into browser code. Browser runtime code calls a
Python endpoint with `fetch()` or a WebSocket; Python performs validation,
authorization, persistence, and secrets management.

## Queued updates and cleanup

Signals use callable reads and explicit setters:

```js
const count = signal(0);
count();                  // read and track
count.set(1);             // write
count.update(value => value + 1);
const unsubscribe = count.subscribe(value => console.log(value));
unsubscribe();
```

The compiler supplies the runtime helpers for supported component scripts;
manual imports are unnecessary in that workflow. `signal(...).value` is not
this runtime's API.

Synchronous writes coalesce into one microtask. Subscription callbacks receive
the latest value, and unsubscribing also cancels a callback already queued.
`createEffect(...).stop()` removes dependencies and prevents pending execution.
A failing scheduled job does not discard unrelated jobs: errors are reported
after the rest of that queue snapshot runs.

`reactive()` observes plain objects and arrays, including array growth,
truncation, property existence, and key iteration. Browser objects and class
instances retain their original receiver; wrap their exposed state separately.

`createFor()` reuses keyed rows, moves only rows whose order changed, and calls
row cleanup when rows are removed or the helper unmounts. `createIf()` preserves
its existing branch when the condition's truth value has not changed. Both
helpers cancel queued subscription callbacks on unmount.

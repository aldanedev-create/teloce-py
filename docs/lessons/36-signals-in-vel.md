# Signals inside `.vel` components

## Table of contents

1. [Choose `data()` or a signal](#choose-data-or-a-signal)
2. [Use zero-setup signals in `.vel`](#use-zero-setup-signals-in-vel)
3. [Expose the signal runtime manually](#expose-the-signal-runtime-manually)
4. [Build a shared counter component](#build-a-shared-counter-component)
5. [Why the component mirrors the signal](#why-the-component-mirrors-the-signal)
6. [Cleanup is required](#cleanup-is-required)
7. [Share signals across components](#share-signals-across-components)
8. [Framework setup](#framework-setup)
9. [Testing and troubleshooting](#testing-and-troubleshooting)

## Choose `data()` or a signal

Use ordinary component state for values owned by one component:

```html
<script>
export default {
  data() { return { count: 0 }; },
  methods: { increment() { this.count++; } },
};
</script>
```

Use a signal when independent components or browser modules need to observe the
same value. A signal is a function with `.get()`, `.set()`, and `.update()`:

```js
const count = signal(0);
count();                          // read
count.set(1);                     // replace
count.update(value => value + 1); // derive and replace
```

`signal`, `effect`, and `computed` are short aliases that Teloce makes
available automatically during a normal project build. The explicit names
`createSignal`, `createEffect`, and `createComputed` are also available.

The signal itself is not automatically unwrapped when placed directly in a
`.vel` template. Mirror its current value into reactive `data()` state. This
keeps template expressions simple and lets the generated component runtime
update the DOM normally.

## Use zero-setup signals in `.vel`

For a project built with `teloce build`, this is all the signal setup needed:

```html
<script>
const count = signal(0)

export default {
  data() { return { count: count() } },
  mounted() {
    this.countEffect = effect(() => { this.count = count() })
  },
  beforeUnmount() {
    this.countEffect?.stop()
  },
  methods: {
    increment() { count.update(value => value + 1) },
  },
}
</script>
```

There is no runtime URL import in this component. The builder emits one shared
runtime, copies its signal scheduler modules, and adds only the signal imports
the component actually uses. This keeps `.vel` files readable while retaining
normal ES-module behavior.

If you run the low-level `Compiler` directly instead of `teloce build`, pass a
`shared_runtime_import` option or keep using an explicit import. Automatic
imports are deliberately enabled only when the compiler knows the generated
shared runtime URL.

The normal build output looks like this:

```text
dist/static/
├── teloce-runtime.js   # shared barrel, including signal exports
├── signals.js           # signal implementation
├── scheduler.js         # batched signal updates
└── js/SharedCounter.js  # generated component
```

Your HTML only mounts the generated component. It does not need a separate
`signals.js` script tag; the generated ES module imports the shared barrel.

## Expose the signal runtime manually

This section is only needed when you use the low-level `Compiler`, hand-write a
browser module, or integrate signals into a non-`.vel` JavaScript file. A normal
`teloce build` copies these files into `dist/static` automatically.

Copy them from the installed package during your Python build/startup step:

```python
from importlib.resources import files
from pathlib import Path
import shutil

runtime_out = Path("static/teloce")
runtime_out.mkdir(parents=True, exist_ok=True)
runtime_package = files("teloce.runtime")
for filename in ("signals.js", "scheduler.js"):
    with runtime_package.joinpath(filename).open("rb") as source:
        with (runtime_out / filename).open("wb") as destination:
            shutil.copyfileobj(source, destination)
```

For a production bundle, keep these files inside the configured static tree
and let esbuild bundle local module imports when appropriate.

## Build a shared counter component

Save this as `static/js/SharedCounter.vel`. It is a complete component and is
compiled by the lesson regression test.

```html
<template>
  <section class="counter-card">
    <p class="eyebrow">Shared signal</p>
    <h1>{{ count }} clicks</h1>
    <p>{{ status }}</p>
    <button type="button" @click="increment">Add one</button>
    <button type="button" @click="reset">Reset</button>
  </section>
</template>

<script>
export const sharedCount = signal(0);

export default {
  data() {
    return { count: sharedCount(), status: "Connected to the shared signal" };
  },
  mounted() {
    this.stopSignal = effect(() => {
      this.count = sharedCount();
    });
  },
  methods: {
    increment() { sharedCount.update(value => value + 1); },
    reset() { sharedCount.set(0); },
  },
  unmounted() {
    this.stopSignal?.stop();
  },
};
</script>

<style scoped>
.counter-card { max-width: 28rem; margin: 3rem auto; padding: 1.5rem; border: 1px solid #dce2f0; border-radius: 1rem; background: white; font-family: system-ui, sans-serif; }
.eyebrow { color: #4f46e5; font-size: .8rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
button { margin-right: .5rem; border: 0; border-radius: .5rem; padding: .65rem .9rem; background: #312e81; color: white; cursor: pointer; }
</style>
```

Mount the compiled module:

```html
<div id="app"></div>
<script type="module">
  import { mount } from "/static/js/SharedCounter.js";
  mount("#app");
</script>
```

Build and run:

```bash
python -m teloce build
python app.py
```

Clicking either button changes `sharedCount`. The effect observes that signal
and copies its value into `this.count`, which the generated `.vel` runtime
understands as ordinary reactive component state.

## Why the component mirrors the signal

The data flow is intentionally explicit:

```text
signal value → createEffect → component data → template → DOM
```

Avoid putting the signal function itself in a template:

```html
<!-- The signal function itself is not the displayed number. -->
<p>{{ sharedCount }}</p>
```

Use the mirrored value:

```html
<p>{{ count }}</p>
```

The direct-signal template shorthand is not currently the stable public API.
The explicit mirror also shows where a component subscribes and cleans up.

## Cleanup is required

Every effect, timer, WebSocket, observer, and event listener created by a
component must be stopped when the component unmounts:

```js
mounted() {
  this.stopSignal = effect(() => {
    this.count = sharedCount();
  });
  this.timer = window.setInterval(() => this.refresh(), 10_000);
},
unmounted() {
  this.stopSignal?.stop();
  window.clearInterval(this.timer);
}
```

Without cleanup, router navigation can leave an old effect subscribed to a
signal and update a detached DOM tree. `createEffect()` returns an effect
object, not a disposer function; call `.stop()` during teardown.

## Share signals across components

Put a shared signal in a normal browser module:

```js
// static/js/shared/store.js
import { createSignal, createComputed } from "/static/teloce/signals.js";

export const selectedId = createSignal(null);
export const hasSelection = createComputed(() => selectedId() !== null);
```

A `.vel` component can import the store and mirror its value:

```html
<script>
import { createEffect } from "/static/teloce/signals.js";
import { selectedId } from "/static/js/shared/store.js";

export default {
  data() { return { selected: selectedId() }; },
  mounted() {
    this.stopSelection = createEffect(() => { this.selected = selectedId(); });
  },
  unmounted() { this.stopSelection?.stop(); },
  methods: { choose(id) { selectedId.set(id); } },
};
</script>
```

Use `createComputed()` for derived values and read it with `value()`:

```js
const online = createSignal(false);
const label = createComputed(() => online() ? "Online" : "Offline");
const logger = createEffect(() => console.log(label()));
online.set(true);
logger.stop();
```

## Framework setup

The runtime is framework-independent. Flask, FastAPI, Django, and Flaxon must
serve these browser assets at stable URLs:

```text
/static/js/SharedCounter.js
/static/teloce/signals.js
/static/teloce/scheduler.js
```

Flask uses its static folder, FastAPI uses `StaticFiles`, Django uses
`STATICFILES_DIRS`, and Flaxon/Jinax uses its normal static route. For a normal
build, serve the generated `dist/static` directory, including
`teloce-runtime.js`, `signals.js`, and `scheduler.js`. Python remains
responsible for API validation, authentication, persistence, and WebSocket
authorization.

For a Flask shell, the important part is serving the generated output:

```python
from flask import Flask, render_template

app = Flask(__name__, static_folder="dist/static", static_url_path="/static")

@app.get("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
```

Compile `.vel` files before starting Flask. In production, compile in CI and
serve `dist/static` from the normal static host.

## Testing and troubleshooting

```bash
python -m teloce build
python -m pytest -q
```

| Symptom | Fix |
| --- | --- |
| `404 signals.js` | Serve the complete `dist/static` output, or manually copy `signals.js` and `scheduler.js` into the configured static directory. |
| `createSignal is not a function` | Check that the URL returns Teloce's ES module, not an HTML error page. |
| `signal is not defined` | Use `teloce build` or pass `shared_runtime_import` to the low-level compiler; otherwise add the explicit runtime import. |
| UI does not update | Read the signal inside `createEffect()` and mirror it into component state. |
| Old component still reacts | Call `.stop()` in `unmounted()`. |
| Signal works in one component only | Put it in a shared module, not only inside one component's `data()`. |
| Browser cannot load a `.ts` store | Transform and bundle the TypeScript module with esbuild first. |

Use `signal()` for the shortest `.vel` syntax, `createSignal()` for explicit
runtime code, `data()` for ordinary local state, and always pair every effect
or subscription with cleanup.

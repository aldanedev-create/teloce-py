# Lesson 19: Signals, reactivity, and the browser runtime

Teloce has two related reactivity layers:

1. Component state returned by `data()` is automatically reactive.
2. Explicit signals are small observable values that can be shared by browser modules or runtime helpers.

Use component state for values owned by one `.vel` component. Use signals when independent components, a browser service, or an effect need to observe the same value.

## First: what does “the runtime” mean?

There are two runtime paths, and choosing the right one avoids confusion.

### 1. Compiled component runtime

When you compile a `.vel` file, Teloce-Py normally emits a self-contained JavaScript module. The generated module includes the behavior it needs for mounting, events, interpolation, conditions, loops, bindings, and lifecycle hooks. For this normal workflow, you do not copy a runtime file or install JavaScript packages.

```html
<div id="app"></div>
<script type="module">
  import { mount } from '/static/js/App.js'
  mount(document.querySelector('#app'))
</script>
```

This is the recommended starting point for a beginner.

### 2. Explicit browser runtime assets

The package also includes reusable browser files in `teloce.runtime`. Use these when you want a standalone server-rendered page, shared signals, or a browser helper used by multiple components. Python only copies/serves these files; they execute in the browser.

The package contains:

```text
teloce/runtime/
├── standalone.js   # global teloce.createApp() runtime for HTML/Jinja
├── signals.js      # createSignal, createComputed, createEffect
├── scheduler.js    # dependency of signals.js
├── runtime.js      # composed ES-module runtime
└── other runtime modules
```

Do not import a Python file into browser JavaScript. The browser needs a URL to a `.js` file served by Flask, FastAPI, Django, Flaxon, or another web server.

## Beginner project: expose the runtime with Flask

Create this project:

```text
runtime-demo/
├── app.py
├── templates/index.html
└── static/teloce/
```

Install the packages:

```bash
python -m pip install Flask teloce-py
```

Create `app.py`. This copies the two files required by the signals module into your public static directory every time the app starts:

```python
from importlib.resources import files
from pathlib import Path
import shutil

from flask import Flask, render_template

ROOT = Path(__file__).parent
RUNTIME_OUT = ROOT / 'static' / 'teloce'
RUNTIME_OUT.mkdir(parents=True, exist_ok=True)

runtime_package = files('teloce.runtime')
for filename in ('signals.js', 'scheduler.js'):
    source = runtime_package.joinpath(filename)
    destination = RUNTIME_OUT / filename
    with source.open('rb') as input_file, destination.open('wb') as output_file:
        shutil.copyfileobj(input_file, output_file)

app = Flask(__name__)

@app.get('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

Now the browser can request:

```text
http://127.0.0.1:5000/static/teloce/signals.js
http://127.0.0.1:5000/static/teloce/scheduler.js
```

Create `templates/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Runtime demo</title>
  </head>
  <body>
    <h1 id="status">Offline</h1>
    <button id="connect">Connect</button>
    <button id="disconnect">Disconnect</button>

    <script type="module">
      import { createSignal, createComputed, createEffect } from '/static/teloce/signals.js'

      const online = createSignal(false)
      const status = createComputed(() => online() ? 'Online' : 'Offline')
      const statusElement = document.querySelector('#status')

      const effect = createEffect(() => {
        statusElement.textContent = status()
      })

      document.querySelector('#connect').addEventListener('click', () => online.set(true))
      document.querySelector('#disconnect').addEventListener('click', () => online.set(false))

      // createEffect() returns an object; stop it during teardown.
      window.addEventListener('pagehide', () => effect.stop(), { once: true })
    </script>
  </body>
</html>
```

Run the app:

```bash
python app.py
```

Open `http://127.0.0.1:5000`. Clicking Connect changes the signal, recalculates `status`, and runs the effect that updates the heading. No page reload is needed.

## Using the standalone runtime with Jinax or Jinja

The standalone runtime is for HTML that is already rendered by Python. It is different from the ES-module signals file. Copy it with:

```python
from importlib.resources import files
import shutil

source = files('teloce.runtime').joinpath('standalone.js')
with source.open('rb') as input_file, (RUNTIME_OUT / 'standalone.js').open('wb') as output_file:
    shutil.copyfileobj(input_file, output_file)
```

Then use it in a server-rendered template:

```html
<div id="app">
  <h1>{{ title }}</h1>
  <button @click="count++">Clicked {{ count }} times</button>
</div>
<script src="/static/teloce/standalone.js"></script>
<script>
  teloce.createApp('#app', { title: 'Hello from Python', count: 0 })
</script>
```

The server renders `{{ title }}` first when using Jinja/Jinax. Teloce then owns browser-side events and state. Escape untrusted server values and never use `v-html` with untrusted content.

Use the standalone runtime for small server-rendered pages or gradual migration. Use compiled `.vel` modules for larger applications, local imports, scoped CSS, source maps, and component-level lifecycle control.

## Component reactivity: the easiest path

Create `static/js/App.vel`:

```html
<template>
  <main class="demo">
    <p class="eyebrow">Teloce reactivity</p>
    <h1>{{ count }} clicks</h1>
    <button @click="increment">Add one</button>
    <button @click="reset">Reset</button>
    <p v-if="count > 0">The component state changed and the DOM updated.</p>
    <p v-else>Click the button to create your first update.</p>
    <ul>
      <li v-for="item in events" :key="item.id">{{ item.label }}</li>
    </ul>
  </main>
</template>

<script>
export default {
  data() {
    return { count: 0, events: [] }
  },
  methods: {
    increment() {
      this.count++
      this.events = [...this.events, { id: this.count, label: `Click ${this.count}` }]
    },
    reset() {
      this.count = 0
      this.events = []
    }
  }
}
</script>

<style scoped>
.demo { min-height: 100vh; display: grid; place-content: center; gap: 1rem; padding: 2rem; background: #0b1020; color: #f4f1ff; font-family: system-ui, sans-serif; }
button { margin-right: .5rem; border: 1px solid #7467b8; border-radius: .6rem; padding: .65rem 1rem; background: #1b1735; color: inherit; cursor: pointer; }
li { margin: .3rem 0; color: #b8aed8; }
</style>
```

`count` and `events` are ordinary JavaScript values from the developer's perspective. Teloce observes assignments made by event handlers, rerenders the component, and updates the affected DOM. Stable `:key` values let the runtime preserve list item identity.

## Explicit signals

Copy the browser runtime into a public static location as part of your build, or expose the packaged runtime using your framework's static-file configuration. Then create `static/js/shared/store.js`:

```js
import { createSignal, createComputed, createEffect } from '/static/teloce/signals.js'

export const online = createSignal(false)
export const status = createComputed(() => online() ? 'Online' : 'Offline')

export const statusLogger = createEffect(() => {
  console.log('Connection status:', status())
})

export function setOnline(value) {
  online.set(Boolean(value))
}
```

Use the store from another browser module:

```js
import { online, status, setOnline } from './shared/store.js'

const label = document.querySelector('#status')
const unsubscribe = status.subscribe(value => { label.textContent = value })
setOnline(true)

// Call unsubscribe() when the page or feature is destroyed.
// statusLogger.stop() stops the effect created by the store.
```

A signal is callable and has useful methods:

```js
const count = createSignal(0)
count()                 // read
count.get()             // read explicitly
count.set(2)            // replace
count.update(value => value + 1)
count.peek()            // read without tracking an effect
const stop = count.subscribe(value => console.log(value))
stop()
```

The tuple form is also supported:

```js
const [name, setName] = createSignal('Ada')
setName('Grace')
console.log(name())
```

## A `.vel` component consuming a signal

For a component that needs a shared signal, import the store in its `<script>` block and copy the current signal value into component state. Subscribe during `mounted` and unsubscribe during `beforeUnmount`:

```html
<script>
import { status } from './shared/store.js'

export default {
  data() { return { status: status() } },
  mounted() {
    this.stopStatus = status.subscribe(value => { this.status = value })
  },
  beforeUnmount() {
    this.stopStatus?.()
  }
}
</script>

<template><p class="status">Server: {{ status }}</p></template>
```

The subscription is a resource. Always remove it when the component unmounts, otherwise a long-running app can retain destroyed components.

## Runtime files and Flask

The Python server does not execute signals. It serves the JavaScript runtime, generated component modules, and HTML shell. A simple Flask setup is:

```python
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=str(ROOT / 'static'))

@app.get('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    build_project(ROOT, options={'dev': True, 'source_maps': True})
    app.run(debug=True, port=5000)
```

In production, serve the runtime from a versioned static path, set cache headers for immutable build assets, and run `teloce build` in CI. Signals are client-side state; passwords, permissions, private records, and authorization decisions must remain in Python.

## Debugging reactivity

If the screen does not update:

- verify the event name and handler name match;
- log the value inside the handler;
- use a stable `:key` in loops;
- check the browser console for generated-module errors;
- confirm the component actually mounted into the HTML element;
- unsubscribe effects and signal listeners during unmount;
- run `teloce lint --strict` and `teloce build --source-map`.

Read [Reactivity](../reactivity.md), [How Teloce-Py works](16-how-teloce-works.md), and [Debugging](../debugging.md) together when diagnosing a larger application.

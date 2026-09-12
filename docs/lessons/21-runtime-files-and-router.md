# Lesson 21: Runtime files and the router

This is a practical reference for developers who want to know what each browser runtime file does and how routing connects the files together.

## The runtime directory

The installed package contains these browser modules in `src/teloce/runtime/`:

| File | Purpose | Typical developer use |
|---|---|---|
| `standalone.js` | Global runtime for HTML already rendered by Jinja/Jinax | Include with `<script src>` and call `teloce.createApp()` |
| `signals.js` | Signals, computed values, effects, reactive proxies, and batching | Import shared browser state from an ES module |
| `scheduler.js` | Microtask queue and `batch()` implementation used by signals | Copy beside `signals.js`; rarely import directly |
| `runtime.js` | ES-module barrel that re-exports the runtime modules | Import several low-level runtime APIs from one URL |
| `reactivity.js` | Re-exports the reactivity APIs | Use when a codebase wants a reactivity-focused import |
| `computed.js` | Re-exports `createComputed` | Optional focused import |
| `effects.js` | Re-exports `createEffect` | Optional focused import |
| `dom.js` | Element creation, attributes, events, loops, conditions, models, classes, and cleanup | Advanced runtime/plugin work |
| `component.js` | Low-level component creation and app mounting helpers | Advanced custom runtime integrations |
| `props.js` | Prop definition and validation helpers | Custom components or runtime integrations |
| `events.js` | Component event emission helper | Advanced component integrations |
| `lifecycle.js` | Lifecycle hook helpers | Advanced runtime integrations |
| `slots.js` | Slot rendering helper | Advanced component integrations |

Most application developers should start with compiled `.vel` modules or `standalone.js`. The files marked advanced are implementation building blocks; importing them directly couples an application to lower-level runtime details.

## How to expose runtime files

Runtime files are not automatically browser URLs. Python must copy them into a public directory and the framework must serve that directory.

For signals, copy both files because `signals.js` imports `scheduler.js`:

```python
from importlib.resources import files
from pathlib import Path
import shutil

output = Path('static/teloce')
output.mkdir(parents=True, exist_ok=True)
runtime = files('teloce.runtime')

for filename in ('signals.js', 'scheduler.js'):
    source = runtime.joinpath(filename)
    with source.open('rb') as input_file, (output / filename).open('wb') as output_file:
        shutil.copyfileobj(input_file, output_file)
```

For the standalone runtime:

```python
source = files('teloce.runtime').joinpath('standalone.js')
with source.open('rb') as input_file, (output / 'standalone.js').open('wb') as output_file:
    shutil.copyfileobj(input_file, output_file)
```

Then the browser imports a URL, not a package path:

```html
<script type="module">
  import { createSignal } from '/static/teloce/signals.js'
</script>
```

The Flaxon notebook in [`examples/flaxon-runtime-notebook`](../../examples/flaxon-runtime-notebook/) demonstrates this asset-copy and asset-serving pattern.

## Which runtime entry point should I choose?

### Compiled `.vel` application

Use this for a multi-component application:

```html
<div id="app"></div>
<script type="module">
  import { mount } from '/static/js/App.js'
  mount(document.querySelector('#app'))
</script>
```

The generated module normally contains the runtime behavior it needs. You do not manually import `dom.js`, `component.js`, or `lifecycle.js` for normal `.vel` work.

### Server-rendered Jinax/Jinja page

Use this for a small page where HTML already comes from Python:

```html
<div id="app">
  <h1>Notebook</h1>
  <button @click="count++">{{ count }}</button>
</div>
<script src="/static/teloce/standalone.js"></script>
<script>
  teloce.createApp('#app', { count: 0 })
</script>
```

If Jinax/Jinja sees Teloce expressions such as `{{ note.title }}` before the browser does, wrap the Teloce-owned markup in `{% raw %}...{% endraw %}`. Keep server expressions outside that block.

### Shared signals

Use `signals.js` when multiple browser modules need the same value:

```js
import { createSignal, createComputed, createEffect } from '/static/teloce/signals.js'

export const online = createSignal(false)
export const label = createComputed(() => online() ? 'Online' : 'Offline')
export const statusEffect = createEffect(() => {
  document.querySelector('#status').textContent = label()
})
```

Call `statusEffect.stop()` when the feature is destroyed. Never treat a client signal as authorization or as a place for secrets.

## How the router is made

Teloce-Py does not require a JavaScript router package. Python validates a route configuration, generates a dependency-free browser router, and writes it into your static output.

```python
from pathlib import Path
from teloce.router import RouterCompiler, RouterGenerator

config = {
    'mode': 'hash',
    'base': '/',
    'routes': [
        {'path': '/', 'component': 'HomePage', 'name': 'home'},
        {'path': '/tutorial', 'component': 'TutorialPage', 'name': 'tutorial'},
        {'path': '/users/:id', 'component': 'UserPage', 'name': 'user'},
        {'path': '/legacy', 'redirect': '/tutorial'},
    ],
}

compiler = RouterCompiler()
compiled = compiler.compile(config)
if compiled is None:
    raise ValueError(compiler.errors)

router_code = RouterGenerator().generate(compiled)
output = Path('dist/static/js/router.js')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(router_code, encoding='utf-8')
```

The generated router still needs imports for the component modules. Add them before the generated code:

```python
imports = """import HomePage from './pages/HomePage.js';
import TutorialPage from './pages/TutorialPage.js';
import UserPage from './pages/UserPage.js';
"""
output.write_text(imports + router_code, encoding='utf-8')
```

Mount it in the HTML shell:

```html
<div id="app"></div>
<script type="module">
  import router from '/static/js/router.js'
  router.mount(document.querySelector('#app'))
</script>
```

## Router modes

### Hash mode

```python
{'mode': 'hash', 'routes': routes}
```

Links look like `href="#/tutorial"`. This is the easiest mode for Vercel and other serverless hosts because refreshing a route remains on the same HTML document.

### History mode

```python
{'mode': 'history', 'routes': routes}
```

Links use normal paths such as `/tutorial`. Your Python server or hosting platform must return the HTML shell for every client route on a direct refresh. Without a fallback rewrite, `/tutorial` can work after clicking but return `404` after refreshing.

## Router API

The generated router exposes:

```js
router.push('/tutorial')
router.replace('/tutorial')
router.back()
router.forward()
router.go(-1)
router.resolve('/users/42?tab=posts')
router.subscribe(state => console.log(state.path, state.params, state.query))

const removeGuard = router.beforeEach((to, from) => {
  if (to.path === '/admin' && !window.currentUser) return '/login'
})
```

Route parameters are available from `router.state.params`; query values are in `router.state.query`; the complete current URL is in `router.state.fullPath`. These values improve view selection, but they do not protect data. Every Python API endpoint must authenticate and authorize independently.

## Router lifecycle and page cleanup

When navigation changes the active component, the router unmounts the previous component before mounting the next one. Use cleanup hooks for timers, animation frames, event listeners, signal subscriptions, WebSocket connections, and media streams:

```html
<script>
export default {
  mounted() {
    this.stopStatus = status.subscribe(value => { this.status = value })
  },
  beforeUnmount() {
    this.stopStatus?.()
  }
}
</script>
```

For Three.js, also dispose geometries, materials, and the renderer. A route change that appears visually correct can still leak resources if cleanup is missing.

## Keep the router fast when a page uses a large library

The router imports its route components before mounting the active page. If a route component has a top-level import for a large library such as Three.js, that download can delay the entire application. Load the library inside `mounted` instead:

```html
<script>
export default {
  data() { return { loading: true, error: false, destroyed: false } },
  mounted() {
    import('https://cdn.jsdelivr.net/npm/three@0.171.0/build/three.module.js').then(
      module => { if (!this.destroyed) this.startScene(module) },
      error => { this.loading = false; this.error = true; console.error(error) }
    )
  },
  beforeUnmount() { this.destroyed = true; this.renderer?.dispose() },
  methods: {
    startScene(THREE) { this.renderer = new THREE.WebGLRenderer({ antialias: true }); this.loading = false }
  }
}
</script>
```

Render a `loading` or `error` fallback immediately. This pattern was required by the Teloce Motion showcase: its original top-level CDN import made Vercel appear to show only a background color until the remote module finished loading. Test both a fast connection and a throttled/offline connection.

## Debugging runtime and router loading

Check these URLs directly:

```bash
curl -I http://127.0.0.1:5000/static/teloce/standalone.js
curl -I http://127.0.0.1:5000/static/teloce/signals.js
curl -I http://127.0.0.1:5000/static/js/router.js
```

Then check the browser console for module errors. A `404`, an HTML response for a JavaScript URL, a missing `scheduler.js`, a router with no matching route, or a mount element that is `null` will prevent the expected UI from appearing.

For the full working combination of Flaxon, Jinax, runtime files, reactive state, and cleanup, run the notebook example and read [Troubleshooting](../troubleshooting.md).

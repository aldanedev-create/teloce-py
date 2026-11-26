# Troubleshooting guide

This guide records issues found while building the Flaxon OS simulation and PySeek search engine.

## Blank page or missing UI

Verify the mount target and module path:

```html
<main id="app"></main>
<script type="module">import { mount } from "/assets/static/js/App.js"; mount("#app")</script>
```

Check every generated JavaScript and CSS request in DevTools Network. A wrong output directory or stale service worker can make a valid Python server look blank.

### The `.vel` file is not being found

Put source components under the directory the compiler scans, normally `static/js/`. Keep server templates in `templates/` and generated files in `dist/` or `public/`:

```text
static/js/App.vel                 # source: edit this
static/js/components/Header.vel   # source: import this relatively
templates/index.html              # server HTML shell
dist/static/js/App.js             # generated: do not edit this
```

Run:

```bash
teloce doctor --verbose
teloce lint --strict
teloce build --out-dir dist --source-map
```

If the component is absent from the build report, it is in the wrong source directory, excluded by configuration, or has an extension/case mismatch. If it appears in the report but the browser receives `404`, your static-file route points at a different output directory.

### The HTML mount is wrong

The HTML shell must contain the mount element and load the generated module:

```html
<main id="app"></main>
<script type="module">
  import { mount } from '/static/js/App.js'
  mount(document.querySelector('#app'))
</script>
```

For a generated router:

```html
<div id="app"></div>
<script type="module">
  import router from '/static/js/router.js'
  router.mount(document.querySelector('#app'))
</script>
```

An empty mount element with no console error often means the module was never requested, the router has no matching route, or an old cached module is being used.

## Text disappears while typing

Do not let a parent native `@input` listener update reactive state on a custom component. The child can be re-rendered and erase the browser value. Use:

```html
<input v-model="localQuery" @input.stop="$emit('suggest', $event.target.value)" />
```

Listen for `@suggest` in the parent. This preserves typing while still supporting suggestions.

## `event.stopPropagation is not a function`

Some runtime versions use `event.detail` for custom events. Native input events can have numeric `detail`, causing a method to receive `0` instead of an event. Prefer the inline `.stop` pattern above or update Teloce-Py to a runtime that distinguishes native and custom events.

## API works but cards are empty or duplicated

Compare the JSON response with the component props. In a loop, pass loop values as interpolated attributes when the runtime cannot preserve loop-scope expressions:

```html
<ResultCard v-for="result in results"
  url="{{ result.url }}" title="{{ result.title }}"
  snippet="{{ result.snippet }}" />
```

Assert that rendered card count equals API result count. Check dynamic `:results` and `:result` bindings in the generated child prop reader.

## Imports, CSS, or routes fail

Resolve imports relative to the importing file and keep filename casing consistent:

```html
<script>import SearchBar from './components/SearchBar.vel'</script>
```

Run `teloce build --out-dir dist`, inspect the generated CSS path, and verify that rewrites do not change `/assets/...` into an unexpected backend route.

### A component import works locally but fails in production

Use a relative import from the importing file and preserve filename casing:

```html
<!-- static/js/pages/Home.vel -->
<script>import Card from '../components/Card.vel'</script>
```

`Card.vel`, `card.vel`, and `CARD.vel` may be treated as different files on Linux even if they appear equivalent on Windows. Run a clean production build in an environment matching deployment. Never rely on a generated file left over from an earlier build.

### The compiler fails around HTML or code examples

Keep HTML void elements valid for the SFC parser:

```html
<br />
<input type="search" />
<img src="/static/logo.svg" alt="Logo" />
```

Avoid unescaped backticks inside template text when the generated component uses a JavaScript template literal. Write `.vel` as text or use an HTML entity instead:

```html
<p>Use a ".vel" file.</p>
```

Put JavaScript template literals inside the `<script>` section, where they belong. After changing a parser-sensitive template, run `node --check` against the generated module.

### CSS exists but does not appear

Check that the component style is inside `<style>` or `<style scoped>` and that the generated CSS is loaded. Scoped CSS selectors receive a component scope attribute; a selector copied into a separate global stylesheet may not match as expected. Also check for an overlay, `z-index`, `display: none`, zero height, or a parent with `overflow: hidden`.

## Three.js, canvas, and animation problems

The Teloce Motion showcase exposed several useful checks:

1. Confirm the CDN module returns `200` and JavaScript content.
2. Confirm the `.vel` file contains the import and the generated module preserves it.
3. Create the renderer only in `mounted`, after the canvas host exists.
4. Give the scene container a non-zero width and height.
5. Use `requestAnimationFrame` and cancel it in `beforeUnmount`.
6. Dispose geometries, materials, and the renderer when leaving the route.
7. Catch WebGL initialization errors and show a user-visible fallback.

```html
<script>
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.171.0/build/three.module.js'

export default {
  data() { return { frame: 0, webglError: false } },
  mounted() {
    const host = document.querySelector('#scene')
    try {
      this.scene = new THREE.Scene()
      this.camera = new THREE.PerspectiveCamera(45, host.clientWidth / host.clientHeight, .1, 100)
      this.camera.position.z = 3
      this.renderer = new THREE.WebGLRenderer({ antialias: true })
      this.renderer.setSize(host.clientWidth, host.clientHeight)
      host.appendChild(this.renderer.domElement)
      this.animateFrame()
    } catch (error) {
      this.webglError = true
      console.error('WebGL initialization failed', error)
    }
  },
  beforeUnmount() {
    cancelAnimationFrame(this.frame)
    this.renderer?.dispose()
  },
  methods: {
    animateFrame() {
      this.frame = requestAnimationFrame(this.animateFrame.bind(this))
      this.renderer.render(this.scene, this.camera)
    }
  }
}
</script>
```

If the page shows the fallback, inspect the console for `Error creating WebGL context`, test another browser, update graphics drivers, and check whether hardware acceleration is disabled. A CSS fallback is preferable to an empty panel.

### Vercel shows only the background color while Three.js loads

Do not use a large CDN import at the top level of the page's router entry module:

```js
// This blocks the router and every page until the CDN responds.
import * as THREE from 'https://cdn.jsdelivr.net/npm/three/build/three.module.js'
```

That pattern can make a serverless deployment appear blank or take a long time to load. The Teloce Motion showcase had this exact problem. Load Three.js after the component has mounted so the text, navigation, and fallback render immediately:

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
    startScene(THREE) {
      try {
        // Create the scene and renderer here, after the host element exists.
        this.scene = new THREE.Scene()
        this.renderer = new THREE.WebGLRenderer({ antialias: true })
        this.loading = false
      } catch (error) {
        this.loading = false; this.error = true; console.error(error)
      }
    }
  }
}
</script>
```

Render a loading/error panel with `v-if="loading || error"`. Keep the import version pinned, or bundle Three.js during the build for a fully self-contained release. After deploying, hard-refresh and verify the generated module contains a dynamic `import(` rather than a top-level `import * as THREE`.

## Router navigation problems

## Vel IDE: `Identifier '.default' has already been declared`

This occurred in the Vel IDE when a `.vel` script contained a top-level helper declaration before `export default`. The compiler preserved the script and also emitted the component definition, so the module declared the default component twice. Keep helper values inside `data()` or component methods when the compiler version has this limitation. For example:

```html
<script>
export default {
  data() { return { starter: [String.fromCharCode(60) + 'template>', String.fromCharCode(60) + '/template>'].join(String.fromCharCode(10)) } }
}
</script>
```

After changing the component, rebuild and run `node --check dist/static/js/components/EditorShell.js`. Import that generated module directly in DevTools if the page is still blank; the first failing module is usually the source of the problem.

## Vel IDE: Monaco does not appear

Do not assume that any existing `window.require` is Monaco's AMD loader. Some pages or tools define their own `require` function. Check `window.monaco?.editor` first; otherwise load the pinned Monaco loader script and initialize Monaco in `mounted()`. Confirm the CDN requests return HTTP 200 and that `window.monaco.editor.getModels().length` becomes greater than zero.

If the Monaco model exists but the editor is invisible, inspect the host's computed height and inspect whether Teloce replaced its children after a state update. A component rerender can detach Monaco's DOM even though its model remains alive. Keep the editor instance in a non-reactive reference such as `window.velIdeEditor` or a host property, set the editor host's `height: 100%`, and update status text directly when necessary. Dispose that reference in `beforeUnmount()`.

## Vel IDE: compile button says failed

Check the response from `POST /api/compile`, not only the button label. A successful response is HTTP 200 with `ok: true`; malformed `.vel` source should be HTTP 422 with `diagnostics.errors`. If the editor value contains literal `\\n` characters instead of real newlines, construct the source with `String.fromCharCode(10)` or a real newline before submitting it. Never silently discard compiler diagnostics.

## Vel IDE: blank screen but Flask returns 200

A 200 HTML response only proves that the shell arrived. Verify, in order:

1. `/static/js/App.js` returns 200 and `text/javascript`.
2. Every imported child module returns 200.
3. `node --check` passes for the generated entry and editor module.
4. The browser console has no module parse error.
5. `mount(document.querySelector('#app'))` is called.
6. Monaco is loaded after the editor component mounts.

The most useful browser test is to load the page at desktop and mobile widths, count `#app .ide`, and inspect `pageerror` events. A responsive layout should not have `document.documentElement.scrollWidth > window.innerWidth`.

When one route works and another is blank, inspect the hash/history URL and the generated router:

```js
console.log(location.hash)
console.log(window.__teloceRouter?.state)
```

For hash mode, links must use `href="#/tutorial"`. For history mode, the server must return the HTML shell for direct requests such as `/tutorial`; otherwise refresh produces a server `404`. When changing routes, verify that the previous component's `beforeUnmount` runs and that animation frames, timers, event listeners, and signal subscriptions are released.

## Signals and reactivity problems

Use component `data()` for local state and explicit signals for state shared by browser modules. If a signal effect runs after a page is gone, keep the cleanup function and call it from `beforeUnmount`:

```js
const stop = status.subscribe(value => {
  element.textContent = value
})

// Later, when the component is destroyed:
stop()
```

Do not store secrets, permissions, or trusted authorization decisions in client signals. The Python server remains authoritative.

## Vercel build fails

Read the first error from `vercel logs`. Common fixes include:

```toml
requires-python = ">=3.11"
dependencies = ["flaxon", "Jinja2>=3.1"]
```

If setuptools reports multiple top-level packages, explicitly declare Python packages in `pyproject.toml`; do not let `public/`, `static/`, or `templates/` be discovered as Python packages.

## Neon returns no results

```bash
curl https://your-app.vercel.app/api/health
curl https://your-app.vercel.app/api/stats
```

The database must be configured, the schema must exist, and a URL must be seeded and crawled. Empty results are different from a database error: empty search returns a successful response with zero results.

## PWA shows an old UI

Increment the service-worker cache name after generated runtime changes, redeploy, and hard-refresh. In DevTools Application, unregister the worker and delete Cache Storage only while diagnosing local stale-cache behavior.

## The fix works locally but not on Vercel

Compare the three environments instead of assuming the source is identical:

```bash
python build.py
curl -I http://127.0.0.1:5000/static/js/App.js
vercel logs your-deployment-url
curl -I https://your-app.vercel.app/static/js/App.js
```

Check Python version, dependency installation, environment variables, build output, static rewrites, case-sensitive paths, service-worker caches, and external CDN availability. The Vercel build must run the same Teloce build command as local development.

## Data-feature troubleshooting

- If `v-virtual-for` renders nothing, inspect the generated module for
  `data-teloce-virtual-for`, confirm the collection is an array/object, and
  give every row a stable `:key`. The container must have a non-zero height
  and `overflow: auto`.
- If a table is empty, check that the `v-data-table` value contains `rows` and
  `columns` and that the shared `data.js` and `table.js` files were deployed
  beside `teloce-runtime.js`.
- If a CSV row is wrong, check quoted commas/newlines and enable `strict` plus
  `onRowError`. Date coercion returns `Date` objects in the browser; serialize
  them explicitly when sending them back to Python.
- If `poll` or `live` keeps retrying, inspect the endpoint status, CORS,
  WebSocket origin policy, and browser network panel. Cleanup is expected on
  unmount; it does not hide server authorization or transport errors.
- If `v-memo` appears stale, its key does not include all values read by the
  subtree. Remove it temporarily, then add a complete key.
- If static rendering fails, pass a Jinax/Jinja-compatible engine and list
  every server-rendered child in `components`. Static rendering intentionally
  does not run browser scripts or discover arbitrary imports.

## Bug-report checklist

Include Teloce-Py/Python versions, OS, command, first compiler diagnostic, browser console error, failing network request and response, and a minimal `.vel` file. Never include database URLs, cron secrets, cookies, or private data.

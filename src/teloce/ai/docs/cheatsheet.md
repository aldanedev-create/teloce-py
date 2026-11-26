# Teloce application cheatsheet

This is a practical reference for building a complete Python application with
`.vel` components. The usual division is:

```text
Python framework: routes, APIs, auth, database, HTML shell
Teloce component: browser state, interaction, DOM, component styles
Browser: executes generated JavaScript
```

## 1. Project layout

```text
my-app/
  app.py
  templates/index.html
  static/js/App.vel
  static/js/components/
  static/css/                 # optional global CSS
  requirements.txt
  dist/                       # generated; deploy this directory
```

## 2. Complete component

```html
<template>
  <main class="app">
    <h1>{{ title }}</h1>
    <p v-if="loading">Loading...</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <ul v-else>
      <li v-for="task in tasks" :key="task.id">
        <label>
          <input type="checkbox" v-model="task.done" @change="save(task)" />
          <span :class="{ done: task.done }">{{ task.name }}</span>
        </label>
      </li>
    </ul>
    <form @submit.prevent="addTask">
      <input v-model="draft" placeholder="New task" />
      <button :disabled="!draft.trim()">Add</button>
    </form>
  </main>
</template>

<script>
export default {
  data() {
    return { title: "Tasks", tasks: [], draft: "", loading: true, error: "" };
  },
  mounted() { this.load(); },
  computed: {
    remaining() { return this.tasks.filter((task) => !task.done).length; }
  },
  methods: {
    async load() {
      try { this.tasks = await fetch("/api/tasks").then((r) => r.json()); }
      catch (error) { this.error = "The API could not be reached."; }
      finally { this.loading = false; }
    },
    async addTask() {
      const task = await fetch("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: this.draft }) }).then((r) => r.json());
      this.tasks.push(task); this.draft = "";
    },
    async save(task) { await fetch(`/api/tasks/${task.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(task) }); }
  }
};
</script>

<style scoped>
.app { max-width: 48rem; margin: 3rem auto; font-family: system-ui; }
.done { text-decoration: line-through; opacity: .6; }
.error { color: #b42318; }
</style>
```

## 3. Template reference

| Need | Original Teloce API | Alias |
|---|---|---|
| Interpolation | `{{ title }}` | `{{ title }}` |
| Condition | `<if condition="ready">...</if>` | `v-if="ready"` |
| Else branch | adjacent conditional content | `v-else-if`, `v-else` |
| List | `<for each="item in items">...</for>` | `v-for="item in items"` |
| Event | `@click="save"` | `v-on:click="save"` |
| Event modifier | `@submit.prevent="save"` | `v-on:submit.prevent="save"` |
| Attribute | `:title="title"` | `v-bind:title="title"` |
| Class | `:class="classes"` | `v-bind:class="classes"` |
| Visibility | `:show="visible"` | `v-show="visible"` |
| Form value | `:model="email"` | `v-model="email"` |
| Text | normal interpolation | `v-text="message"` |
| HTML | not recommended | `v-html="trustedHtml"` |

Original syntax is preserved. You can use either style in the same project.

## 4. Component script API

```js
export default {
  name: "TaskList",
  props: { projectId: { type: String, required: true } },
  data() { return { tasks: [] }; },
  computed: { count() { return this.tasks.length; } },
  watch: { tasks(next) { console.log(next.length); } },
  components: { TaskRow },
  methods: { refresh() {} },
  mounted() {},
  updated() {},
  unmounted() {}
};
```

Use `props` for parent input, `emits` for child-to-parent events, `computed`
for derived values, and `watch` for side effects. Do not place server secrets
in component state.

## 5. Components and imports

```html
<script>
import UserCard from "./components/UserCard.vel";
export default { components: { UserCard } };
</script>
<template><UserCard :user="user" /></template>
```

Use relative local imports. The project build resolves local dependencies and
emits the generated modules. Keep component names consistent with imports.

## 6. Signals

Normal component `data()` is reactive and is the recommended starting point.
For shared browser state, use `createSignal`, `createComputed`, and
`createEffect`; see [Reactivity](reactivity.md).

```js
const count = createSignal(0);
count.set(count() + 1);
const doubled = createComputed(() => count() * 2);
```

## 7. CSS

```html
<style scoped>
.card { padding: 1rem; }
</style>
```

Use scoped styles for component rules and global CSS for resets, fonts, and
design tokens. Never use `v-html` with unsanitized user content.

## 7a. Data-heavy UI

```html
<div v-virtual-for="row in rows" :key="row.id" item-height="40">{{ row.name }}</div>
<div v-data-table="{ rows: rows, columns: columns, pageSize: 20 }"></div>
<section v-scrolly @step="active = $event.detail.name">
  <article v-step="intro">Intro</article>
</section>
```

Use `v-for` for ordinary lists and opt into `v-virtual-for` for large lists.
Use `v-memo` only when its key includes every value the subtree reads. Load
CSV with `loadCsv` from the shared runtime, shape server records with
`to_frontend_data`, and use `poll`/`live` only with secured API endpoints.

## 8. Python page shell

```html
<!doctype html>
<html><body>
  <div id="app"></div>
  <script type="module">
    import { mount } from "/static/js/App.js";
    mount("#app");
  </script>
</body></html>
```

## 9. Run and build

Beginner workflow:

```bash
python app.py
```

Development server:

```bash
teloce dev
```

Production build:

```bash
python -m teloce build --out-dir dist --hash-assets --bundle --report build-report.json
```

## 10. Production checklist

- compile during CI, not on every request;
- serve generated assets from a static directory or CDN;
- use stable keys for repeated data;
- authenticate and authorize Python API routes;
- add CSRF protection to state-changing requests;
- sanitize HTML before `v-html`;
- keep source maps private when required;
- run Python and browser tests;
- pin Python and Teloce-Py versions;
- add error monitoring for Python and browser failures.

## 11. `teloce.config.json`

Keep this in the project root and commit it so local development, CI, and
deployment use identical paths and optimisation settings.

```json
{
  "compiler": { "source_maps": false, "target": "es2020" },
  "build": {
    "out_dir": "dist",
    "static_dir": "static",
    "clean": true,
    "minify": true,
    "shared_runtime": true,
    "tree_shake": true,
    "bundler": "minifyjs",
    "lazy_components": ["SettingsPage"]
  },
  "server": { "host": "127.0.0.1", "port": 5173, "hmr": true }
}
```

`python -m teloce build` compiles `static/js/App.vel` to
`dist/static/js/App.js` and writes `dist/static/teloce-runtime.js` once.
Generated components import that shared runtime instead of duplicating it.

## 12. Build commands

```bash
# Compile one self-contained component.
python -m teloce compile static/js/App.vel -o dist/static/js/App.js --source-map

# Normal configured project build.
python -m teloce build

# Production output and size report.
python -m teloce build --minify --hash-assets --report build-report.json --max-size 50000

# Optional final esbuild bundle/chunks (install esbuild in the app first).
python -m teloce build --bundle --bundler esbuild --minify --hash-assets

# Development tools.
python -m teloce dev
python -m teloce lint --strict
python -m teloce doctor
```

Use `compile` for a standalone experiment. Use `build` for imported
components, cached project builds, shared runtime output, and deployment.

## 13. Django admin + `.vel` dashboard

Django admin remains Django's permission-protected server UI. Use `.vel` for a
staff dashboard that reads authorized Django endpoints.

```python
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from .models import Product

@staff_member_required(login_url="/admin/login/")
def home(request):
    return render(request, "index.html")

@staff_member_required(login_url="/admin/login/")
def inventory_summary(request):
    products = list(Product.objects.values("id", "name", "sku", "stock"))
    return JsonResponse({"total_products": len(products), "products": products})
```

```html
{% load static %}
<div id="app"></div>
<script type="module">
  import { mount } from "{% static 'js/AdminDashboard.js' %}";
  mount("#app");
</script>
```

The complete tested project is [`examples/django-admin-vel`](../examples/django-admin-vel).
Do not replace server authorization, CSRF protection, or model validation with
browser checks.

## 14. TypeScript in `.vel`

```html
<script lang="ts">
interface CounterState { count: number; }
export default {
  data(): CounterState { return { count: 0 }; },
  methods: { increment(): void { this.count++; } }
};
</script>
```

Teloce removes common type-only syntax, but it does not type-check. For full
type checks and `.ts` utility modules:

```bash
npm install --save-dev typescript esbuild
npx tsc --noEmit
python -m teloce build --bundle --bundler esbuild --minify
```

Keep decorators, JSX/TSX, advanced type transformations, and path alias
resolution in TypeScript/SWC/esbuild rather than expecting Python to transform
the complete TypeScript language.

## 15. Quick diagnosis

| Symptom | Check |
| --- | --- |
| Blank page | Confirm HTML has `#app`, imports generated `.js` rather than `.vel`, and DevTools has no module error. |
| `404 App.js` | Run `python -m teloce build`; serve `dist/static`; match the template URL to the output. |
| `await` syntax error | Keep `async` before every method, lifecycle hook, or watcher that uses `await`. |
| CSS missing | Use `<style>` in `.vel` or serve global CSS separately; never mount the authored `.vel`. |
| `.ts` import fails | Bundle/transform it with esbuild or TypeScript; browsers do not run `.ts`. |
| API redirects/403 | Sign in and keep authorization in the Python view. |

For detailed diagnostics run `python -m teloce debug`, then use the
[debugging guide](debugging.md) and [troubleshooting guide](troubleshooting.md).

# Known issues and workarounds

Verified while building a real app (a Flask scrollytelling story editor) against teloce-py 0.3.4. Items marked
**fixed in source** are fixed in the teloce-py source tree after 0.3.4. If your installed version
(`teloce --version`) still shows the problem, use the workaround.

## `v-scrolly` does not start when steps are rendered later (fixed in source)

Steps created by `v-for`, `v-if` or async data appear after the `v-scrolly` element was bound, so no step was found and
nothing became active.

Workaround for older releases: bind an attribute that changes after mount, which makes Teloce bind again.

```html
<div v-scrolly :data-steps="ready ? items.length : 0" @step="active = $event.detail.name">
  <section v-for="item in items" :key="item.id" :data-v-step="item.name" tabindex="0">...</section>
</div>
```

```js
data() { return { active: "", ready: false }; },
mounted() { this.ready = true; }
```

In a loop use `:data-v-step="item.name"`. A plain `v-step="intro"` is the literal name.

## `v-model` on a `<select>` with looped options does not preselect (fixed in source)

The select was bound before its options existed, so the saved value stayed unselected (`selectedIndex` was -1).

Workaround for older releases:

```html
<select @change="item.level = Number($event.target.value)">
  <option v-for="(row, i) in rows" :key="row.id" :value="i" :selected="item.level === i">{{ row.label }}</option>
</select>
```

## Type checker: false "conflicts with local declaration" for imported signal helpers (fixed in source)

In a `<script lang="ts">` that used TypeScript syntax (for example `0 as number`) and explicitly imported `signal` or
`createSignal`, `teloce typecheck` reported `TS2440: Import declaration conflicts with local declaration`. The checker could
not see the import and declared the helper a second time. Workaround for older releases: remove the explicit import and
call the helper directly, or keep the import and avoid TypeScript-only syntax in that script.

## Props are not available inside `data()`

`data()` is called without props, so `this.myProp` is `undefined` there. Copy props in `created()`:

```js
data() { return { draft: null }; },
created() { this.draft = JSON.parse(JSON.stringify(this.story)); }
```

Render the form with `v-if="draft"`.

## `in:` / `out:` transitions on a `v-if` element can leave it on screen (open)

In a minimal component these transitions work. In one real app, a banner with `in:slide` and `out:fade` and `v-if` on a
computed value that changed after a poll stayed on screen after the value became false. Without the transition
attributes it disappeared correctly. The cause is not known.

Workaround: do not put transitions on such an element. Toggle a CSS class instead.

## Runtime-created elements are not styled by `<style scoped>`

`v-chart-annotation` creates its `<aside class="teloce-chart-annotation">` at runtime. Style it in a second `<style>` block
without `scoped`.

## Small API facts that are easy to get wrong

- `createScope()` has `get`, `post`, `request`, `call`, `track` and `dispose`. For PUT or DELETE use
  `scope.request({ method: "PUT", url, data })`.
- Call `scope.dispose()` from `unmounted()`.
- Import the network clients by package name: `import { http, action, createScope } from "teloce/runtime";` (fixed in
  source after 0.3.4). On older releases use the relative path: `"../teloce-runtime.js"` from `static/js/`,
  `"../../teloce-runtime.js"` from `static/js/pages/`.
- Calling an action with `curl` needs the header `X-Teloce-Action: 1`.
- A `use:` action is a function declared at the top of `<script>` (above `export default`). It receives the element
  and the parameters, and returns an object that may have `destroy()`.
- `.vel` changes need a rebuild. The Flask reloader watches Python files only. Restart, or use `teloce dev`.

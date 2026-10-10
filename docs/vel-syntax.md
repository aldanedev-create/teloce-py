# `.vel` syntax

A Single File Component has up to three sections:

```html
<template>...</template>
<script>export default { ... };</script>
<style scoped>...</style>
```

The original Teloce forms remain supported:

```html
<if condition="user">Welcome {{ user.name }}</if>
<for each="item in items" :key="item.id">{{ item.name }}</for>
<button @click.prevent="save">Save</button>
<input :model="email">
```

npm-style aliases are also supported:

```html
<p v-if="ready">Ready</p>
<li v-for="item in items" :key="item.id">{{ item.name }}</li>
<input v-model="email">
<button v-on:click="save">Save</button>
```

Component scripts use the Teloce object API: `data`, `methods`, `computed`, `watch`, lifecycle hooks, `props`, and `emits`. JavaScript is the component language. TypeScript is deliberately not required by the Python compiler.

Use `:class`, `v-bind:class`, object class maps, and scoped styles for presentation. Use `v-text` for escaped text and reserve `v-html` for trusted, sanitized HTML.

## Native form model synchronization

`v-model` initializes native controls from state and synchronizes later programmatic changes on both direct and fallback rendering paths. Bindings inside keyed `v-for` rows use the row's live scope. You do not need to re-key a form merely to clear its fields.

```html
<input v-model="form.name">
<input v-model.trim="form.note">
<input v-model.number="form.quantity">
<input v-model.lazy="form.draft">
```

`.trim` and `.number` normalize writes to state while preserving equivalent text already in the control, including trailing spaces and number formatting. `.lazy` commits on `change`; an unrelated rerender preserves the focused, uncommitted edit, while a changed model value synchronizes from state. Native IME composition delays model writes and DOM value replacement until composition ends (or the later `change` for `.lazy`). Unknown/undefined model values leave existing input untouched; `null` clears ordinary text controls.

Boolean/array checkboxes, radio groups, single-selects and multi-selects synchronize on initial mount and state changes. Listeners, including composition handlers, are removed when controls unmount. These guarantees describe native controls, not a new custom-component `v-model` contract.

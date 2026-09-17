# Lesson 38: automatic components and `$attrs`

Teloce registers a local component when a parent imports its `.vel` file. The
`components: { Card }` option is therefore optional for normal imports. Keep
it when you want an explicit public name or when maintaining older code.

Create `static/js/components/Card.vel`:

```html
<template>
  <article class="card" v-bind="$attrs">
    <h2>{{ title }}</h2>
    <slot />
  </article>
</template>
<script>
export default { props: { title: { type: String, required: true } } };
</script>
<style scoped>
.card { padding: 1rem; border: 1px solid #dbe4ee; border-radius: .75rem; }
</style>
```

Create `static/js/App.vel`:

```html
<template>
  <main><Card title="Welcome" id="intro" class="featured" aria-label="Greeting">Hello</Card></main>
</template>
<script>import Card from "./components/Card.vel";</script>
```

Build with `teloce build`. The generated parent imports `Card.js`, and the
child root receives undeclared `id`, `class`, `aria-*`, and `data-*` values.
Declared props are not duplicated into `$attrs`; class values are merged.
The build manifest records each source, generated module, CSS file, imports,
and lazy flag in `dist/manifest.json`.

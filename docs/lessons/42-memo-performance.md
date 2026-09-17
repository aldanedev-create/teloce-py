# Lesson 42: skip unchanged subtrees with `v-memo`

`v-memo` stores a small key value on an element. When the rendered key is
unchanged, DOM reconciliation skips that element and its descendants.

```html
<template>
  <section>
    <input v-model="query" placeholder="Filter">
    <article v-for="card in cards" :key="card.id" v-memo="card.id + ':' + card.version">
      <h2>{{ card.title }}</h2>
      <p>{{ card.description }}</p>
    </article>
  </section>
</template>
<script>
export default { data() { return { query: "", cards: [] }; } };
</script>
```

The memo key must include every value used by the subtree. If the card title,
description, or version changes, include that value or remove `v-memo`.
Memoization is an optimization, not a replacement for `:key`; use both for
reordered data. Measure before and after with the browser performance tools.

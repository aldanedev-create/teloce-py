# Lesson 39: virtual lists for large datasets

Use ordinary `v-for` for normal lists. Use `v-virtual-for` only when a list
can contain thousands of rows. It keeps a bounded number of row elements in
the DOM and requires a stable key for predictable focus and identity.

```html
<template>
  <div class="results" v-virtual-for="row in rows" :key="row.id" item-height="44" overscan="5">
    <button @click="select(row.id)">{{ row.title }}</button>
  </div>
</template>
<script>
export default {
  data() { return { rows: [], selected: null }; },
  methods: { select(id) { this.selected = id; } }
};
</script>
<style scoped>
.results { height: 28rem; overflow: auto; }
</style>
```

`item-height` is the estimated row height in pixels and `overscan` adds rows
outside the viewport to reduce flicker. Rows are keyed with `row.id`; do not
use the index when rows can be sorted or inserted. The browser runtime also
restores focus by key when the visible window changes. Teloce emits a warning
when a virtual loop has no key.

# Lesson 40: sortable and filterable tables

For a ready-made table, put `v-data-table` on an empty element. Its value is
an object with `rows`, `columns`, `pageSize`, and optional `key`. The shared
runtime imports the table helper only for components that use it.

```html
<template>
  <section>
    <h1>People</h1>
    <div v-data-table="{ rows: people, columns: columns, pageSize: 10 }"></div>
  </section>
</template>
<script>
export default {
  data() {
    return {
      people: [{ id: 1, name: "Ada", team: "Core" }, { id: 2, name: "Lin", team: "Web" }],
      columns: [{ key: "name", label: "Name" }, { key: "team", label: "Team" }]
    };
  }
};
</script>
```

Users can type in the filter and click sortable headers. Rows are keyed by
`id` (or `key`) and paginated so a table does not create an unbounded DOM.
For a custom large scrolling layout, combine `v-virtual-for` with your own
headers. From JavaScript, `createDataTable(element, options)` returns
`setRows`, `getVisibleRows`, `exportCsv`, and `unmount`.

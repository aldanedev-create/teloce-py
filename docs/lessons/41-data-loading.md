# Lesson 41: CSV loading and Python data shaping

The browser helper parses quoted CSV/TSV, headers, multiline fields, and
common number/boolean/date values. It has no pandas dependency.

```html
<template><ul><li v-for="row in rows" :key="row.id">{{ row.name }}: {{ row.amount | number }}</li></ul></template>
<script>
import { loadCsv } from "../teloce-runtime.js";
export default {
  data() { return { rows: [] }; },
  async mounted() {
    this.rows = await loadCsv("/static/data/report.csv", {
      types: { id: "number", amount: "number", published: "date" }
    });
  }
};
</script>
```

For server data, keep aggregation and access control in Python:

```python
from teloce import to_frontend_data

rows = to_frontend_data(
    report_rows,
    {"id": "integer", "name": "string", "amount": "number"},
)
return jsonify({"rows": rows})
```

`to_frontend_data` accepts mappings, dataclasses, tuples with a schema, and a
pandas DataFrame when pandas is already installed by your application.
pandas remains optional; it is not installed with Teloce. A supplied schema
also acts as an allow-list so backend-only columns are not exposed.

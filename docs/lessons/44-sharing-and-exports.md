# Lesson 44: shareable state and exports

Declare query state in the component options. Teloce hydrates it from the URL
on mount and updates the query string with `history.replaceState`.

```html
<script>
export default {
  data() { return { category: "all", page: 1 }; },
  queryState: {
    category: { type: "string", key: "category" },
    page: { type: "number" }
  }
};
</script>
```

The URL becomes `?category=climate&page=2`, so a reader can bookmark the exact
view. Only declare state that is safe to expose. Query state is not a secret
storage mechanism.

Export rows from a method or action:

```js
import { downloadRowsAsCsv, exportChartToPng } from "../teloce-runtime.js";
downloadRowsAsCsv(this.rows, "filtered-report.csv");
exportChartToPng(document.querySelector(".chart"), "chart.png");
```

The PNG helper requires a canvas; the SVG helper requires an SVG element.
Browser download permissions and cross-origin canvas rules still apply.

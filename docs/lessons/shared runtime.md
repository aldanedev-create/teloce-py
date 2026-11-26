# Shared runtime and small component bundles

Project builds use a shared runtime by default. Instead of inserting the same
runtime helpers into every compiled `.vel` component, Teloce writes one file:

```text
dist/static/teloce-runtime.js
```

Each generated component imports the shared helpers with a relative ES-module
path. For example, `static/js/App.vel` becomes `dist/static/js/App.js`, which
imports `../teloce-runtime.js`.

In your own `<script>` you do not have to write that path. Import by package name and the build
rewrites it for the component's folder depth:

```js
import { http, action } from "teloce/runtime";   // becomes "../teloce-runtime.js" in App.js
```

`teloce/network`, `teloce/signals`, `teloce/data`, `teloce/scheduler` and `teloce/table` point at the
individual modules. This works in project builds (`teloce build`, `teloce dev`, `build_project`). A component
compiled on its own, without a shared runtime, keeps the specifier unchanged.

This is why a project build is preferable to compiling individual files when
shipping an application. A single-file `teloce compile App.vel` result stays
self-contained for quick experiments; `teloce build` is the production path.

Use this configuration for the normal optimised setup:

```json
{
  "build": {
    "minify": true,
    "shared_runtime": true,
    "tree_shake": true
  }
}
```

The browser downloads the shared runtime once and reuses it for every page and
lazy-loaded component. Use `teloce build --report` to inspect the generated
file sizes, and use `--max-size 50000` to receive a warning when a generated
asset grows beyond the chosen budget.

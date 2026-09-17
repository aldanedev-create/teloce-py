# Public API

## Compile one component

```python
from pathlib import Path
from teloce.compiler import compile_file

result = compile_file("static/js/App.vel")
if not result["success"]:
    raise RuntimeError(result["diagnostics"])
Path("static/js/App.js").write_text(result["code"], encoding="utf-8")
```

## Build a project

```python
from teloce.build import build_project
result = build_project(".", options={"source_maps": True, "dev": False})
```

The result contains build counters and generated files. The CLI is the recommended interface for application teams.

## Result shape

`compile_file` returns a dictionary containing `success`, generated `code`,
generated `css`, an optional source `map`, `diagnostics`, and parsed component
information. Always check `success` before writing output. `build_project`
returns build statistics and errors for a whole project.

## Transition and animation directives

`transition:`, `in:`, `out:`, and `animate:` (see [Directives](directives.md#transitions-and-animations))
affect the generated `code` but need no separate API call — they compile
through the normal `compile()` / `compile_file()` / `build_project()` path.

The generator inspects each component's rendered template and only inlines
the built-in helpers (`fade`, `slide`, `scale`, and the FLIP logic behind
`animate:flip`) that the component actually references. A component with no
transition directives emits none of that code, so `len(result["code"])` does
not grow for components that don't use them.

```python
from teloce.compiler import compile

result = compile(source, filename="Banner.vel")
uses_transitions = 'data-teloce-in=' in result["code"] or 'data-teloce-out=' in result["code"]
```

There is no separate transitions flag in `teloce.config.json` — this is
always on, driven entirely by whether a component's template contains
`transition:`/`in:`/`out:`/`animate:` attributes.

## Server integration

The API is useful for custom build systems. Most applications should compile
before startup or in CI, write output to `dist/`, and configure the framework
to serve that directory. Do not compile arbitrary user-supplied `.vel` files
inside a public request without an explicit sandbox and resource policy.

## Compiler API

Use `compile()` when the `.vel` source is already in memory and `compile_file()`
when it is on disk. Both return the same result shape.

```python
from teloce.compiler import compile

source = """<template><button @click="count++">{{ count }}</button></template>
<script>export default { data() { return { count: 0 }; } };</script>
<style scoped>button { padding: .6rem; }</style>"""

result = compile(source, filename="Counter.vel", source_maps=False)
if not result["success"]:
    raise RuntimeError(result["diagnostics"])

javascript = result["code"]
css = result["css"]
```

`code` is an ES module, `css` is generated component CSS, and `map` is present
when source maps are enabled. Always check `success` before serving output.

## Project build API and shared runtime

`build_project()` scans `.vel` files, resolves local imports, writes generated
modules/assets, and returns a report. Project builds use one shared runtime by
default, so components do not each embed reactive DOM/event helpers.

```python
from pathlib import Path
from teloce.build import build_project

root = Path(__file__).resolve().parent
result = build_project(
    root,
    out_dir=root / "dist",
    options={
        "static_dir": "static",
        "dev": False,
        "source_maps": False,
        "minify": True,
        "shared_runtime": True,
        "tree_shake": True,
    },
)
if result["failed"]:
    raise RuntimeError(result["errors"])
print(result["runtime"])  # static/teloce-runtime.js
```

With the standard layout, `static/js/App.vel` becomes `dist/static/js/App.js`
and imports `../teloce-runtime.js`. Configure the framework to serve
`dist/static`, not the authored `static` directory. Disable `shared_runtime`
only when an intentionally self-contained file is required.

## `teloce.config.json`

Teams should usually commit this configuration and invoke the CLI:

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
    "bundler": "teloce"
  }
}
```

```bash
python -m teloce build
```

Use the Python API when a framework startup script or custom deployment
pipeline needs explicit control. Use the CLI for repeatable team builds.

## Build result shape

| Field | Meaning |
| --- | --- |
| `total` | Source components discovered. |
| `compiled` | Components compiled in this build. |
| `skipped` | Unchanged components reused from cache. |
| `failed` | Components that could not compile. |
| `files` | Generated file metadata and sizes. |
| `errors` | Per-file build failures. |
| `runtime` | Shared runtime path when enabled. |
| `runtime_size` | Shared runtime size in bytes when enabled. |

Use `python -m teloce build --report build-report.json --max-size 50000` for
a machine-readable report and size-budget warnings.

## Framework mount and TypeScript boundary

Every framework renders an HTML shell containing a mount node and generated
module import. Teloce does not replace routing, authentication, CSRF, or the
database layer.

```html
<div id="app"></div>
<script type="module">
  import { mount } from "/static/js/App.js";
  mount("#app");
</script>
```

For Django templates, use `{% load static %}` and `{% static 'js/App.js' %}`.
The verified [`django-admin-vel` example](../examples/django-admin-vel) keeps
the model and staff authorization in Django while a `.vel` dashboard reads a
staff-only JSON endpoint.

`<script lang="ts">` supports limited type erasure for common annotations,
interfaces, assertions, and simple enums. It is not full TypeScript checking.
Run `npx tsc --noEmit` for diagnostics and use esbuild/SWC for advanced
TypeScript or `.ts` browser modules. See [JavaScript and TypeScript tooling](javascript-typescript-tooling.md).

## Data and large-dataset APIs

Project builds copy browser data helpers beside the shared runtime:

```js
import { loadCsv, parseDelimited, downloadRowsAsCsv, exportChartToPng } from "../teloce-runtime.js";
```

`loadCsv(url, options)` parses CSV or TSV and supports `headers`, `delimiter`,
`tsv`, `types`, `strict`, and `onRowError`. `to_frontend_data(records, fields)`
is the Python-side equivalent for mappings, dataclasses, tuple rows, and a
pandas DataFrame when pandas is already part of the host application. pandas
is optional and is not installed with Teloce. A supplied field schema is also
an allow-list for backend-only columns.

Use `v-virtual-for="row in rows" :key="row.id" item-height="40"` for bounded
DOM rendering. Existing `v-for` remains the normal list API. `v-memo` skips a
subtree when its evaluated key is unchanged. `v-data-table` attaches the
shared sortable/filterable table helper; the direct `createDataTable(element,
options)` API returns `setRows`, `getVisibleRows`, `exportCsv`, and `unmount`.

## Story, live, and DOM behavior

`v-scrolly` observes child `v-step` elements and emits `teloce:step`.
`v-chart-annotation` adds an accessible overlay to a chart container.
`poll="/api/data" interval="10000" poll-target="state.path"` fetches JSON
with visibility pausing, abort cleanup, and bounded retry delay. `live` accepts
a `ws:`/`wss:` URL or a name in `globalThis.__teloceLiveAdapters`; WebSocket
connections reconnect with backoff and are closed on unmount.

`use:name="params"` calls an action with the actual DOM element. Return a
cleanup function or `{ update(next), destroy() }`. Timers, observers, event
listeners, sockets, action cleanups, and child instances are disposed when a
component or branch is removed.

## Static components and embed mode

`await render_static_component(source, context, components={...}, engine=...)`
expands only explicitly allow-listed child `.vel` templates through a
Jinax/Jinja-compatible engine. It does not execute component scripts or follow
imports from markup. Set `build.embed.enabled` in `teloce.config.json` to
produce an iframe-friendly entrypoint with a validated aspect ratio and
optional chrome removal.

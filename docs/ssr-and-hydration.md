# Server rendering and hydration

Teloce can compile `.html` and `.vel` templates into browser modules and a separate, versioned server render program. The server renderer has no Flaxon dependency and never executes the component's JavaScript. Flaxon, Flask, or another host loads application data and passes an explicit public snapshot to it.

## Build an SSR entry

Put components in `ui/` and configure `teloce.config.json`:

```json
{
  "build": {
    "html_mode": true,
    "source_roots": ["ui"],
    "ssr": true,
    "ssr_entries": ["ui/App.html"],
    "bundle": true,
    "bundler": "minifyjs",
    "minifier": "minifyjs"
  }
}
```

Run `teloce build`. The build produces browser modules, scoped CSS, `.ssr.json` programs and `manifest.json`. Selected entries include their imported component dependencies. Other components still compile for browser use. Omitting `ssr_entries` validates every component for SSR. AST SSR requires the shared runtime, which is enabled by default.

Use the renderer independently:

```python
from teloce.server import Renderer

renderer = Renderer("dist")
result = renderer.render("ui/App.html", {"title": "Projects"})
# result.html, result.props_json, result.assets, result.diagnostics
```

Load the renderer once per build. Replace it after rebuilding. Entry names must exist in the manifest; the renderer does not import arbitrary component paths.

## Supported template expressions

The server compiler consumes Teloce's canonical template AST and expression AST. It emits validated JSON instructions rather than translating JavaScript with regular expressions or evaluating application Python objects.

Supported constructs include text interpolation, `v-if`/`v-else`, indexed `v-for`, keyed rows, `:attribute`, `v-text`, `v-show`/`v-hide`, imported child components, and default/named slots. Slots use the parent's public scope. Scoped CSS uses the same scope identifier as the browser compiler.

Expressions support public identifiers, plain arrays/objects, property and computed access, ternaries, arithmetic, comparisons, equality, `typeof`, `!`, `&&`, `||`, and `??`. Empty arrays and objects are truthy; booleans remain distinct from numbers under `===`. Optional property access is supported, but mixed optional/nonoptional chains are rejected: use explicit conditionals instead. Template literals, arbitrary calls, assignments, spreads, dynamic components, virtual lists and raw `v-html` are outside the initial SSR subset. `v-model` remains browser-only in this release.

String methods are `toUpperCase()`, `toLowerCase()`, `trim()`, `includes(value)`, `startsWith(value)` and `endsWith(value)`. Arrays support `includes(value)` and `join(separator)`. These methods accept only the documented arguments; position arguments and optional method calls are not supported. Expressions with unsupported syntax fail during the build with an original component location. Public values missing at request time raise `SSRRenderError` with the affected template location.

This is a tested subset of JavaScript semantics, not a general JavaScript engine. Server/client parity fixtures run against Node, and Chromium tests cover development and production output.

## Public data and security

Pass a plain dictionary containing only JSON-compatible values. Nested objects must be plain dictionaries/lists, not models, functions, dates, or arbitrary application objects. Convert dates, money and large integers to strings explicitly. Nonfinite numbers and numbers outside JavaScript's safe range are rejected. Do not pass an entire user/database object or server settings: every public value is also sent to the browser.

Interpolations and attributes are escaped for their HTML contexts. Script props escape `<`, `>`, `&` and Unicode line separators. URL bindings reject executable schemes and backslashes; inline event attributes and raw HTML are rejected. Rendering has limits on data depth/items, expression size/nodes, component nesting, iterations, and output size. SSR does not run `data()`, methods, or lifecycle hooks on the server. Supply every server-rendered state field explicitly, including child props.

## Hydrate an existing root

Your host injects the server HTML and the **same public snapshot** into a marked root:

```html
<div id="app" data-teloce-ssr="1">...server HTML...</div>
```

Then import `hydrate` from the manifest's client entry and call `hydrate("#app", publicProps)`. `hydrate` is also available on the component's default export. The shared runtime reconciles matching nodes in place, initializes props, binds events once, and hydrates imported child components. Keyed rows retain their identity.

Signals remain signals. If client `data()` returns `count: signal(0)`, seed it with `{"count": {"value": 4}}`; hydration writes its value and subscribes to subsequent changes. Signal helpers are provided by the compiler's runtime imports; no manual import is needed in the normal component workflow.

Matching input nodes preserve the value, selection and focus present before startup. Replaced nodes cannot preserve their identity. Because `v-model` is not in the SSR subset, restored input values do not automatically become application state; bind your input handler deliberately or keep that form client-only.

Structural/version mismatches emit a `hydration` diagnostic and reconcile the affected component. Browser-only lifecycle hooks still run. Avoid fetching the same data again in `mounted()` when the public snapshot already contains it. `unmount()` removes event handlers, signal subscriptions and child instances. SPA routers can continue using ordinary client mounts for later navigation.

## Prerender and cache

After an SSR build, create `public.json` containing the public snapshot:

```bash
teloce prerender ui/App.html --data public.json --build-dir dist --output index.html
```

The command writes hydrated HTML, safe props and stylesheet links inside the build directory. Serve `dist/` at the site root. Unsupported/missing entries return a nonzero status.

`Renderer("dist", cache_size=32)` enables an optional LRU render cache. Its key includes the entry and complete public snapshot; it is limited to 256 entries and 8 MB of serialized data/output. The default is disabled. It does not cache authentication, HTTP responses, data-loading queries or secret context. Recreate the renderer after each build.

## Development diagnostics

The runtime exposes `onTeloceError(listener)` and `reportTeloceError(error, detail)` from the shared runtime, and dispatches a `teloce:error` browser event. Reports include category, component and available original expression locations. A failing reporter cannot interrupt application updates. Hosts can subscribe without making Teloce depend on them.

Flaxon's adapter adds the development overlay, source-map resolution and dashboard transport. See Flaxon's SSR/debugger guide. Source maps resolve the nearest emitted mapping; they are not a guarantee of token-level accuracy for every transformed expression.

## Legacy compatibility

`ssr: "legacy"` retains Jinax/Jinja `.html` artifacts. Existing `teloce.ssr.render_ssr()` remains a legacy adapter and does not acquire the explicit hydration contract. The new `ssr: true` build uses AST programs. `teloce build --static` retains legacy output unless `ssr` is explicitly configured. Migrate a host to `teloce.server.Renderer` before switching its artifact reader.

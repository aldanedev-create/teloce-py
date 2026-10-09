# Direct DOM updates

Teloce-Py can compile a safe subset of a `.vel` component into a targeted
update plan. Instead of rebuilding the component's HTML when one state field
changes, the shared runtime keeps the existing nodes and updates only the text
node or DOM property that depends on that field.

This feature is opt-in while the compatibility renderer remains the safety
net for unsupported components and layouts.

## Enable it

In `teloce.config.json`:

```json
{
  "build": {
    "shared_runtime": true,
    "direct_dom_updates": true
  }
}
```

Or enable it for one production build:

```bash
teloce build --direct-dom-updates
```

Use the compatibility renderer explicitly when debugging a migration:

```bash
teloce build --no-direct-dom-updates
```

CI can make the optimization boundary strict:

```bash
teloce build --direct-dom-updates --strict-direct-dom
```

In strict mode, an unsupported expression is `E3001` and stops the build. In
the normal mode it is `W3001` and the component safely uses compatibility
reconciliation.

The shared runtime is required because the generated component imports the
single scheduler, reactive proxy, lifecycle, and DOM-update implementation
from the build's `teloce-runtime*.js` file.

## What is optimized

This component is a direct-update candidate:

```html
<template>
  <section>
    <h1>{{ title }}</h1>
    <p :class="tone">A stable paragraph.</p>
    <button @click="count++">Clicked {{ count }} times</button>
  </section>
</template>

<script>
export default {
  data() {
    return { title: "Hello", tone: "calm", count: 0 };
  }
};
</script>
```

The compiler records each expression, its conservative dependency roots, and
the `.vel` source location. A change to `count` updates the button's text
binding; it does not recreate the `section`, `h1`, or paragraph. Multiple
synchronous changes are collected into one microtask update. Bindings are indexed
by dependency; simple member reads use generated functions, while complex
expressions keep the safe evaluator.

Nested state is tracked at its root:

```html
<p>{{ user.name }}</p>
```

Changing `state.user.name` invalidates the `user` binding. Computed bindings
also include the state roots read by the computed body, so this remains fresh:

```html
<p>{{ displayName }}</p>
```

```js
computed: {
  displayName() {
    return this.firstName + " " + this.lastName;
  }
}
```

## Bindings and cleanup

Direct updates cover text interpolation, `:class`, `:style`, normal dynamic
attributes, boolean properties, `v-model`, and forwarded binding metadata. The
existing event/directive binder remains responsible for event modifiers,
actions, filters, transitions, plugins, and cleanup. Unmounting a component
clears retained text/property references, child instances, event listeners,
actions, observers, and timers registered through the runtime.

Use the same DOM identity check in a browser regression test:

```js
const heading = document.querySelector("h1");
app.state.title = "Updated";
await Promise.resolve();
console.assert(heading === document.querySelector("h1"));
console.assert(heading.textContent === "Updated");
```

## Structural regions and fallback

Supported outer `v-if` and regular `v-for` blocks have comment-delimited
regions. A change to their dependencies renders and patches that region;
unrelated text or attribute changes use direct bindings without rebuilding
those regions. Nested blocks reconcile within their outer region.

The region reconciler matches `data-teloce-key`, moves existing rows, creates
new rows, and cleans up removed subtrees. Retained focused inputs preserve
focus and selection during keyed moves. Always provide stable keys:

```html
<li v-for="item in items" :key="item.id">{{ item.name }}</li>
```

A changed list still renders its region. Child components, projected slots,
virtual lists, integration directives, and restricted layouts such as tables,
selects, and SVG retain the compatibility renderer. Both paths share lifecycle
and cleanup behavior. `I3001` describes structural reconciliation; it does not
promise every component uses a targeted region.

Without a key, `W2002` warns that row identity cannot be guaranteed during
reorder. Virtual lists emit `W2001` without a stable key.

## Unsupported expressions

The direct plan is conservative. Expressions containing constructs the shared
safe evaluator cannot analyze, such as inline arrow functions, `new`, `await`,
generators, template literals, or statement separators, cause the whole
component to use the compatibility renderer and produce `W3001` with the
source line and column. This is intentional: a slower correct update is safer
than a direct binding that can become stale.

Move complex work into a method or computed value, or turn the feature off for
that build if the expression needs full JavaScript evaluation:

```json
{ "build": { "direct_dom_updates": false } }
```

## Source metadata and diagnostics

With source maps enabled, compiled results include standard VLQ mappings plus
an `x_teloce.direct_plan` extension containing each binding's source line and
column. This metadata is useful to debugger tooling and build reports even
when minification changes generated line numbers.

The compiler distinguishes:

- `W3001`: direct analysis was unsafe; compatibility rendering is used;
- `I3001`: a structural block uses keyed compatibility reconciliation;
- `W2001`: virtual loop has no stable key;
- `W2002`: regular loop has no stable key.

## Optional preprocessing

Preprocessors run before the `.vel` SFC parser and are useful for a project
specific source transform or a separately installed TypeScript/Sass step. They
are not required for ordinary JavaScript and CSS. Register one through the
Python compiler API:

```python
from teloce.compiler.compiler import Compiler

def replace_tokens(source, filename=None):
    return source.replace("__APP_TITLE__", "Learning dashboard")

result = Compiler({"preprocessors": [replace_tokens]}).compile(
    source,
    "static/js/App.vel",
)
assert result["success"]
```

A preprocessor can also be an object with `process(source, filename=...)` or
`transform(...)`, and may return source text, `(source, metadata)`, or a
`{"code": source}` mapping. Failures are reported as `E1100`/`E1101` with the
component filename and a suggested correction; they do not crash a dev
server. Keep transforms deterministic and preserve line structure where
possible so source diagnostics remain useful.

Run the compiler-level tests and browser tests before changing the default for
a production application:

```bash
python -m pytest -q tests/compiler/test_compiler.py tests/integration/test_direct_dom.py
```

The direct path is an optimization, not a new template language. Existing
`.vel` syntax and the original runtime API remain compatible.

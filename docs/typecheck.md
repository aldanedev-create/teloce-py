# Type checking

Type checking requires Python 3.11+; the rest of Teloce continues to support Python 3.10.

`teloce typecheck` type-checks the TypeScript in your components and the expressions in your templates.
It uses [pytscheck](https://pypi.org/project/pytscheck/), which bundles Microsoft's native TypeScript compiler; no Node.js is needed.

```bash
pip install "teloce-py[typecheck]"
teloce typecheck                 # checks ./ui and ./modules/*/ui
teloce typecheck ui --json       # machine-readable output for CI
teloce typecheck --no-templates  # only <script lang="ts"> blocks and .ts files
```

Exit codes: `0` no errors, `1` type errors found, `2` not available or bad input (for example pytscheck is not installed).

Flaxon or other tools can call `teloce.typecheck.check_project()` with their registered UI folders. This package does not automatically register a `management.py typecheck` command.

## What is checked

* `<script lang="ts">` blocks and `.ts` files, with errors reported at the original line and column.
* Template expressions: `{{ }}`, `:attr`, `v-if`, `v-else-if`, `v-show`, `v-text`, `v-html`, `v-model`, `v-for` sources and `@event` handlers.
  Names are resolved against the component's `data()`, `computed`, `methods` and `props`, and `v-for` variables take their
  type from the iterated value.

```text
ui/shop/Shop.html(7,30): error TS2551: Property 'lenght' does not exist on type 'Product[]'. Did you mean 'length'?
```

## Writing components that check well

Annotate the data you return from `data()` so templates get real types:

```ts
data() {
  const products: Product[] = [];
  return { products, query: "" };
},
```

Computed properties that read other computed properties need an explicit return type
(`total(): number { ... }`), as in other TypeScript component systems.

## Runtime features covered by regression tests

The adapter models all ten compiled lifecycle hooks (`beforeCreate`, `created`, `beforeMount`, `mounted`, `beforeUpdate`, `updated`, `activated`, `deactivated`, `beforeUnmount`, `unmounted`), component methods/computed state, `$attrs`, declared event names through `$emit`, and watchers for data properties. Watchers receive their data property's type and the component's `this` context.

Project-build signal helpers use the compiler's own auto-import decisions. `signal`/`createSignal`, `computed`/`createComputed`/`createMemo`, `effect`/`createEffect`, `batch`, `untracked`, `isSignal`, `isComputed`, `toSignal`, and `getValue` receive their runtime contracts. Signal reads, writes, updates and subscriptions retain the value type. Explicit imports and local declarations take precedence, and implicit helpers do not leak into ordinary TypeScript modules.

`v-if`, adjacent `v-else-if` and `v-else` preserve TypeScript narrowing for their bindings and descendant expressions, including loop scopes and void elements. Expression identifiers are resolved using the TypeScript AST, including arrow/function scopes, destructuring, comments, regular expressions and parameter defaults.

Host-generated globals, such as Flaxon's router or configured PWA controller, belong in your project's `.d.ts` declarations. Annotate nullable state and empty arrays explicitly, narrow caught errors, and check DOM event targets before accessing element-specific properties. Compilation alone is not a type-check pass.

## Coverage and runtime boundaries

| Feature | Checking behavior |
| --- | --- |
| TypeScript and JavaScript SFC scripts | Native TS/JS checking, including JSDoc; diagnostics map to the original component. |
| Script export forms | Direct options objects, local named options objects and single-call wrappers such as `defineComponent({...})` retain context. |
| Imported children | Default/named imports, barrel exports and project aliases resolve through TypeScript and carry public prop contracts. |
| Dynamic components | Registered string-name selectors carry required/type-checked props. Declare the finite union of possible names; unrestricted runtime strings cannot identify a contract. Props must satisfy every possible selected component. |
| Default/named slots | Supplied slot names are validated against the child's declared `<slot>` outlets; parent content and child fallback expressions use their own contexts. |
| Diagnostics | Script offsets, expression occurrences, UTF-16 columns and HTML attribute entities retain original positions. |

Teloce's current runtime does not implement scoped slot-prop functions; the checker does not invent such a runtime feature. Unknown JavaScript/external component contracts and values explicitly typed `any` retain JavaScript/TypeScript's normal limits. Array-style props have no supplied value types; use object-style props for strict contracts. Dynamic component names must be a declared finite union to verify their props. Packages supplying only permissive declarations cannot be checked beyond those declarations. These are information/runtime boundaries, not a claim that arbitrary dynamic programs can be statically proven correct.

Static attributes are strings; constructor-array props infer unions. Custom prop validators execute at runtime and cannot generally be proved statically. Template HTML remains parsed separately from JavaScript expressions, so malformed/unsupported template syntax must also pass the compiler's build checks. Pin PyTSCheck in CI because its bundled native compiler is a preview build.

## Python integration

```python
from teloce.typecheck import check_project

result = check_project(["ui", "modules/shop/ui"])
for finding in result.findings:
    print(finding.format())
```

Supply existing directories. Empty input and compiler/configuration/I/O failures raise `TypecheckUnavailable`; the CLI reports exit code 2. Declaration files (`.d.ts`) under these directories are included. Checks inherit the nearest ancestor `tsconfig.json` automatically, including extended compiler options, JSX, strictness and import aliases, and resolve real project files and installed declarations. Without a config, checking uses strict ES2022/bundler defaults. `--no-strict` explicitly overrides strictness. Generated files use a temporary workspace and never overwrite project files; conflicting generated filenames are errors.

For multiple source folders, pass the application's root explicitly:

```python
result = check_project(["ui", "modules/shop/ui"], project_root=".", tsconfig="tsconfig.json")
```

The `tsconfig` argument is optional. CLI equivalents are `--project-root .` and `--tsconfig tsconfig.json`. Relative configuration paths resolve against the project root. PyTSCheck checks project files selected by the config in addition to generated components, so findings may also reference files outside the UI folders. Installed npm declarations are resolved from the consuming project's `node_modules`; Python declaration packages may expose declarations in the project. No npm packages are installed automatically. The adapter enables JavaScript/JSDoc checking (`allowJs` and `checkJs`) and TypeScript extension imports for generated sources, in addition to disabling emission; other configured compiler rules are retained.

Locations are 1-based; columns use UTF-16 coordinates. Template property errors use the generated expression occurrence when available; other template diagnostics point to the expression or attribute start. Expression references use a TypeScript AST; template extraction and HTML entity/source-position mapping still have limits.

## Typed object-style props

```ts
export default {
  props: {
    title: { type: String, required: true },
    count: { type: Number, default: 0 },
    subtitle: { type: String }
  },
  methods: {
    label() { return this.title.toUpperCase(); }
  }
};
```

`title` is a string, `count` is a number, and `subtitle` is `string | undefined`. Template expressions use the same types.

## Props passed between components

Import a TypeScript or JavaScript child component directly or through a named/barrel/alias import that resolves to a generated `.html` or `.vel` contract under the checked UI roots. The checker uses its prop declaration for template attributes and bindings:

```html
<script lang="ts">
import Counter from "./Counter.html";
export default {
  components: { Counter },
  data() { return { count: 3 }; }
};
</script>
<template>
  <Counter label="Items" :count="count" />
</template>
```

If `Counter` requires a string `label` and accepts a numeric `count`, a missing `label`, `:count="'hello'"`, or a misspelled `:coutn="count"` reports a finding against the parent template. Optional props and props with defaults may be omitted; `required: true` still requires a supplied value. Bindings inside `v-for` use the loop variable's type. Attribute findings map to the parent attribute's line/column; missing-prop findings point to the component tag.

Kebab-case attributes map to camelCase prop names (for example, `:project-name` supplies `projectName`), matching the runtime. Static attributes are strings (`count="3"` is not a number); use `:count="3"` and `:active="true"` for numeric/boolean values. Events, framework directives, and supported passthrough attributes (`class`, `style`, `id`, `key`, `ref`, `slot`, `role`, `tabindex`, `aria-*`, `data-*`) are handled separately from declared props. `--no-templates` disables these template checks.

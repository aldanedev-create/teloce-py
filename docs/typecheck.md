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

## Limits

* Only `lang="ts"` components are checked; plain `<script>` components are skipped.
* Array-style `props` remain untyped (`any`). Object-style props infer String, Number, Boolean, Array, Object, Function, and class-constructor types within the component. Required/default props are defined; optional props may be undefined. Array items and plain Object members need further annotations; props passed to statically imported TypeScript children are checked against their public contract.
* Slots, dynamic `<component :is>`, unknown tags, JavaScript children, and non-object default exports are not checked. Child checking currently follows relative default imports within the supplied UI roots; named/package/alias component imports are not resolved into child contracts. Object spreads are checked structurally, but additional keys hidden in a spread or values typed as `any` cannot be fully validated.
* Template extraction uses a position-preserving scanner; it will move to the template AST once nodes carry exact source spans.
* pytscheck bundles a preview build of the TypeScript compiler; pin the pytscheck version in CI.

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

The `tsconfig` argument is optional. CLI equivalents are `--project-root .` and `--tsconfig tsconfig.json`. Relative configuration paths resolve against the project root. PyTSCheck checks project files selected by the config in addition to generated components, so findings may also reference files outside the UI folders. Installed npm declarations are resolved from the consuming project's `node_modules`; Python declaration packages may expose declarations in the project. No npm packages are installed automatically. The adapter only overrides emission settings and enables TypeScript extension imports for generated template imports; other configured compiler rules are retained.

Locations are 1-based; columns use UTF-16 coordinates. Template property/identifier errors point to the first matching identifier in the expression; other template diagnostics point to the expression start. The expression scanner is a prototype and does not model every JavaScript lexical scope, regular expression, or HTML entity mapping.

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

Default-import a TypeScript child component from a relative `.html` or `.vel` path under the checked UI roots. The checker uses its prop declaration for template attributes and bindings:

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

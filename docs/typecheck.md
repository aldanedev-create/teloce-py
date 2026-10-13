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
* Component `props` are untyped (`any`), so values passed to child components are not checked yet.
* Slots, dynamic `<component :is>`, and unknown component tags are not checked.
* Template extraction uses a position-preserving scanner; it will move to the template AST once nodes carry exact source spans.
* pytscheck bundles a preview build of the TypeScript compiler; pin the pytscheck version in CI.

## Python integration

```python
from teloce.typecheck import check_project

result = check_project(["ui", "modules/shop/ui"])
for finding in result.findings:
    print(finding.format())
```

Supply existing directories. Empty input and compiler/configuration/I/O failures raise `TypecheckUnavailable`; the CLI reports exit code 2. Declaration files (`.d.ts`) under these directories are included. This prototype checks an isolated virtual project with explicit compiler options; it does not automatically inherit the application's tsconfig or installed package declarations. Include suitable declarations under the supplied roots.

Locations are 1-based; columns use UTF-16 coordinates. Template property/identifier errors point to the first matching identifier in the expression; other template diagnostics point to the expression start. The expression scanner is a prototype and does not model every JavaScript lexical scope, regular expression, or HTML entity mapping.

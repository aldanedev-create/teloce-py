# JavaScript, TypeScript, and production bundling

Teloce's default JavaScript boundary parser uses the bundled Tree-sitter
backend in `src/teloce/javascript/tree_sitter_backend.py`. Teloce keeps the
stable source-preserving AST and token classes in
`src/teloce/javascript/parser.py`, so existing integrations do not need to
change. The legacy parser remains available with `backend="legacy"` for
constrained environments.

The installed parser grammars provide structural JavaScript/JSX and
TypeScript/TSX syntax analysis. They do not execute code, type-check a
program, or emit/transpile TypeScript. Teloce still owns the `.vel` component
model and generated browser runtime.

They are regular Teloce runtime dependencies, so a normal installation is
enough:

```powershell
python -m pip install teloce-py
```

The package declares one compatible version range for `tree-sitter`,
`tree-sitter-javascript`, and `tree-sitter-typescript`; users do not need to
install a separate parser package or Node.js just to compile a `.vel` file.

The package exposes a source-preserving language AST:

```python
from teloce.javascript import parse_javascript_language


program = parse_javascript_language(
    "const total = prices.reduce((a, b) => a + b, 0);"
)
declaration = program.body[0]
assert declaration.kind == "VariableDeclaration"
assert declaration.children[0].kind == "VariableDeclarator"
```

The language parser reports balanced-syntax errors with line and column
locations, optional repair suggestions, and preserves the original source of
every node. Its recursive AST covers common declarations and statements,
blocks, conditionals, loops, functions, classes, module boundaries, arrows,
calls, members, `new`, arrays/objects, spread/rest, unary/binary/assignment,
conditional, optional-chaining, and update expressions. It does not promise
support for every current or future ECMAScript proposal.

That distinction matters: Teloce now performs structural JavaScript and
TypeScript parsing without forcing a Node toolchain. TypeScript type erasure,
symbol linking, type checking, and industrial dead-code elimination remain
separate compiler jobs.

## What the JavaScript tooling packages do

| Tool | What it provides | Where it fits |
| --- | --- | --- |
| TypeScript compiler API (`typescript`) | Microsoft's parser, binder, type checker, emitter, source maps, and language-service data | Full TypeScript/JavaScript analysis and transpilation; normally run in a Node build step |
| Tree-sitter with JavaScript/TypeScript grammars | Fast incremental concrete syntax trees and error nodes | Teloce's bundled syntax backend and editor tooling; it is not a type checker or bundler |
| SWC (`@swc/core`) | Rust-based JavaScript/TypeScript/JSX parser and transformer | Fast transpilation and syntax lowering in a Node build pipeline |
| esbuild | Bundling, ESM-aware tree-shaking, code splitting, minification, and source maps | Production asset optimization after Teloce emits JavaScript |

The TypeScript compiler API models a pipeline of parser, binder, checker,
emitter, and services. Tree-sitter provides syntax trees and incremental
editing, but does not replace semantic type checking. SWC is a transformer,
while esbuild is the most direct fit for final bundling and tree-shaking.

References: [TypeScript Compiler API](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API),
[Tree-sitter JavaScript grammar](https://pypi.org/project/tree-sitter-javascript/),
[Tree-sitter TypeScript grammars](https://pypi.org/project/tree-sitter-typescript/),
[SWC parser configuration](https://swc.rs/docs/usage/core), and
[esbuild tree-shaking and code splitting](https://github.com/evanw/esbuild/blob/main/docs/architecture.md).

## TypeScript in a `.vel` file today

```html
<script lang="ts">
interface User { id: number; name: string; }
const user: User = { id: 1, name: 'Ada' };
</script>
```

For `lang="ts"`, Teloce removes a limited set of type-only declarations,
common parameter/return/variable annotations, type imports, assertions, and
simple enums before generating browser JavaScript. It does not type-check the
program, resolve types, support every TypeScript construct, or provide
TypeScript language-service diagnostics. Complex generics, decorators, JSX,
advanced enum behavior, declaration merging, and many newer TS features should
be compiled by TypeScript or SWC first.

## How esbuild fits

When you run:

```bash
teloce build --bundle --bundler esbuild --minify --hash-assets --source-map
```

the flow is:

```text
.vel (lang="ts")
  -> Teloce removes supported type-only syntax
  -> Teloce generates JavaScript modules and CSS
  -> esbuild bundles generated modules
  -> esbuild tree-shakes, splits, minifies, and writes source maps
  -> browser loads the final assets
```

esbuild does not make Teloce's parser a TypeScript type checker. If the
generated module imports a `.ts` file, esbuild can transpile that file only if
the project has configured esbuild as the bundling entry and the syntax is
within esbuild's supported transform surface. Teloce itself still discovers
and compiles `.vel` files first.

## Why Teloce bundles Tree-sitter

The bundled parser keeps `pip install teloce-py` independent of Node while
providing a real structural syntax tree for JavaScript, JSX, TypeScript, and
TSX. The parser is used for source validation, module boundaries, component
script diagnostics, and source-preserving AST tooling. Teloce still keeps its
legacy parser as an explicit compatibility backend:

```python
from teloce.javascript import parse_javascript

modern = parse_javascript("const value = source?.value ?? 0;")
legacy = parse_javascript("const value = 1;", backend="legacy")
```

Tree-sitter does not make Teloce a TypeScript type checker, JavaScript
transpiler, or full symbol linker. Applications using TypeScript syntax that
Teloce's compatibility lowering does not erase should use the TypeScript
compiler or another dedicated emitter before the final browser bundle.

## Recommended full TypeScript arrangement

For applications that need full TypeScript, use a separate Node build stage:

1. Parse and transpile the `<script lang="ts">` block with TypeScript or SWC.
2. Return source-mapped JavaScript to Teloce's generator.
3. Run the emitted modules through esbuild for tree-shaking, splitting,
   hashing, minification, and browser-target selection.
4. Preserve Teloce diagnostics and map them back to the `.vel` source.

Tree-sitter-TypeScript is included for parsing and diagnostics. It does not
replace the TypeScript compiler when an application needs full type erasure,
type checking, declaration output, or language-service behavior.

## Current Teloce commands

```powershell
# Development compiler/runtime path
python app.py

# Production output with Teloce's built-in optimizer
teloce build --hash-assets --report --max-size 250000

# Add Jinax server-rendered artifacts
teloce build --static

# Emit lazy local component imports
teloce build --lazy-components SettingsPanel
```

Teloce's built-in optimizer performs AST-aware local component import
tree-shaking, built-in filter selection, lazy import emission, shared runtime
extraction, keyed DOM reconciliation, and size reporting. It is not a
replacement for a full JavaScript bundler's symbol-level dead-code analysis;
use an optional bundler when the application needs that guarantee.

## Expression security

Generated components and the standalone runtime interpret template expressions
with Teloce's constrained evaluator. They do not use `eval()` or `Function()`
and reject dangerous property paths such as `constructor`, `prototype`, and
`__proto__`. Unsupported expressions resolve safely and can be diagnosed in
development. Do not treat browser expressions as a security boundary: keep
authorization, validation, secrets, and database work in Python.

Older applications may still pass an `unsafe_eval` setting. It is retained as
a compatibility-shaped configuration value but does not enable dynamic code
execution in current generated or standalone runtimes.

## SSR and Python frameworks

New SSR builds use the independent AST renderer in `teloce.server`, with
explicit public snapshots, manifest entries and hydration. Read
[SSR and hydration](ssr-and-hydration.md) for the supported expression subset.

### Legacy Jinax adapter

`render_ssr()` accepts a Jinax/Jinja-compatible engine. Flaxon can provide
Jinax directly, while Flask, Django, and FastAPI applications can pass their
framework-owned Jinja environment or template adapter. The SSR translator
only evaluates server-safe template directives; browser event handlers and
unsafe JavaScript are not executed on the server.

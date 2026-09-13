# Lesson 34: Teloce-Py Mastery — Compiler Internals, Runtime Mechanics, and Production Builds

This lesson is the deep end. [Lesson 16](16-how-teloce-works.md) gave you
the pipeline at a glance; this lesson opens up every stage of it, explains
*why* the runtime is built the way it is, and walks through the exact
scoping model that governs `v-for`, `v-if`, `v-model`, `:bind`, and `@event`
— because that one model explains nearly every subtle bug you'll ever hit
in a real `.vel` codebase. Every mechanic described here was traced through
the actual compiler source and verified by compiling real components and
running the generated JavaScript, not inferred from documentation.

## Part 1: The full pipeline, one level deeper

```text
.vel source
   │
   ▼
Lexer            tokenizes template markup, attribute names/values,
                 interpolations, directive prefixes (transition:/in:/out:/animate:)
   │
   ▼
Parser           builds an AST: ElementNode, ForNode, IfNode, TextNode,
                 InterpolationNode, EventNode, BindingNode, TransitionDirectiveNode
   │
   ▼
Transformer /    tree-to-tree rewrites (e.g. lowering v-for/v-if/v-else
Optimizer        into ForNode/IfNode, dead-code elimination)
   │
   ▼
Generator        walks the final AST and emits:
                   - an HTML template string (with data-teloce-* markers)
                   - a JS runtime (shared or inlined) that renders and
                     patches that template against a live DOM
   │
   ▼
Builder          orchestrates compiling every .vel file in a project,
                 writes output, copies static assets, builds a manifest
```

The critical thing to internalize: **the "template" is not HTML that gets
parsed once.** It's a *string* that gets **re-rendered from scratch** into
a fresh `<template>` element on every state change, then **reconciled**
against the live DOM by a keyed diff. Two completely different mechanisms
are at play — string templating (`__renderTemplate`) and DOM patching
(`__patch`) — and almost every hard-to-explain bug in this compiler traces
back to one of those two mechanisms not agreeing with the other about what
scope a piece of markup belongs to.

## Part 2: `__renderTemplate` — turning state into an HTML string

This is the actual, current order of operations inside the generated
`__renderTemplate(source, state, loopScopes)` function:

```text
1. Resolve <slot> tags against state.__slots
2. Unroll every <for>...</for> block (recursively) via __renderLoops
3. Resolve every remaining <if>...<else>...</if> block (iteratively)
4. Substitute {{ interpolations }}
5. Convert stray @event="..." into data-teloce-event-*
6. Convert stray :name="..." into resolved attributes
```

Step order matters enormously, and it's the source of one of the bugs
fixed in this lesson series: **`<if>` resolution used to run *before* loop
unrolling.** That meant any `v-if` nested inside a `v-for` got evaluated
against top-level state (where the loop variable doesn't exist) and was
stripped before the loop ever got a chance to run. The fix was simply
reordering steps 2 and 3 — loops unroll first, so by the time the
top-level `<if>` pass runs, every `<if>` still remaining is a genuinely
top-level one and evaluates against the right scope. This is worth
remembering as a general principle: **in a multi-pass string-rewriting
pipeline, order-of-passes *is* scoping.**

### `__renderLoops`: how a `<for>` block actually unrolls

For each `<for key="..." item="..." in="...">...</for>` found via a plain
string scan (`indexOf("<for ")`, not a real parser — more on this below):

```js
const values = __evaluate(collectionMatch[1], state) || [];
const rendered = Array.from(values).map((value, index) => {
  const loopScope = { ...state, [itemMatch[1]]: value, index };
  const nested = __renderLoops(body, loopScope);   // recurse for nested <for>
  return __resolveNestedIf(                        // resolve <if> in this body first
    nested.replace(/data-teloce-bind-.../, ...)     // resolve :bind against loopScope
  , loopScope)
    .replace(/@event.../, ...)                      // tag @events with loop scope
    .replace(/data-teloce-model.../, ...)            // tag v-model with loop scope
    .replace(/{{ interpolation }}/, ...);            // resolve {{ }} against loopScope
}).join("");
```

Two things to internalize here:

**`loopScope` is a shallow spread of `state` plus the loop variable(s).**
`{ ...state, item: value, index }`. This means `value` — the actual array
element — is inserted **by reference**, not copied. That single fact is
why `v-model="item.name"` correctly mutates the real array element (see
Part 4) and why `key`-based reconciliation can safely assume object
identity is preserved across renders.

**The scan for `<for `/`</for>` is a plain string search, not a
tag-aware parser.** `source.indexOf("<for ")` finds the *first*
occurrence of that literal substring in the whole remaining source,
regardless of what it's nested inside. This is deliberate and it's why
the loop-unrolling recursion in `__renderLoops` is written to call itself
on the *body* of what it just found — it's peeling one layer at a time,
trusting that whatever's left after removing a matched `<for>...</for>`
is still well-formed for the next pass to find the next one.

### `data-teloce-bind-*` vs. `data-teloce-resolved-*`

This distinction exists specifically because of a real, shipped bug. The
naive version: loop unrolling evaluates a `:bind` expression correctly
(with `loopScope`) and bakes the concrete value into
`data-teloce-bind-src="/actual/value.png"`. Later, a *separate* hydration
pass (during DOM patching, described in Part 3) walks every element and
re-evaluates every `data-teloce-bind-*` attribute's value *again* — but
against top-level `state`, because that pass has no way to know the
element came from a loop. It tried to evaluate the string
`"/actual/value.png"` as if it were still JavaScript source. That either
silently returned `undefined` or threw inside the expression parser
(a leading `/` looks like a regex literal or division operator to a naive
tokenizer).

The fix: loop-resolved bindings get renamed to `data-teloce-resolved-*`
during unrolling, with the value serialized via `JSON.stringify` (not
lossy `String(x ?? "")`, which collapsed `null`/`false`/`0` into an empty
string). The hydration pass now branches on the attribute prefix: `bind-*`
still gets evaluated as an expression (correct for elements that were
never inside a loop, where the attribute value genuinely is still raw
source); `resolved-*` gets `JSON.parse`d and applied directly, no
re-evaluation. Two attribute name prefixes doing two different jobs is the
whole fix — but you can't discover that from reading either half of the
code in isolation. This is the kind of thing that only becomes obvious
once you've traced a value from source template through to DOM attribute
and back.

### `data-teloce-loop-scope`: how events and `v-model` reach into a loop

Events (`@click="select(item)"`) and `v-model` face a different problem
than `:bind`: they can't just bake in a resolved *value*, because they
need to run **later**, in response to a real user interaction, with the
**correct loop-scoped variables still available at that time** — not at
render time.

The solution both use: tag the element with a JSON blob of the loop scope
at the moment it's rendered —

```html
<button data-teloce-event-click="select(item)"
        data-teloce-loop-scope="{&quot;item&quot;:{...},&quot;index&quot;:0}">
```

— and when the listener actually fires, re-read and re-parse that
attribute **fresh, inside the callback**, not from a value captured once
at attach time. This matters because of keyed reconciliation: the *same*
DOM node can get reused for a *different* array item across renders (that
is the entire point of keyed diffing — reuse nodes, don't recreate them).
If the loop scope were captured once when the listener was first attached,
a reordered list would silently fire handlers against stale data. Reading
`getAttribute("data-teloce-loop-scope")` inside the handler, every time,
is what keeps it correct.

**The optimization layer.** Encoding a full JSON blob into every looped
element's attribute on every render is wasteful for large lists. A final
post-processing pass over the generated runtime string rewrites this
specific pattern: instead of inlining the JSON directly into the
attribute, it assigns each loop scope a compact numeric ID and stores the
actual object in a `Map` (`loopScopes`), so the DOM attribute holds just
`data-teloce-loop-scope="17"` and the lookup is `loopScopes.get("17")` —
an actual object reference, no JSON parsing, no string bloat per row. This
optimization is applied via *exact-string* `.replace()` calls against the
"naive" version of the code, which is why adding `v-model`'s loop-scope
support required **also** teaching this same optimization pass about the
new code — extending an existing string-substitution optimizer is its own
skill, and it's brittle: get the exact string wrong and the optimization
silently no-ops instead of erroring.

## Part 3: `__patch` — reconciling the string against the live DOM

Once `__renderTemplate` produces an HTML string, `__patch(target, html)`
diffs it against what's actually in the DOM:

```js
const template = document.createElement("template");
template.innerHTML = html;
// ... walk target's children and template.content's children together ...
```

**Keyed reconciliation.** Elements carrying `data-teloce-key` are matched
by key across renders (a `Map<key, node>` lookup), not by position. This
is what makes `animate:flip` possible — a row that moves from index 4 to
index 0 is recognized as *the same DOM node*, just relocated, rather than
being destroyed and recreated.

**`cloneManaged` / `disposeNode`.** New nodes get `cloneManaged`'d (marked
as framework-owned, so future diffs know they're allowed to touch them) —
and if any transition directives are in play, `__playEnter` fires here.
Removed nodes go through `disposeNode`, which unmounts nested component
instances, strips event listeners, and — again, only if transitions are in
play — fires `__playExit` **before** actual removal.

**The FLIP guard.** `animate:flip` used to call `getBoundingClientRect()`
on every managed child of a list parent on *every single patch* of that
parent, even ones that only changed an item's text and never reordered
anything. `getBoundingClientRect()` forces a synchronous layout — cheap
once, expensive when multiplied across every keystroke on an unrelated
input in the same list. The fix: before measuring anything, compare the
list's current key order against the order cached from the previous patch
(`parent.__teloceFlipKeys`). If unchanged, skip the whole measure/animate
pass entirely — no `getBoundingClientRect()` calls at all. A second,
independent bug was found here too: the original `__flipSnapshot`
implementation used `querySelectorAll` over the parent's *entire subtree*
instead of just its direct children, so a component with nested lists paid
the measurement cost once per ancestor level, not once total. Both fixes
together took a 300-item benchmark from 600 wasted layout reads on every
keystroke down to zero.

## Part 4: The unified scoping model

Everything in Parts 2 and 3 is really one idea wearing different clothes:

> **Every value in a `.vel` template resolves against exactly one scope
> object at the moment it's evaluated, and that scope must contain the
> loop variable if the value is inside a `v-for`.**

The entire history of bugs fixed across this lesson series is the same
mistake in five different disguises:

| Directive | What broke | Root cause |
|---|---|---|
| `:bind` (`:src`, `:disabled`, ...) | Silently never applied inside `v-for` | Hydration re-evaluated an already-resolved value against top-level `state` instead of `loopScope` |
| `v-if` | Never rendered inside `v-for` | Resolved globally, before loops unrolled, against `state` without the loop variable |
| `v-model` | No initial value, no write-back, inside `v-for` | Same as `:bind` — evaluated and assigned against `state`, never `loopScope` |
| `v-else`/`v-else-if` | Rendered unconditionally, always | Never merged with the preceding `v-if` at all — broken by ordinary whitespace between sibling elements confusing the "is the previous AST node an IfNode" check |
| Multi-branch `v-else-if` chains | Only the first and last branch worked | The AST-merge fix for the bug above didn't walk to the *end* of an existing branch chain, so each new branch overwrote the previous one instead of appending |

Once you see the pattern, you can predict where the next bug in this
family would hide: **any construct that reads or writes state inside a
loop, using a mechanism that wasn't specifically designed with `loopScope`
in mind, is suspect until proven otherwise.** When you build a custom
directive or extend this compiler yourself, the question to ask before
anything else is: *does this directive's runtime code ever run for an
element inside a `v-for`, and if so, where does it get the loop variable
from?*

### The one caveat this model doesn't fully solve

`__assign`'s path-walking write-back (`scope[path[0]][...][lastKey] =
value`) works correctly for `v-model="item.name"` because `item` is an
*object* and the write mutates it by reference — the same object sitting
in the real array. It does **not** correctly propagate for
`v-model="item"` directly on a loop item that is itself a primitive (e.g.
`v-for="item in tags"` where `tags` is `["a", "b", "c"]`) — writing into a
merged copy of the scope reassigns the copy's `item` key, not the original
array slot. This is a known, narrow limitation, not something this lesson
series fixed, because it needs a different mechanism entirely (index-based
write-back rather than reference mutation). If you need two-way binding on
a primitive array item, wrap it in an object (`{ value: "a" }`) instead.

## Part 5: Compiler quirks worth memorizing

These aren't bugs (or are bugs that are out of scope for now) — they're
current, real behavior you should design around:

- **`v-for` only destructures arrays**, via `.entries()` — `(item, index)
  in array`. There is no `(value, key) in object` form. Convert an object
  to an array first: `Object.entries(obj).map(([k, v]) => ({ k, v }))`.
- **A static `class="..."` and a `:class="..."` binding on the same
  element don't merge** — the binding replaces the static value entirely.
  Compute the full class string yourself: `:class="'base ' + variant"`.
- **`teloce.config.json` is read automatically only by the CLI**
  (`python -m teloce build`). Calling `build_project()` directly from
  Python does not read it — see Part 6.

## Part 6: The build system, precisely

### `build_project()` output location

```python
from teloce.build import build_project
result = build_project(ROOT)
```

This writes to **`<root>/dist/`** by default, not in place next to your `.vel`
source. A development build uses logical names such as
`dist/static/js/App.js`; a production build uses content-hashed files such as
`App.<hash>.js` and `teloce-runtime.<hash>.js`, plus a small stable `App.js`
shim. Your Python framework should serve static files from `dist/static`, not
the authored `static` directory.

**Don't pass `out_dir` equal to your project root** when your `.vel`
source and other static assets already live inside that root — the asset
copier will attempt to copy a file onto itself and crash with
`shutil.SameFileError`. Verified directly:

```
shutil.SameFileError: PosixPath('.../static/teloce-runtime.js') and
PosixPath('.../static/teloce-runtime.js') are the same file
```

Use the default `dist/` separation, or point `out_dir` somewhere that
doesn't overlap your source tree.

### Making the output smaller: what each production switch does

The built-in `minify` option is, by design, only a whitespace-stripping
pass that preserves strings, template literals, regular expressions, and
source semantics. It does not rename user symbols or replace a full
JavaScript bundler. The exact byte reduction depends on the component; use
`build-report.json` for current measurements.

Real reduction requires bundling with a real minifier, and a few
additional flags. Verified end to end, in order of actual impact:

| Config | Output |
|---|---|---|
| development | readable modules, logical filenames, HMR-friendly output |
| production defaults | one shared runtime, minified modules/CSS, extracted CSS, tree-shaking, hashed files, and stable logical JS shims |
| `bundle: true, bundler: "teloce"` | one dependency-aware bundle using the dependency-free built-in bundler |
| `bundle: true, bundler: "esbuild"` | optional whole-application bundle with esbuild minification and code splitting |

**`bundle` is a separate flag from `bundler`/`minify`, and gates whether
bundling happens at all.** Set `bundler: "esbuild"` and `minify: true`
without `bundle: true` and both are silently inert — confirmed by testing
that exact combination and getting byte-identical output to no bundling
at all. `bundle: true` is what actually invokes the bundler; `bundler`
picks which one (`"esbuild"` vs. teloce's plain `ModuleBundler`); `minify`
then means something real, because it's passed straight through as
esbuild's own `--minify` flag.

With the built-in bundler, component modules and their local dependencies are
merged into one output. With esbuild, code splitting can leave shared and
lazy chunks as separate files. Deploy the complete output directory in both
cases; do not upload only the entry file.

**The extra ~2%: flags the Python wrapper didn't originally expose.**
`EsbuildBundler.bundle()` only forwarded `minify`/`sourcemap`/`target`/
`splitting` to the underlying esbuild command. Three more esbuild flags
give a further, smaller reduction — `--drop:console`/`--drop:debugger`
(strips those calls entirely, not just their output), `--legal-comments=none`
(drops any license-comment preservation esbuild would otherwise keep), and
`--charset=utf8` (emits literal UTF-8 characters instead of `\uXXXX`
escape sequences where safe). These are now wired through as `drop`
(a list of names to `--drop:`-prefix), `legal_comments`, and `charset`
options on both `EsbuildBundler.bundle()` and `Builder`'s options dict —
they didn't exist before this lesson was written; adding them was as
simple as extending the flag-construction logic in `esbuild.py` and
threading three more `self.options.get(...)` calls through the one
`Builder` call site that invokes it.

```json
{
  "build": {
    "bundle": true,
    "bundler": "esbuild",
    "minify": true,
    "tree_shake": true,
    "drop": ["console", "debugger"],
    "legal_comments": "none",
    "charset": "utf8"
  }
}
```

`code_splitting`, `target`, and `source_maps` were also tested against
this same single-component app and made **no measurable difference** —
they only matter with multiple entry points or when targeting older
JavaScript syntax levels that require downleveling.

### `tree_shake` and `lazy_components`: the Svelte-shaped lever

Everything above shrinks code that's *going to ship regardless*. These
two options decide **whether code ships at all**, which is the bigger
architectural win once an app has more than one component:

- **`tree_shake: true`** drops the import for a child `.vel` component
  entirely if that component is never actually referenced in the
  template — free, always safe to enable, catches dead imports the
  compiler can prove are unused.
- **`lazy_components: ["ComponentName", ...]`** rewrites a specific
  child component's import from a static `import X from "./X.js"` into
  a dynamic one, wrapped in a small lazy-loading helper:

  ```js
  // without lazy_components:
  import HeavyModal from "./HeavyModal.js";

  // with lazy_components: ["HeavyModal"]:
  const HeavyModal = __teloceLazy(() => import("./HeavyModal.js"));
  ```

  Verified with a real two-component test — `HeavyModal.js` is not
  fetched by the browser at all until `__teloceLazy`'s loader actually
  runs (i.e., the first time that component is mounted). A settings
  panel, an admin view, an upgrade modal — anything not needed on first
  paint is a candidate.

**Neither option does anything for a single, self-contained component**
like the Image Studio's `App.vel`, which has no child `.vel` imports —
there's nothing to shake or lazily load. They only pay off once an app is
decomposed into multiple components, some of which aren't always needed.
This is worth internalizing as the actual Svelte-shaped mental model: the
compiler deciding *what ships* based on *what's used*, rather than
minification deciding *how small what already ships* can get.

### `teloce.config.json` — read manually, not automatically, by the Python API

The schema (nested under `compiler` and `build`):

```json
{
  "compiler": { "source_maps": true },
  "build": { "minify": false, "shared_runtime": true, "clean": true }
}
```

`Builder.__init__` takes a single **flat** `options` dict — it has no
knowledge of `teloce.config.json` at all; only the CLI reads and flattens
that file before constructing a `Builder`. If your app calls
`build_project()` directly (the "automated build on server startup"
pattern below) and you want it to honor the same config file your CI and
`teloce build` use, you have to load and flatten it yourself:

```python
import json
from pathlib import Path

def load_teloce_config(root: Path) -> dict:
    path = root / "teloce.config.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    flat = {}
    flat.update(raw.get("compiler", {}))
    flat.update(raw.get("build", {}))
    return flat
```

Verified end to end: the current shared-runtime build keeps the generated
component module small and writes the component glue once in the shared
runtime. With `minify: true`, both generated JavaScript and CSS are compacted;
exact byte counts vary with the component and runtime version, so use the
generated `build-report.json` rather than copying fixed numbers from a lesson.

### The automated-build-on-startup pattern

The pattern that actually matters for `python app.py`: call
`build_project()` **at module import time**, not only inside
`if __name__ == "__main__":`. If the build only happens inside the
`__main__` guard, running the exact same app via
`uvicorn app:app --reload` (which imports the module without ever
executing that guard) would silently serve stale or entirely missing
assets.

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from teloce.build import build_project

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Runs at import time -- works for both `python app.py` and
# `uvicorn app:app --reload`. Raises RuntimeError (refusing to start)
# if any .vel file fails to compile, rather than serving stale assets.
build_project(ROOT, options=load_teloce_config(ROOT))

app = FastAPI()
app.mount("/static", StaticFiles(directory=DIST / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    # The build already happened above -- nothing build-related belongs here.
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

Keep user-generated content (uploads, processed files, anything your app
writes at runtime) **outside** the directory `build_project()` manages.
With `clean: true` in the config (or by default in some builder modes),
a rebuild can legitimately wipe the output directory — storing writable
application data inside `dist/` risks losing it on the next restart. The
Image Studio example from [Lesson 33](33-image-studio-saas.md) mounts a
completely separate `/media` route backed by a plain directory the build
never touches, specifically to avoid this:

```python
MEDIA = ROOT / "media"
app.mount("/static", StaticFiles(directory=DIST / "static"), name="static")
app.mount("/media", StaticFiles(directory=MEDIA), name="media")
```

Verified end-to-end via `TestClient`: home page renders through the
Jinax/Jinja shell, `build_project()` runs and produces `dist/static/js/
App.js` is a stable shim for the hashed implementation (both are confirmed
served correctly at `/static/js/App.js` and the hashed URL),
an uploaded image round-trips correctly through `/media/uploads/...`, and
applying a filter produces a new file served through
`/media/processed/...` — all through the exact code path a real
`python app.py` invocation would take, not a hand-wired test shortcut.

## Part 7: How to actually find bugs like the ones fixed in this series

This is the methodology, not just the results, because it's reusable on
whatever you build next:

1. **Reproduce with the smallest possible component.** Every bug in this
   lesson series was eventually confirmed with a 3-10 line `.vel` file —
   no unrelated markup, no custom directives, nothing that could hide the
   real cause. Start there, not with your full app.
2. **Inspect the compiled template *string*, not just the final DOM.**
   `compile_file()`'s `result["code"]` contains the raw generated
   JavaScript, including the literal `__template = "..."` string. Grepping
   this directly showed, for example, that `data-teloce-animate="flip:&gt;"`
   was corrupted — a fact invisible from the DOM alone.
3. **Run the compiled output in a real (simulated) DOM, not just
   `node --check`.** Syntax-checking a file only proves it parses. Use
   `jsdom` to actually `mount()` the component, mutate `instance.state`,
   call `instance.update()`, and inspect real element attributes
   (`getAttribute`, `.value`, `.checked`) — not just the generated source.
4. **Stub the platform APIs you need, nothing more.** `jsdom` doesn't
   implement `Element.animate()` or real layout (`getBoundingClientRect()`
   always returns zeros), so transition/FLIP tests stubbed those two
   functions to record calls instead of performing real animation —
   enough to verify *that* and *how often* they're called, without needing
   a real browser.
5. **When a fix changes behavior, re-run the full existing test suite
   before doing anything else.** Two of the fixes in this series
   accidentally broke a pre-existing, passing test on the first attempt
   (extending the loop-scope optimizer for `v-model`, and a chain-merging
   bug in the `v-else-if` fix itself) — both caught immediately because
   the habit was "run `pytest` after every edit," not "run it once at the
   end."
6. **Test the actual production entry point, not a shortcut.** The
   config-loading and automated-build verification in Part 6 used
   `TestClient` against the real `app.py`, importing the real module —
   not a hand-rolled script that merely calls the same functions in
   isolation. Bugs like the `out_dir`/`SameFileError` crash only show up
   when you exercise the real path.

## Mastery checklist

You can consider yourself fluent in this compiler when you can answer all
of the following without looking anything up:

- Why does `__renderTemplate` unroll loops *before* resolving `<if>` tags,
  and what breaks if that order is reversed?
- Why do `data-teloce-bind-*` and `data-teloce-resolved-*` need to be two
  different attribute names instead of one?
- Why must an event listener re-read `data-teloce-loop-scope` inside its
  callback, instead of capturing it once when the listener is attached?
- Why does `v-model="item.name"` correctly write back into the original
  array, but `v-model="item"` on a primitive array item does not?
- Why does `animate:flip` need to compare key order before measuring
  anything, rather than always measuring and letting `dx`/`dy` come out
  as zero for unmoved rows?
- Why does `build_project()` called directly from Python not honor
  `teloce.config.json`, even though `python -m teloce build` does?
- Why does setting `bundler: "esbuild"` and `minify: true` alone produce
  byte-identical output to not setting them at all — what's the one flag
  that actually turns bundling on?

If any of those are shaky, re-read the matching section above with a
real `.vel` file open next to the actual generated `result["code"]` —
reading the mechanism and watching it happen are different kinds of
understanding, and this compiler rewards the second one.

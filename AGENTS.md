# AGENTS.md

Instructions for AI coding agents working on the **Teloce-Py** repository (the compiler, runtime and CLI).
If you are building an app *with* Teloce, read the files in your project's `docs/teloce/` instead.

## What this repo is

Teloce-Py compiles `.vel` single-file components into browser JavaScript, ships a small browser runtime, and
has a CLI that scaffolds and builds projects. It is Python-native: generated projects do not need Node or npm.

## Layout

| Path | What it holds |
| --- | --- |
| `src/teloce/sfc`, `lexer`, `parser`, `template`, `expressions` | Reading `.vel` files and template expressions |
| `src/teloce/compiler` | `generator.py` turns a component into JavaScript. `compiler.py` is the entry point. |
| `src/teloce/directives`, `filters`, `components` | Compile-time directives, template filters, built-in components |
| `src/teloce/runtime` | Browser runtime, plain JavaScript with JSDoc types. `compiled.js` is the core. |
| `src/teloce/build`, `project`, `watcher` | Project scanning, the build pipeline, watch mode |
| `src/teloce/cli` | The `teloce` command (`main.py`, `create.py`, `ai_docs.py`, ...) |
| `src/teloce/bridge` | Python side of the network `action` and socket clients |
| `src/teloce/ai` | `AGENTS.md` / `CLAUDE.md` templates and docs that every generated project receives |
| `docs/` | Documentation. `docs/lessons/` holds the numbered lessons. |
| `examples/` | Runnable example apps. Tests build every one of them. |
| `tests/` | pytest suite, grouped by area |
| `scripts/` | Maintenance scripts |

## Setup and commands

```bash
python -m pip install -e . pytest      # Python 3.10 or newer
python -m pytest -q                    # whole suite
python -m pytest tests/ai -q           # one area
```

- Some tests skip when an optional tool is missing: Flask-Admin (one example), Playwright and Chromium
  (browser regression tests), Node (a few runtime checks).
- Style: `black src/ tests/`, `isort src/ tests/`, `mypy src/` (see `CONTRIBUTING.md`).
- Runtime type check: `npm install` then `npm run typecheck` (TypeScript checks the JSDoc in `src/teloce/runtime`).
- Try a change in a real app: `python -m teloce create /tmp/try --no-install --no-git`, then build it.

## Working on the runtime

- Edit `src/teloce/runtime/*.js`. The build copies these files into each project's `dist/static`.
- After a change, build an app that uses it and check it in a browser. Unit tests alone do not prove DOM behavior.
- Directives are bound per element. An element is bound **before** its children are rendered, so anything that
  looks at children must also watch for later changes (see how `bindScrolly` uses a `MutationObserver`).
- Clean up what you add. Observers, listeners and timers are released in the element teardown and in the
  directive's own cleanup.

## Docs and generated files

- `src/teloce/ai/docs/` holds copies of some files from `docs/`. After editing a listed doc, run
  `python scripts/sync_ai_docs.py`. A test fails if the copies drift. The list is in that script.
- `src/teloce/ai/docs/index.md` and `known-issues.md` are written by hand. Keep `known-issues.md` honest: move an
  item to "fixed in source" only when a test covers it, and remove it after the next release.
- The templates in `src/teloce/ai/templates/` use `@@TOKEN@@` placeholders, not `$` or `{{ }}`, because Teloce syntax
  uses both.
- Update `CHANGELOG.md` under `## Unreleased` for every user-visible change.

## Rules for changes

1. **Test first for bugs.** Write a test that fails, then fix it. Check the new test fails without your fix.
2. **Keep the change small.** No unrelated refactors or reformatting.
3. **Do not weaken a test** to make it pass. If a test is wrong, say why in the change.
4. **No new dependencies** unless asked. Runtime code stays dependency-free.
5. **Security matters.** Templates escape output. Do not add paths that render raw HTML, and do not loosen the
   action client's CSRF or origin checks.
6. **Examples must keep building.** `tests/integration/test_examples.py` builds every folder in `examples/`.
7. **Do not edit generated output** such as `dist/` folders or `.pyc` files.

## Before you finish

1. Run the tests for the area you changed, then the whole suite.
2. For runtime or compiler changes, build an example and check the browser console.
3. Update docs and `CHANGELOG.md`.
4. Report what you changed, what you ran, and anything you could not check.

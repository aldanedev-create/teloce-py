## Runtime JSDoc coverage

- Check every maintained runtime JavaScript module with strict, no-emit TypeScript.
- Document shared option contracts and intentional dynamic boundaries.
- Resolve the ambiguous combined-runtime `batch` export to the signal API.

# Changelog

### Runtime type checks

- Add JSDoc contracts and strict, no-emit JavaScript checking for signals, scheduling, effects/computed exports and lifecycle helpers. Add pinned development tooling and a CI check; runtime stays JavaScript.

All notable changes to Teloce-Py are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Release dates below are the first upload dates on [PyPI](https://pypi.org/project/teloce-py/#history), in UTC. Historical summaries were reconstructed from repository changes up to each publication date. The repository has no release tags; comparison links use commits instead. Teloce-Py remains beta software.

## [Unreleased]

### Fixed
- Make callable signals expose a reactive `.value` accessor so component model bindings and SSR state seeding notify subscribers correctly.
- Synchronize native `v-model` controls after state changes on direct, structural and fallback paths, using live loop scope for initial values and edits.
- Preserve normalized `.trim`/`.number` text and focused `.lazy` edits, respect IME composition, synchronize checkbox arrays/radios/selects, and clean up composition handlers.

### Added
- Independent AST-based SSR programs, safe public snapshots, named slots, explicit hydration and runtime diagnostics.
- Manifest-selected SSR entries, bounded render caching and the `teloce prerender` command.
- Node expression parity and Chromium hydration regression coverage.

### Changed
- `ssr: true` now produces `.ssr.json` programs; use `ssr: "legacy"` for Jinax artifacts.
- Preserve computed member expressions, `undefined`, numeric exponents, loop index aliases and original template locations in the canonical AST.


### Changed
- Initialize keyed-row dependency caches during the first render and attach their DOM references during the existing binding walk, avoiding a second collection/setup pass. Single-root edits in unchanged row order skip whole-list reconciliation.
- Direct DOM updates now default to enabled, with automatic compatibility fallbacks and an explicit disable switch.
- Production builds default to native MinifyJS bundling, optimizing the resolved module graph once; `--no-bundle` preserves separate modules.
- Keyed reconciliation minimizes moves using a longest increasing subsequence; simple keyed rows cache dependency snapshots and skip unchanged rendering.
- Virtual lists preserve overlapping rows and cancel queued scroll work on cleanup.


### Added
- First-class MinifyJS production minifier and bundler, installed as a Python dependency.
- Native split bundles, hashed outputs, original `.vel` source map composition, metadata, and build reporting.
- Adapter and bundler APIs, backend configuration, production browser regression tests, and Node esbuild parity checks.
- Opt-in direct DOM updates for supported bindings, with compatibility reconciliation and strict diagnostics for unsupported expressions.
- Tree-sitter syntax analysis for JavaScript/JSX and TypeScript/TSX, with a legacy parser fallback.
- Imported TypeScript module handling and incremental build coverage.
- Configurable HTML component support across compilation, builds, development, and watch workflows.
- Component scaffolding CLI command.
- Data utilities and runtime features for CSV, data tables, virtual lists, memoization, URL state, polling, live data, and actions.
- Local component auto-registration, `$attrs` forwarding, static child rendering, and embed output.
- Data-story example and lessons covering components, data workflows, performance, actions, and static exports.

### Changed
- Expanded production configuration, JavaScript/TypeScript tooling guidance, and troubleshooting documentation.
- Extended compiler optimization, source mapping, scoped CSS handling, and SSR support.

### Changed
- Build stages share one source snapshot; Tree-sitter parsers and bounded source/tree analysis are reused per thread.
- Development builds reuse import analysis, invalidate transitive component/TypeScript dependencies, and avoid rewriting unchanged generated files.
- Optional persistent development workers receive fresh source text and close through the Builder context manager.
- Direct updates index bindings by dependency, generate simple reader functions, and reconcile supported conditional/list regions independently.

### Fixed
- Reactive arrays notify length, truncated-index, and iteration dependencies correctly.
- Scheduler failures no longer discard unrelated queued jobs; unsubscribing cancels pending callbacks and subscriptions receive current values.
- Empty direct text bindings create real text nodes; keyed updates preserve focus/selection and read current global state in row events.
- Modular keyed-list helpers clean up removed/unmounted rows and avoid detaching unchanged rows.
- Authored import/export and lazy-import paths now resolve hashed copied assets.
- `jobs=0` correctly selects the automatic worker count instead of matching `False`.
- Builder CSS manifest syntax and optional Flaxon SSR tests are compatible with Python 3.10.

## [0.2.5] - 2026-09-13

### Added
- Shared compiled runtime and a Python router facade.
- Production minifier, build reports, and expanded asset/build configuration.
- CLI diagnostics and additional component, runtime, router, and browser regression coverage.
- GitHub-style Flask application example.
- Lessons on transitions and animations, signals in `.vel`, SPA development, and an image-studio application.

### Changed
- Expanded component import handling, project scanning, and production build optimization.
- Improved generated component updates, runtime DOM handling, and reactive signal integration.
- Expanded router and runtime documentation.

### Fixed
- Compiler, generated runtime, and component import edge cases covered by new regression tests.
- Updated configuration-driven Flask and Django admin examples and their build integration.

## [0.2.4] - 2026-09-01

### Added
- Configuration-driven Flask example and Django admin dashboard example.
- Reusable demo UI components and application shell example.
- TypeScript-in-`.vel`, lazy-loading, shared-runtime, and project configuration lessons.
- Additional plugin, router, scoped CSS, SFC, and documented-example regression coverage.

### Changed
- Hardened script parsing, component generation, scoped CSS, and SFC parsing.
- Improved plugin registry/hooks, router generation, lint fixes, and build configuration.
- Expanded API documentation and the directive cheatsheet.

### Fixed
- Compiler and runtime edge cases found during hardening.
- Corrected examples and documentation for TypeScript, component imports, and project layouts.

## [0.2.3] - 2026-08-29

### Added
- JavaScript syntax parser and script-analysis tooling.
- Optional esbuild build adapter.
- Jinax/Jinja-compatible SSR helpers that render server-safe templates without executing component JavaScript.
- CLI and configuration options for expanded build workflows.
- Compiler stress tests and regression tests for expression security, component imports, CSS, SSR, and runtime behavior.
- Flaxon cheatsheet and gallery examples.
- Production architecture, security, compatibility, testing, and deployment guidance.

### Changed
- Hardened compiler generation, template lexing, script/SFC parsing, and scoped CSS processing.
- Improved component and standalone runtime behavior, router generation, and development tooling.
- Expanded manifests and production builder capabilities.

## [0.2.0b2] - 2026-08-27

### Added
- Production build pipeline with asset copying, bundling, manifests, and output writing.
- Single-file compile command and expanded lint tooling.
- Flaxon project scaffold and generated `teloce.config.json`.
- Signals/reactivity lessons, runtime/router guidance, debugging lessons, and framework integration examples.
- Flaxon standalone runtime notebook example.

### Changed
- Improved project creation for basic, Flask, Django, FastAPI, and Flaxon templates.
- Added project-name and template validation and corrected generated requirements.
- Expanded development server, watch, build, and CLI workflows.
- Kept Teloce Studio and Flaxon OS outside the compiler repository.

### Fixed
- Preserved loop scope in dynamic bindings.
- Corrected runnable README examples and framework integrations.
- Protected runtime notebook interpolation from Jinax processing.
- Improved compiler, lint, development-server, and browser behavior with regression coverage.

### Notes
- This version is published on PyPI, but there is no corresponding version-file bump or release tag in the repository. Its summary covers repository changes through the publication time.

## [0.2.0b1] - 2026-08-24

### Changed
- Prepared the beta PyPI package metadata and changed the package version from `0.1.0` to `0.2.0b1`.

## [0.1.0] - 2026-08-24

### Added
- Initial alpha release of the Python-native Teloce compiler and runtime.
- `.vel` single-file component parsing and JavaScript generation.
- Template interpolation, event handling, two-way binding, conditions, and loops.
- Component resolution, scoped CSS, and source map support.
- Development server, watch/build workflows, debugging, and project creation CLI.
- Python web framework integration examples for Flask, Flaxon, Django, and FastAPI.
- Error diagnostics, documentation, examples, and an initial test suite.

[Unreleased]: https://github.com/aldanedev-create/teloce-py/compare/7728cab89e5dfaeaef8c782f7e614d77ad775597...main
[0.2.5]: https://github.com/aldanedev-create/teloce-py/compare/67edb0d5c94d9f32a7deb62c4e98920d566996d2...7728cab89e5dfaeaef8c782f7e614d77ad775597
[0.2.4]: https://github.com/aldanedev-create/teloce-py/compare/ab5667d353d670551d4f5c4f001156b8ddfce94c...67edb0d5c94d9f32a7deb62c4e98920d566996d2
[0.2.3]: https://github.com/aldanedev-create/teloce-py/compare/dd34cea...ab5667d353d670551d4f5c4f001156b8ddfce94c
[0.2.0b2]: https://github.com/aldanedev-create/teloce-py/compare/28caaf4fc03ea3407d011e6a8ca2a645219835e5...dd34cea
[0.2.0b1]: https://github.com/aldanedev-create/teloce-py/compare/859a016fef3042973285647f1b438e5b9c543582...28caaf4fc03ea3407d011e6a8ca2a645219835e5
[0.1.0]: https://github.com/aldanedev-create/teloce-py/commit/859a016fef3042973285647f1b438e5b9c543582

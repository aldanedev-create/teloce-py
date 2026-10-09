# Compiler and runtime performance

Compiler speed controls build feedback. Runtime speed controls browser updates.
Measure them separately using the scripts in
[`benchmarks/compiler-runtime`](../benchmarks/compiler-runtime/README.md).

## Build behavior

Each build reads authored component and TypeScript text once, sharing that
snapshot between hashing, import analysis, compilation, and SSR. A new build
reads again so edits are never hidden by an old in-memory snapshot.

Tree-sitter language objects are reused. Mutable parsers belong to one thread
in one process. A bounded per-thread cache reuses exact source/language trees
between stages; callers receive tree copies, so `Tree.edit()` cannot corrupt
another stage's cached result. It retains at most 32 source/tree entries and
1 MiB of source text; modules over 128 KiB bypass that cache. These are cache
limits, not a promise about total process memory.

Development manifests store source hashes and import analysis. Unchanged
imports reuse that analysis, but resolution uses the current project file set.
Component and TypeScript changes invalidate transitive parents; removing an
input invalidates its parents too. A scan and content-hash pass still runs:
this is incremental analysis, not an operating-system metadata-only cache.

Generated files written through `FileWriter`, including the shared runtime,
are left untouched when their bytes match. Manifests and asset-copying stages
can still write files. Production cleaning, bundling, and asset hashes retain
their existing behavior.

## Development workers

The default remains one process. Enable persistent workers explicitly for a
large project after measuring its rebuilds:

```json
{
  "build": {
    "jobs": 4,
    "persistent_workers": true,
    "shared_runtime": true,
    "direct_dom_updates": true
  }
}
```

The development and watch commands use incremental builds. Small pending
batches stay sequential; the default parallel threshold is 32 files. Larger
batches can reuse a worker pool in development. Each task receives fresh source
text; changing the project/output or worker count replaces the pool. Failed
pool work falls back to sequential compilation for unfinished files.

For a custom watcher, close the builder when stopping:

```python
from teloce.build import Builder

with Builder({
    "dev": True,
    "html_mode": True,
    "jobs": 4,
    "persistent_workers": True,
}) as builder:
    result = builder.build(".", "dist")
    # Reuse builder.build(...) for subsequent edits.
```

One-shot `build_project()` closes its builder automatically. Persistent pools
are opt-in and are not used for production builds. They are not guaranteed to
help small projects.

## Browser behavior

With `direct_dom_updates` enabled, dependency indexes select affected bindings.
Simple state/member reads use compiler-generated reader functions; more complex
expressions use the existing safe evaluator. Calls and filters invalidate
conservatively because they may read other state.

Supported outer conditionals and regular loops receive comment anchors. Only
an affected region renders and reconciles; unrelated text updates leave those
regions alone. Nested structural changes reconcile within their outer region.
Keyed list reconciliation minimizes DOM moves. Supported simple loops cache
row dependency snapshots and render only dirty rows. This still scans the
collection; it is not an O(1) per-row signal subscription engine.

Child components, projected slots, virtual lists, integrations, and unsupported
layouts retain compatibility rendering. Direct DOM updates are enabled by default, with an explicit compatibility switch. See
[Direct DOM updates](direct-dom.md) for configuration and coverage.

## Correctness before timing

Keep response and output checks alongside measurements. A shared dependency
edit can legitimately do more work after invalidation is strengthened. Report
both elapsed time and the number of compiled files rather than describing a
skipped rebuild as a speed improvement.

The benchmark report includes raw repeated timings and generated output bytes.
Browser timing covers the JavaScript update cycle, not completed screen painting
or network requests. It should not be used to promise a frame rate on users'
devices.

Import analysis also retains resolved edges when both source text and the
project's source-file set are unchanged. Adding or removing a file invalidates
that resolution snapshot; this matters for extensionless imports and `.js`
imports resolved to authored TypeScript. A rebuild computes affected transitive
parents once, rather than walking each component's dependency closure repeatedly.

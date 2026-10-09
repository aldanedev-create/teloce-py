# Teloce compiler and runtime benchmarks

Baseline: `10f786b9ce99cf62cb2e154a913843b027b20ee7`. Updated source: the implementation accompanying this report. Recorded October 9, 2026.

Python 3.12.14, MinifyJS 0.1.3, Tree-sitter 0.26.0, Chromium 145.0.7632.6. Both revisions ran in the same environment with the same scripts. Builds were measured sequentially, without browser tests running concurrently. These are synthetic workloads, not general application speed guarantees.

## Compiler

Median elapsed milliseconds from five fresh project runs. Each project contains `.html` components, scoped CSS, and a shared TypeScript import. Rebuilds reuse the same Builder. Lower is better.

| Components | Scenario | Before (ms) | After (ms) | Time reduction |
| --- | --- | ---: | ---: | ---: |
| 10 | Cold | 14.42 | 13.48 | 6.5% |
| 10 | Unchanged | 4.79 | 4.24 | 11.4% |
| 10 | One component edit | 5.78 | 5.61 | 3.0% |
| 100 | Cold | 127.96 | 132.18 | -3.3% |
| 100 | Unchanged | 32.61 | 27.24 | 16.4% |
| 100 | One component edit | 33.99 | 27.92 | 17.9% |
| 1000 | Cold | 1208.09 | 1183.67 | 2.0% |
| 1000 | Unchanged | 300.78 | 267.20 | 11.2% |
| 1000 | One component edit | 301.35 | 273.06 | 9.4% |

Negative reductions mean slower elapsed time. Cold-build changes are small and mixed; the strongest compiler gains here are incremental rebuilds.

The shared-TypeScript edit is intentionally excluded from the speed table: the baseline recompiles only the TypeScript module, while the updated dependency graph recompiles the module and all transitive component parents. Raw files retain timings and compiled-file counts for that stronger invalidation behavior.

Production smoke builds include native MinifyJS optimization, source maps, extracted scoped CSS, and hashed assets. They are recorded in the raw build reports, but each production scenario has only one measurement; they are not repeated evidence for a percentage claim. Output byte counts include the shared runtime and generated artifacts; updated runtime features increase output size.

## Browser runtime

Both revisions enable `direct_dom_updates`. Medians of five batches after a warm-up; measurements include state changes and their microtask update cycles, without waiting for screen painting. Text/typing/conditional batches have 200 changes; list text batches have 40 changes; list reorders have 20 reversals of 1,000 rows.

| Workload | Before (ms/batch) | After (ms/batch) |
| --- | ---: | ---: |
| Counter among 200 other bindings | 5.40 | 0.90 |
| Typing and model binding | 2.60 | 2.60 |
| Text beside a conditional | 9.30 | 1.00 |
| Conditional toggles | 7.90 | 4.20 |
| Text beside 1,000 keyed rows | 722.00 | 0.20 |
| Reverse 1,000 keyed rows | 2504.10 | 2673.90 |

The major list-text improvement comes from avoiding any list rendering/patching. Sub-millisecond batches approach timer resolution; use patch counts in the raw data as the stronger explanation, rather than extrapolating a huge speedup multiplier.

Typing was effectively unchanged. Large-list reversal remains costly and was slower in this run. A changed list still renders and reconciles its region; this implementation does not provide per-row signal subscriptions or an optimized minimum-move list algorithm. Direct mode was opt-in at the time of this measurement. The follow-up [large-list report](../large-lists/README.md) covers minimum-move reconciliation, row caching and the new defaults.

## Reproduce

Install the package dependencies, Node for JavaScript checks, and browser tools:

```bash
python -m pip install -e . minifyjs==0.1.3 pytest playwright==1.58.0
python -m playwright install chromium
PYTHONPATH=src python benchmarks/compiler-runtime/build_benchmark.py --output build.json --repeat 5
PYTHONPATH=src python benchmarks/compiler-runtime/runtime_benchmark.py --output runtime.json
TELOCE_BROWSER_TESTS=1 python -m pytest tests/integration/test_targeted_regions_browser.py -q
```

Run the identical benchmark scripts against the baseline source via `PYTHONPATH`, using a separate checkout/output. On Windows, set environment variables using the shell’s corresponding syntax.

Profiling is separate from timing:

```bash
PYTHONPATH=src python benchmarks/compiler-runtime/profile_build.py --output profile.json
```

`profile-after.json` contains a cumulative CPU profile and Python-traced allocation peak for 100 components. That allocation measurement follows a warm-up and excludes native Tree-sitter, Go/esbuild, browser allocations, and whole-process RSS. It is diagnostic data, not a total-memory comparison.

Raw reports: [compiler before](build-before.json), [compiler after](build-after.json), [runtime before](runtime-before.json), [runtime after](runtime-after.json), [profile](profile-after.json).

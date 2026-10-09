# Large lists and production bundling

Baseline: `3b83ee7b1447e5df9c19d906ff604b635596db07` (tree `68d5d8816646dfce074ab554f9dfc3eb61c28f7d`), before this follow-up. Updated source: the implementation accompanying this report. Recorded October 9, 2026.

Python 3.12.14, MinifyJS 0.1.3, Chromium 145.0.7632.6. Both revisions ran the same scripts sequentially on the same machine, without browser tests running concurrently. Results are synthetic workloads, not a general application performance guarantee. Raw samples are committed beside this report.

## List updates

Median milliseconds **per update**, from five batches after one warm-up update. Batches contain ten updates at 100/1,000 rows and two at 10,000 rows. Timings include the state change and microtask completion; they exclude painting. Each scenario follows the preceding scenario in the same mounted app.

| Rows | Operation | Before (ms/update) | After (ms/update) |
| ---: | --- | ---: | ---: |
| 100 | edit | 3.33 | 0.47 |
| 100 | rotate | 7.41 | 0.37 |
| 100 | reverse | 25.90 | 0.37 |
| 100 | insert-delete | 48.86 | 0.73 |
| 1,000 | edit | 27.13 | 2.91 |
| 1,000 | rotate | 72.39 | 2.32 |
| 1,000 | reverse | 296.96 | 3.16 |
| 1,000 | insert-delete | 703.32 | 2.81 |
| 10,000 | edit | 273.50 | 26.60 |
| 10,000 | rotate | 303.95 | 29.20 |
| 10,000 | reverse | 466.85 | 35.20 |
| 10,000 | insert-delete | 702.00 | 39.80 |

A rotation now moves one row per update; a reversal moves N−1 rows. Reversal inherently needs many moves. A single primitive-field edit parses one row template and moves no existing rows. Cached rows still require a collection scan to compare dependency snapshots; this is not constant-time per-row signal subscription.

The update gains combine row caching, minimum-move reconciliation, simple-path readers and a proxy correctness fix. Previously, assigning reordered arrays containing observable rows wrapped those proxies repeatedly; subsequent operations became progressively more expensive. These figures do not isolate the LIS algorithm or establish a speed ranking against other frameworks.

## Production startup and JavaScript size

Five fresh pages per size. Mount time is synchronous component mount, excluding module download and painting. Baseline production used separate minified modules; updated production uses the new default native bundle. Requested bytes include **all JS responses** used by the page. Gzip sizes are estimates from independently compressed responses, not an HTTP-server compression measurement.

| Rows | Before mount (ms) | After mount (ms) | Before JS bytes | After JS bytes | Before gzip bytes | After gzip bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 10.10 | 11.00 | 80,647 | 45,311 | 22,692 | 15,713 |
| 1,000 | 32.60 | 37.60 | 80,647 | 45,311 | 22,692 | 15,712 |
| 10,000 | 223.80 | 267.80 | 80,647 | 45,311 | 22,692 | 15,713 |

**Initial mounting is slower in these samples.** Row dependency-cache setup adds work and memory. The implementation hydrates caches from existing DOM instead of rendering twice, but it still trades initial setup for faster subsequent edits. Use optional fixed-height virtualization or pagination for very large collections. Variable-height virtualization and O(1) row subscriptions remain future work.

Production bundling tree-shakes unused exports and optimizes the resolved graph once. Original modules remain available for independently mounted framework pages, so output-directory size is not the same as bytes downloaded by a bundled page. Applications with different features, imports, or multiple bootstraps will have different sizes.

## Reproduce

Install the project and Playwright, then install Chromium. Run from the repository root with the selected checkout on PYTHONPATH:

```bash
PYTHONPATH=src python benchmarks/large-lists/benchmark.py --output /tmp/list-updates.json
PYTHONPATH=src python benchmarks/large-lists/startup.py --output /tmp/list-startup.json
```

To compare the baseline, archive its `src/` directory into a separate folder and point PYTHONPATH there while retaining these identical benchmark scripts. Run revisions sequentially. The browser tests cover identity, minimum moves, single-row parsing, focus/selection, shared/index dependencies, source-type transitions, cleanup, scoped CSS virtualization, default native bundling, stable aliases, and lazy chunks.

## Follow-up: initialize caches during the first render

Baseline: `b91b59721a3ead1aa5ebc1e84713b6ffe48f1231` (tree `724d7e2af5e0bedde372e5a9da9edf12ddb0ba0c`). This follow-up captures row dependency snapshots and event scopes while generating the initial HTML, then attaches nodes during the existing binding walk. It avoids reevaluating the collection and constructing row scopes in a separate cache setup pass. Supported rows read only their required state roots; unrelated computed getters are not copied into every row.

Same production startup script, five fresh pages per size, same machine and browser. Both revisions use native production bundling. The following paired results supersede the earlier startup comparison for this change:

| Rows | Before mount (ms) | After mount (ms) | Less elapsed time |
| ---: | ---: | ---: | ---: |
| 100 | 10.20 | 9.50 | 6.9% |
| 1,000 | 42.70 | 32.30 | 24.4% |
| 10,000 | 275.80 | 220.10 | 20.2% |

Repeat-update checks use five batches of **20 operations**, following **five warm-up operations** per scenario. The benchmark script now accepts `--iterations` and `--warmup`; its original defaults are unchanged. Times below are milliseconds per operation, excluding paint.

| Rows | Operation | Before (ms/update) | After (ms/update) |
| ---: | --- | ---: | ---: |
| 100 | edit | 0.41 | 0.35 |
| 100 | rotate | 0.42 | 0.36 |
| 100 | reverse | 0.36 | 0.34 |
| 100 | insert-delete | 0.47 | 0.42 |
| 1,000 | edit | 3.00 | 2.74 |
| 1,000 | rotate | 2.64 | 2.93 |
| 1,000 | reverse | 2.60 | 4.25 |
| 1,000 | insert-delete | 2.81 | 3.50 |
| 10,000 | edit | 27.57 | 23.13 |
| 10,000 | rotate | 27.79 | 30.72 |
| 10,000 | reverse | 34.68 | 34.16 |
| 10,000 | insert-delete | 33.66 | 34.26 |

Single-row edits now skip whole-list reconciliation when row order is unchanged. Updates to multiple roots still use one bulk patch, avoiding quadratic repeated scans. Identity, focus, event scopes and cleanup retain the existing behavior.

**Repeated-update timings did not improve uniformly.** In this run, several reorder workloads were slower, particularly 1,000-row reversal. This change improves startup and single-row edits in these samples; it is not a blanket steady-state speedup. Small batch timings, garbage collection and JIT warm-up can vary. Raw samples preserve the observed regressions rather than discarding them.

Raw paired files: `startup-cache-before.json`, `startup-cache-after.json`, `updates-cache-before.json`, and `updates-cache-after.json`. Reproduce the repeat-update comparison with:

```bash
PYTHONPATH=src python benchmarks/large-lists/benchmark.py --iterations 20 --warmup 5 --output /tmp/cache-updates.json
```

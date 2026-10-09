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

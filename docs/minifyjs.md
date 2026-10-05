# MinifyJS: native production builds

Teloce-Py installs `minifyjs>=0.1.3,<0.2` as a dependency. Its wheel includes
esbuild's Go engine, so production minification and bundling require Python
but no Node.js or npm. Linux glibc/musl x86-64 and ARM64, macOS Intel/ARM64,
and Windows x86-64 wheels are available in MinifyJS 0.1.3.

```bash
pip install teloce-py
teloce build --bundle --source-map
```

`minifyjs` is the default production minifier and the default bundler when
`--bundle` is enabled. Development builds and direct `Builder()` calls retain
the conservative Teloce minifier unless `minifier="minifyjs"` is requested.
Bundling remains opt-in. CSS compilation/extraction and template compilation
continue to belong to Teloce.

## Configure a build

```json
{
  "build": {
    "minifier": "minifyjs",
    "minify": true,
    "bundle": true,
    "bundler": "minifyjs",
    "code_splitting": true,
    "hash_assets": true,
    "target": "es2020",
    "charset": "utf8",
    "tree_shake": true,
    "define": {"DEBUG": "false"},
    "drop": ["debugger"],
    "packages": "bundle",
    "external": [],
    "report": "build-report.json"
  }
}
```

`define` values are JavaScript expressions encoded as strings. For a string
constant use a JSON-quoted expression, for example `"API_ENV": "\"production\""`.
`drop=["console"]` also removes the evaluation of console arguments; enable it
only when their side effects are unnecessary. Dependencies are bundled by
default. Use `external` for specific dependencies supplied by an import map,
or `packages="external"` to preserve all package imports. Your host application
must make external imports resolvable in the browser.

The default format is browser ESM. `code_splitting=true` emits lazy imports to
hashed `chunks/` files. With `--no-splitting`, lazy modules are included in the
entry bundle. Deploy every emitted chunk and CSS asset, not just the entry file.

## Python API

```python
from teloce.build import build_project

result = build_project(".", "dist", options={
    "mode": "production", "bundle": True,
    "bundler": "minifyjs", "minifier": "minifyjs",
    "source_maps": True, "report": "build-report.json",
})
print(result["bundle"])
print(result["bundle_outputs"])
print(result["bundle_bytes"])
```

Build results, manifests, and reports list all MinifyJS outputs and their sizes.
`bundle_bytes` includes emitted source-map files. `total_bytes` includes other
compiled/copied files too; it is not the downloaded entry bundle size. Teloce
retains generated modules as intermediate artifacts. Use `bundle_outputs` to
identify the bundle deployment files. Hashes and the source entry's asset map
point at the final native entry. Report builds also save `minifyjs-meta.json`
for dependency and output analysis.

MinifyJS optimizes once after module resolution for bundled builds. Unbundled
production components are optimized individually; their `.vel` source maps
are composed through MinifyJS so minified locations still refer to the component
source. Bundled source maps include inline and sidecar maps. Keep maps private
or disable them when publishing source content is undesirable.

## The Teloce adapter

```python
from minifyjs import Options
from teloce.build import TeloceMinifyJSAdapter, MinifyJSBundler

adapter = TeloceMinifyJSAdapter(Options(
    compress=True, mangle=True, format="esm", target="es2020",
))
# Teloce's adapter writes to the same public path by default.
result = adapter.minify_file("dist/static/app.js")

bundler = MinifyJSBundler(".")
entry = bundler.bundle("dist/static/App.js", minify=True,
                       splitting=True, hash_assets=True)
print(entry, bundler.result.metafile)
```

The adapter subclasses MinifyJS's framework-neutral `Adapter`. It transforms
individual modules and composes compiler source maps. Directory minification
does not resolve imports or perform graph-wide tree shaking. `MinifyJSBundler`
uses the separate `minifyjs.bundle()` API for that work and exposes the native
`Result` as `bundler.result`.

## Existing backends

```bash
teloce build --bundle --bundler teloce --minifier teloce
teloce build --bundle --bundler esbuild
```

The Teloce backend retains its conservative behavior. The esbuild backend still
needs the Node esbuild executable. Native errors fail the build and are reported;
there is no silent fallback to a weaker optimizer. Incremental build signatures
include adapter code, backend options, and the MinifyJS version.

## Upstream references

- [MinifyJS Adapter guide](https://github.com/aldanedev-create/minifyjs/blob/main/docs/python/adapter.md)
- [MinifyJS bundle guide](https://github.com/aldanedev-create/minifyjs/blob/main/docs/python/bundle.md)
- [MinifyJS on PyPI](https://pypi.org/project/minifyjs/)

## Reproduce the comparison

Install Node esbuild only for the independent comparison:

```bash
npm install --save-dev esbuild@0.28.2
python scripts/benchmark_minifyjs.py --esbuild node_modules/.bin/esbuild
```

On the Flask dashboard example at this integration's base revision, with
ES2020, UTF-8, inline component CSS, no source maps, ESM splitting and all
minification passes, the published MinifyJS 0.1.3 output matches Node esbuild
byte-for-byte:

| Runtime | Generated input graph | MinifyJS / Node output | Reduction | Gzip output |
| --- | ---: | ---: | ---: | ---: |
| Self-contained | 35,551 B | 22,180 B | 37.61% | 8,402 B |
| Shared | 105,032 B | 42,048 B | 59.97% | 14,507 B |

Input size is the sum of MinifyJS metafile input bytes for the exact generated
module graph, not `.vel` source size. This measures one example, not a promise
for every application. The script compares the actual entry before Teloce
writes its public aliases, ensuring neither tool receives the other's output.

# Compiler configuration reference

`teloce create` can generate `teloce.config.json`. A minimal development
configuration is:

```json
{
  "compiler": {
    "source_maps": true,
    "target": "es2020"
  },
  "build": {
    "out_dir": "dist",
    "static_dir": "static",
    "clean": false,
    "minify": false,
    "hash_assets": false,
    "extract_css": false,
    "shared_runtime": true,
    "tree_shake": true,
    "bundle": false,
    "lazy_components": []
  }
}
```

Development favors readable output and HMR. Production should use the nested
`build` configuration below. The production CLI defaults enable the shared
runtime, minification, CSS extraction, tree-shaking, clean output, and content
hashes. Source maps remain an explicit choice so teams can keep them private in
release artifacts.

Generated output may include JavaScript, CSS, source maps, a manifest, shared
runtime files, lazy chunks, and a size report. Deploy the complete output set;
copying only the entry module causes lazy imports and runtime files to 404.

Recommended release command:

```bash
teloce build --out-dir dist --source-map --bundle --report
```

The built-in optimizer understands Teloce component imports and filters. It is
not a replacement for a complete JavaScript bundler's whole-program symbol
analysis; enable esbuild when that guarantee is required.

The same release policy can be committed for local builds and CI:

```json
{
  "compiler": { "source_maps": false, "target": "es2020" },
  "build": {
    "out_dir": "dist",
    "static_dir": "static",
    "clean": true,
    "minify": true,
    "hash_assets": true,
    "extract_css": true,
    "shared_runtime": true,
    "tree_shake": true,
    "lazy_components": ["SettingsPage"],
    "bundle": false,
    "report": "build-report.json",
    "max_asset_size": 250000
  }
}
```

Production switches:

- `shared_runtime` writes one `teloce-runtime.<hash>.js` barrel and keeps
  component modules small. The barrel also contains the compiled component
  glue; it is not duplicated in every generated module.
- `minify` compacts generated JavaScript, extracted CSS, and the shared
  runtime. With `bundler: "esbuild"`, esbuild also minifies the whole bundle.
- `extract_css` writes component stylesheets beside their modules and adds
  them to generated `dist/index.html`.
- `tree_shake` removes compiler-known unused local component imports and unused
  browser filters. It cannot prove arbitrary JavaScript side effects are
  unused; use esbuild for whole-application symbol analysis.
- `lazy_components` changes selected imports to dynamic ESM imports. Deploy
  every generated module and chunk, or lazy routes will 404.
- `hash_assets` fingerprints generated modules, runtime, CSS, and copied
  static assets. Stable logical `.js` re-export shims are also emitted, so
  existing Flask/Django/FastAPI templates requesting `/static/js/App.js` keep
  working while browsers cache the hashed implementation.
- `report` records sizes, hashes, copied assets, aliases, and warnings. Set
  `max_asset_size` to surface oversized generated or copied assets in CI.

`--no-hash-assets`, `--no-extract-css`, `--no-minify`, `--no-tree-shake`, and
`--max-size N` are available for controlled debugging or compatibility builds.
Use `teloce dev` for readable HMR artifacts.

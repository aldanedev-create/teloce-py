# Configure a production Teloce build

`teloce.config.json` is the shared build contract for a team. The CLI reads it
from the project root, and `teloce create` generates one automatically. Keep
the file in source control so local builds, CI, and deployment use the same
paths and optimisation settings.

```json
{
  "compiler": {
    "source_maps": false,
    "target": "es2020"
  },
  "build": {
    "out_dir": "dist",
    "static_dir": "static",
    "clean": true,
    "minify": true,
    "shared_runtime": true,
    "tree_shake": true,
    "bundler": "minifyjs",
    "lazy_components": ["SettingsPage"]
  },
  "server": {
    "host": "127.0.0.1",
    "port": 5173,
    "hmr": true
  },
  "watch": {
    "enabled": true,
    "debounce": 300
  }
}
```

Run a production build with:

```bash
python -m teloce build
```

`static_dir` is the authored component directory and public output directory.
With the configuration above, Teloce compiles `static/js/App.vel` to
`dist/static/js/App.js` and does not compile unrelated `.vel` files elsewhere
in the repository. A custom `static_dir` such as `client` produces
`dist/client/js/App.js` and `dist/client/teloce-runtime.js`; configure the
Python framework to serve that same output directory.

`shared_runtime` is enabled by default for project builds. Teloce writes
`dist/static/teloce-runtime.js` once, then generated components import its
common evaluator, reactive state, event, and DOM patch helpers. This prevents
each component from carrying a copy of the runtime. Turn it off only when you
intentionally need a self-contained JavaScript file:

```json
{ "build": { "shared_runtime": false } }
```

`minify` removes compiler-generated formatting from JavaScript, CSS, and the
shared runtime. Keep source maps on for a staging/debug build; turn them off
for a smaller production deployment when browser source mapping is not needed.

For a one-off override, command-line options win where available:

```bash
python -m teloce build --no-minify --source-map
python -m teloce build --hash-assets --report build-report.json
```

Use JSON for `teloce.config.json`. Teloce discovers the configuration from the
current directory or its project root, so run the CLI from the application
root in local development and CI.

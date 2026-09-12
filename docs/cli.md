# Teloce CLI

Install and inspect the command:

```bash
python -m pip install teloce-py
teloce --help
teloce --version
```

Run commands from the project directory containing `static/`, `templates/`, and optional configuration. The CLI discovers the current working directory.

## Fastest workflow: `python app.py`

For the “write a `.vel` file and see it in the browser” workflow, call the builder from your Python entry point:

```python
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=str(ROOT / "dist" / "static"))

@app.get("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    build_project(ROOT, options={"dev": True, "source_maps": True})
    app.run(debug=True, port=5000)
```

Run `python app.py`, then open `http://127.0.0.1:5000`. See [Getting started](getting-started.md) for the complete `App.vel` and HTML files.

## `teloce dev`

Starts the development server, performs an initial build, watches `.vel` and template files, and reloads the browser when HMR is enabled.

```bash
teloce dev
teloce dev --port 5173 --host localhost
teloce dev --no-hmr
teloce dev --proxy http://127.0.0.1:5000
```

Options: `--port`/`-p`, `--host`/`-H`, `--no-hmr`, and `--proxy URL`. When omitted, host and port come from `teloce.config.json` and then fall back to `127.0.0.1:5173`.

## `teloce watch`

Runs a separate watcher and development server:

```bash
teloce watch
teloce watch --out-dir build --port 5173 --host 127.0.0.1
teloce watch --no-hmr
```

Options: `--out-dir`, `--no-hmr`, `--port`, `--host`, and `--proxy`.

## `teloce build`

Builds production assets:

```bash
teloce build
teloce build --out-dir dist --source-map
teloce build --minify --hash-assets --bundle
teloce build --no-clean
```

Options:

- `--out-dir`, `-o`: output directory, default `dist`.
- `--minify` and `--no-minify`: enable or disable minification.
- `--source-map`: emit source maps.
- `--no-clean`: preserve the existing output directory.
- `--hash-assets`: add content hashes to JavaScript and CSS filenames.
- `--bundle`: create a dependency-aware production bundle.
- `--entry FILE`: choose the bundle entry relative to the output directory.

Recommended CI command: `teloce build --out-dir dist --source-map --hash-assets --bundle`.

## `teloce lint`

```bash
teloce lint
teloce lint --strict
teloce lint --fix
```

`--strict` enables strict checks. `--fix` enables available automatic fixes; review the result and run lint again.

## `teloce doctor`

```bash
teloce doctor
teloce doctor --verbose
```

Doctor checks Python and Teloce versions, project discovery, configuration, required directories, and discovered `.vel` files.

## `teloce create`

```bash
teloce create my-app --template flask
teloce create my-api --template fastapi
teloce create my-site --template django
teloce create basic-app --template basic
teloce create flaxon-app --template flaxon
```

Options are `--template`, `--no-install`, and `--no-git`. Templates are `flask`, `fastapi`, `django`, `flaxon`, and `basic`. The `flaxon` template creates a Flaxon + Jinax backend, a compiled `.vel` frontend, an asset route, and a health endpoint. The command validates the project name, creates a `teloce.config.json`, includes `teloce-py` in generated requirements, and refuses unknown templates.

### Generated `teloce.config.json`

Every new project gets explicit defaults that can be committed with the project:

```json
{
  "compiler": { "source_maps": true, "minify": false, "dev": true, "target": "es2020" },
  "build": { "out_dir": "dist", "static_dir": "static", "clean": true },
  "server": { "host": "127.0.0.1", "port": 5173, "hmr": true },
  "watch": { "enabled": true, "debounce": 300 }
}
```

`dev`, `watch`, and `build` load this file automatically. Command-line options override its values.

## `teloce debug`

```bash
teloce debug
teloce debug --port 9000 --host localhost
teloce debug --no-open
```

The command starts a localhost HTTP dashboard, opens it unless `--no-open` is
used, and stays alive until `Ctrl+C`. The default port is `9000`.

The dashboard currently provides:

- project name, root, Python version, platform, and Teloce version;
- discovered `.vel` component paths;
- compile diagnostics for every discovered component;
- pass, error, and warning counts;
- a refresh button that reruns diagnostics;
- JSON endpoints at `/api/health`, `/api/project`, and `/api/diagnostics`.

The dashboard is a local build and diagnostics inspector. It does not yet
provide live runtime component state inspection or production telemetry. Keep
it bound to localhost and do not expose it publicly without authentication.

For the complete dashboard, browser, API, cache, and deployment workflow, see
[Debugging](debugging.md) and [Troubleshooting](troubleshooting.md).

## `teloce benchmark`

```bash
teloce benchmark .
teloce benchmark . --iterations 5
teloce benchmark . --iterations 5 --json
```

Use `--json` for CI and performance tracking.

## `teloce compile`

Compile one component without creating a project:

```bash
teloce compile static/js/App.vel -o dist/js/App.js
teloce compile static/js/App.vel -o dist/js/App.js --source-map
```

The CSS is written beside the JavaScript output. Failed compilation prints a
readable diagnostic with the error code, file, location when available, source
context, and a suggested fix. Use `--json` when an IDE or CI tool needs the
structured diagnostic payload. The default output is next to the source with a
`.js` extension.

```bash
teloce compile static/js/Broken.vel
# ERROR [E1001] static/js/Broken.vel:...
#   Fix: Check that every template, script, style, and HTML element has a matching closing tag.

teloce compile static/js/Broken.vel --json > diagnostics.json
```

The equivalent Python API is:

```python
from pathlib import Path
from teloce.compiler import compile_file

result = compile_file("static/js/App.vel")
if not result["success"]:
    raise RuntimeError(result["diagnostics"])
Path("static/js/App.js").write_text(result["code"], encoding="utf-8")
```

## Command guide

| Need | Command |
|---|---|
| Create a project | `teloce create my-app --template flask` |
| Run Python app and compile first | `python app.py` |
| Develop with Teloce server | `teloce dev` |
| Watch and rebuild | `teloce watch` |
| Production output | `teloce build --hash-assets --bundle` |
| Check setup | `teloce doctor --verbose` |
| Validate templates | `teloce lint --strict` |
| Benchmark compilation | `teloce benchmark . --json` |

## Exit codes and CI

Commands return zero only when their requested operation succeeds. `lint`,
`doctor`, `compile`, and `build` return non-zero for diagnostics or missing
configuration, so they can be used directly in CI. `lint --fix` only applies
safe, known formatting fixes; it does not rewrite arbitrary JavaScript.

For a reproducible pipeline, run `doctor`, strict lint, tests, and the
production build in that order. Keep the generated manifest and all lazy
chunks together when deploying.

# Teloce-Py

<p align="center">
  <img src="https://raw.githubusercontent.com/aldanedev-create/teloce-py/main/assets/py-teloce.jpg" alt="Teloce-Py logo" width="160">
</p>

<p align="center">
  Build interactive Python apps with <code>.vel</code> components. No Node.js required.
</p>

<p align="center">
  <a href="https://pypi.org/project/teloce-py/"><img src="https://img.shields.io/pypi/v/teloce-py" alt="PyPI version"></a>
  <a href="https://github.com/aldanedev-create/teloce-py/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  <a href="https://github.com/aldanedev-create/teloce-py/blob/main/docs/README.md"><img src="https://img.shields.io/badge/docs-read-green" alt="Documentation"></a>
</p>

Teloce-Py compiles a template, browser behavior, and scoped CSS from a single `.vel` file into plain browser assets. Your Python framework (Flask, FastAPI, Django, or Flaxon) keeps handling routes, APIs, databases, auth, and security.

## Features

- **Single-file components:** Template, script, and scoped style in one `.vel` file.
- **Bring your own backend:** Works with Flask, FastAPI, Django, and Flaxon.
- **No Node.js:** Production builds use [MinifyJS](https://github.com/aldanedev-create/teloce-py/blob/main/docs/minifyjs.md), a native esbuild engine bundled in the wheel.
- **Fast builds:** Tree shaking, mangling, code splitting, source maps, and hashed assets.

## Teloce Ecosystem

Teloce is designed to support both Python-based application development and JavaScript-based workflows.

### Teloce-Py

[Teloce-Py](https://github.com/aldanedev-create/teloce-py) is the Python implementation. It lets developers build applications using `.vel` single-file components without requiring Node.js.

It integrates with Python web frameworks and handles component compilation, scoped styles, browser assets, and production builds.

### Teloce-NPM

[Teloce-NPM](https://github.com/aldanedev-create/teloce-npm) is the companion npm project for the Teloce ecosystem.

It provides npm-based tooling and packages for developers working with Teloce and JavaScript-based projects. It complements Teloce-Py by supporting workflows outside the Python package environment.

**Explore Teloce-NPM:**

- [Teloce-NPM repository](https://github.com/aldanedev-create/teloce-npm)
- [Three.js example](https://github.com/aldanedev-create/teloce-npm/tree/main/examples/three-example)

The [Three.js example](https://github.com/aldanedev-create/teloce-npm/tree/main/examples/three-example) demonstrates using Teloce-NPM in a project with Three.js.

Together, Teloce-Py and Teloce-NPM provide different ways to work with the Teloce ecosystem.

## Getting Started

Install:


## Editor Support

Before you start, install the [Teloce extension for VS Code](https://marketplace.visualstudio.com/items?itemName=Flaxon-vscode.teloce-vscode). It adds syntax highlighting, diagnostics, autocomplete, hover information, formatting, and snippets for `.vel` files.

```bash
code --install-extension Flaxon-vscode.teloce-vscode
```

Or open the Extensions panel (`Ctrl+Shift+X` / `Cmd+Shift+X`), search for **Teloce**, and click **Install**. The extension is optional: Teloce-Py works without it.

```bash
python -m pip install teloce-py Flask
```

Create `static/js/App.vel`:

```html
<script>
export default {
  data() { return { count: 0 }; },
  methods: {
    increment() { this.count += 1; }
  }
};
</script>

<template>
  <button @click="increment">Clicked {{ count }} times</button>
</template>
```

Create `app.py`:

```python
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
build_project(ROOT, out_dir=ROOT / "dist", options={"dev": True})

app = Flask(
    __name__,
    static_folder="dist/static",
    static_url_path="/static"
)

@app.get("/")
def home():
    return render_template("app.html")

if __name__ == "__main__":
    app.run(debug=True)
```

Create `templates/app.html`:

```html
<!doctype html>
<html>
  <body>
    <div id="app"></div>
    <script type="module">
      import { mount } from "{{ url_for('static', filename='js/App.js') }}";
      mount("#app");
    </script>
  </body>
</html>
```

Run it and open [http://127.0.0.1:5000](http://127.0.0.1:5000):

```bash
python app.py
```

## Project Structure

```text
my-app/
├── app.py
├── teloce.config.json
├── static/
│   └── js/
│       └── App.vel       # Your source
├── templates/
│   └── app.html          # HTML shell with #app mount
└── dist/                 # Generated, never edit by hand
```

## Production Build

```bash
teloce lint --strict
teloce build --source-map --hash-assets --bundle --report
```

Teloce strips common TypeScript syntax during compilation. The optional `teloce typecheck` command checks scripts and supported template expressions with PyTSCheck.

## Documentation

- [Documentation](https://github.com/aldanedev-create/teloce-py/blob/main/docs/README.md)
- [Network API: http, action, socket](https://github.com/aldanedev-create/teloce-py/blob/main/docs/network-api.md)
- [Project structure](https://github.com/aldanedev-create/teloce-py/blob/main/docs/lessons/file-structure.md)
- [Examples](https://github.com/aldanedev-create/teloce-py/blob/main/examples/README.md):
  - [Flask chat](examples/flask-chat)
  - [FastAPI CMS](https://github.com/aldanedev-create/teloce-py/tree/main/examples/fastapi-cms)
  - [Django Admin](examples/django-admin-vel)
  - [Django scanner](https://github.com/aldanedev-create/teloce-py/tree/main/examples/django-scanner)
  - [Flaxon network](https://github.com/aldanedev-create/teloce-py/tree/main/examples/flaxon-network)
  - [Gallery](https://github.com/aldanedev-create/teloce-py/tree/main/examples/teloce-gallery)

## Status

Teloce-Py is in beta. Pin your version and test generated assets on your target framework and platform.

## License

[MIT](https://github.com/aldanedev-create/teloce-py/blob/main/LICENSE)

## Runtime Contributor Checks

The JavaScript runtime uses JSDoc types with a development-only checker:

```bash
npm ci --ignore-scripts
npm run typecheck
```

See [coverage and workflow](https://github.com/aldanedev-create/teloce-py/blob/main/docs/runtime-typechecking.md).

Runtime files stay `.js`; Python application users do not need Node or TypeScript.

## Optional Component Type Checking

On Python 3.11+, install:

```bash
pip install "teloce-py[typecheck]"
```

Then run:

```bash
teloce typecheck ui
```

Or use JSON output for CI:

```bash
teloce typecheck ui --json
```

This checks TypeScript script blocks, `.ts` files/declarations, and supported template expressions using the bundled PyTSCheck compiler.

See the [type-checking guide](https://github.com/aldanedev-create/teloce-py/blob/main/docs/typecheck.md) for API examples, diagnostic locations, optional dependency handling, and prototype limits.

Plain JavaScript components are skipped. Project tsconfig settings and dependency declarations are inherited automatically; object-style props infer supported constructor types. Props passed to statically imported TypeScript children are validated. Array-style prop values, dynamic children, and some import forms remain limited.

You can also explore this [Teloce-NPM Three.js example](https://github.com/aldanedev-create/teloce-npm/tree/main/examples/three-example).

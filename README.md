<p align="center">
  <img src="https://raw.githubusercontent.com/Flaxon-labs/teloce-py/main/assets/py-teloce.jpg" alt="Teloce-Py logo" width="160"/>
</p>

<h1 align="center">Teloce-Py</h1>

<p align="center">
  Build interactive Python apps with <code>.vel</code> components. No Node.js required.
</p>

<p align="center">
  <a href="https://pypi.org/project/teloce-py/"><img src="https://img.shields.io/pypi/v/teloce-py" alt="PyPI version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  <a href="https://github.com/aldanedev-create/teloce-py/blob/main/docs/README.md"><img src="https://img.shields.io/badge/docs-read-green" alt="Documentation"></a>
</p>

Teloce-Py compiles a template, browser behavior, and scoped CSS from a single
`.vel` file into plain browser assets. Your Python framework (Flask, FastAPI,
Django, or Flaxon) keeps handling routes, APIs, databases, auth, and security.

## Features

- **Single-file components**: template, script, and scoped style in one `.vel` file.
- **Bring your own backend**: works with Flask, FastAPI, Django, and Flaxon.
- **No Node.js**: production builds use [MinifyJS](docs/minifyjs.md), a native esbuild engine bundled in the wheel.
- **Fast builds**: tree shaking, mangling, code splitting, source maps, and hashed assets.

## Getting Started

Install:

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
app = Flask(__name__, static_folder="dist/static", static_url_path="/static")

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

Run it and open <http://127.0.0.1:5000>:

```bash
python app.py
```

## Project Structure

```text
my-app/
├── app.py
├── teloce.config.json
├── static/js/App.vel     # your source
├── templates/app.html    # HTML shell with #app mount
└── dist/                 # generated, never edit by hand
```

## Production Build

```bash
teloce lint --strict
teloce build --source-map --hash-assets --bundle --report
```

Teloce strips common TypeScript syntax but does not type-check.

## Documentation

- [Documentation](https://github.com/aldanedev-create/teloce-py/blob/main/docs/README.md)
- [Project structure](https://github.com/aldanedev-create/teloce-py/blob/main/docs/lessons/file-structure.md)
- [Examples](https://github.com/aldanedev-create/teloce-py/blob/main/examples/README.md): [Flask chat](examples/flask-chat), [FastAPI CMS](https://github.com/aldanedev-create/teloce-py/tree/main/examples/fastapi-cms), [Django Admin](examples/django-admin-vel), [Django scanner](https://github.com/aldanedev-create/teloce-py/tree/main/examples/django-scanner), [Flaxon network](https://github.com/aldanedev-create/teloce-py/tree/main/examples/flaxon-network), [Gallery](https://github.com/aldanedev-create/teloce-py/tree/main/examples/teloce-gallery)

## Status

Teloce-Py is in beta. Pin your version and test generated assets on your target
framework and platform.

## License

[MIT](LICENSE)
### Runtime contributor checks

The JavaScript runtime uses JSDoc types with a development-only checker:

```bash
npm ci --ignore-scripts
npm run typecheck
```

See [coverage and workflow](docs/runtime-typechecking.md). Runtime files stay
`.js`; Python application users do not need Node or TypeScript.

# Getting started: write `.vel`, run `python app.py`

The simplest workflow is exactly this:

1. Put `App.vel` in `static/js/App.vel`.
2. Let `app.py` compile it when the server starts.
3. Run `python app.py`.
4. Open the printed URL in your browser.

Install the package in the same virtual environment as your Python application:

```bash
python -m pip install teloce-py
```

For this repository use `python -m pip install -e .`. A `.vel` file is not served directly: compile it to a browser module, then serve the generated file from your framework's static directory.

```bash
teloce build --out-dir dist --source-map
```

Create this project:

```text
my-app/
  app.py
  templates/index.html
  static/js/App.vel
```

`static/js/App.vel`:

```html
<template>
  <main class="app">
    <h1>{{ title }}</h1>
    <button @click="increment">Clicked {{ count }} times</button>
  </main>
</template>

<script>
export default {
  data() { return { title: "My Python app", count: 0 }; },
  methods: { increment() { this.count++; } }
};
</script>

<style scoped>
.app { max-width: 40rem; margin: 4rem auto; font-family: system-ui; }
</style>
```

`templates/index.html`:

```html
<div id="app"></div>
<script type="module">
  import { mount } from "/static/js/App.js";
  mount("#app");
</script>
```

`app.py`:

```python
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=str(ROOT / "dist" / "static"), template_folder=str(ROOT / "templates"))

@app.get("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    result = build_project(ROOT, options={"dev": True, "source_maps": True})
    print(f"Compiled {result['compiled']} component(s)")
    app.run(debug=True, port=5000)
```

Run it:

```bash
python app.py
```

Visit `http://127.0.0.1:5000`. The server compiles the `.vel` file before Flask starts, serves the generated browser module from `dist/static`, and mounts it into the HTML page.

Use `teloce dev` while developing from the project root. It reads `teloce.config.json`, builds the project, and starts the development server. Use `teloce watch` when you want the standalone watcher workflow.

Keep the Python server responsible for API calls, authorization, cookies, database work, and HTML delivery. Keep browser state and interaction in components.

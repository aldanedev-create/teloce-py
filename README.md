# Teloce-Py



 
 <p align="center">
  <img src="https://raw.githubusercontent.com/Flaxon-labs/teloce-py/main/assets/py-teloce.jpg" alt="teloce-py logo"
   width="200"/>
</p>



Build interactive Python applications with `.vel` files. Teloce-Py compiles
the template, browser behavior, and component CSS into normal browser assets;
Flask, FastAPI, Django, or Flaxon remains responsible for routes, APIs,
databases, authentication, and security.

## The problem it solves

Python teams often maintain a backend template system and a separate frontend
toolchain just to build forms, dashboards, and reactive UI. Teloce keeps the
interactive part in readable `.vel` components while preserving the Python
framework you already use.

## Fast workflow: write `.vel`, run `python app.py`

```text
static/js/App.vel -> app.py builds it -> Python serves the page -> browser runs it
```

Recommended layout:

```text
my-app/
├── app.py
├── teloce.config.json
├── static/js/App.vel         # authored source
├── templates/app.html    # HTML shell and #app mount
└── dist/                   # generated output; never edit by hand
```

## Copy-paste Flask example

Install:

```bash
python -m pip install teloce-py Flask
```

Create `static/js/App.vel`:

```html

<script>
export default {
  data() { return { draft: "", messages: [] }; },
  async mounted() { this.messages = await fetch("/api/messages").then(r => r.json()); },
  methods: {
    async send() {
      const text = this.draft.trim();
      if (!text) return;
      const message = await fetch("/api/messages", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text})
      }).then(r => r.json());
      this.messages = [...this.messages, message];
      this.draft = "";
    }
  }
};
</script>

<template>
  <main class="chat">
    <h1>Quick chat</h1>
    <ul>
      <li v-for="message in messages" :key="message.id">{{ message.text }}
      </li>
      </ul>
    <form @submit.prevent="send">
      <input v-model="draft" aria-label="Message" />
      <button>Send</button>
    </form>
  </main>
</template>

<style scoped>
.chat { max-width: 40rem; margin: 3rem auto; padding: 1rem; font: 1rem system-ui; }
form { display: flex; gap: .5rem; } input { flex: 1; padding: .7rem; }
</style>
```

Create `app.py`. It builds automatically, so the only development command is
`python app.py`:

```python
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from teloce.build import build_project

ROOT = Path(__file__).parent
build_project(ROOT, out_dir=ROOT / "dist", options={"dev": True})
app = Flask(__name__, static_folder="dist/static", static_url_path="/static")
messages = []

@app.get("/")
def home():
    return render_template("app.html")

@app.get("/api/messages")
def list_messages():
    return jsonify(messages)

@app.post("/api/messages")
def create_message():
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
    if not text or len(text) > 500:
        return jsonify({"error": "Message must contain 1-500 characters"}), 400
    message = {"id": len(messages) + 1, "text": text}
    messages.append(message)
    return jsonify(message), 201

if __name__ == "__main__":
    app.run(debug=True)
```

Create `templates/app.html`:

```html
<!doctype html><html><head><meta charset="utf-8"><title>Quick chat</title></head>
<body><div id="app"></div>
<script type="module">import { mount } from "{{ url_for('static', filename='js/App.js') }}"; mount("#app");</script>
</body></html>
```


Run it:

```bash
python app.py
```

Open `http://127.0.0.1:5000`. This is a real Flask API and compiled `.vel`
UI; it uses in-memory messages for a small demonstration. Add a database,
authentication, CSRF protection, and rate limits before production use.

## Flaxon and WebSockets

Flaxon is the async option when the app needs rooms and real-time events. The
verified pattern is `accept()`, `join(room)`, `receive_json()`, and
`broadcast_json(room, data)`:

```python
from flaxon import Flaxon
from flaxon.websocket import WebSocket

app = Flaxon("chat", debug=True)

@app.websocket("/ws/chat/<room_id>")
async def chat(socket: WebSocket, room_id: str):
    await socket.accept()
    await socket.join(room_id)
    try:
        async for message in socket.iter_json():
            await socket.broadcast_json(room_id, {
                "text": str(message.get("text", ""))[:500]
            })
    finally:
        await socket.leave(room_id)
```

Serve the generated asset directory with Flaxon and run the framework's
Flaxon command (`python -m flaxon run app:app --reload`). Use `wss://` behind
HTTPS. The Flask example above intentionally uses ordinary HTTP so it can be
started reliably with only `python app.py`.

## Release checks

```bash
teloce lint --strict
teloce build --source-map --hash-assets --bundle --report
python -m pytest -q
python -m build --sdist --wheel
python -m twine check dist/*
```

Use `--bundler esbuild` for whole-program tree-shaking, code splitting, and
minification. Teloce supports limited common TypeScript syntax stripping, not
full TypeScript type-checking. Read the [documentation](docs/README.md),
[optimized structure lesson](docs/lessons/file-structure.md), and
[all examples](examples/README.md): [`examples/flask-chat`](examples/flask-chat), [`examples/config-driven-flask`](examples/config-driven-flask),
[`examples/fastapi-cms`](examples/fastapi-cms), [`examples/django-scanner`](examples/django-scanner),
[`examples/django-admin-vel`](examples/django-admin-vel), [`examples/flaxon-network`](examples/flaxon-network), and [`examples/teloce-gallery`](examples/teloce-gallery).

## Status

Teloce-Py is beta software. Pin versions and test generated browser assets in
the Python framework and deployment platform you support.

## License

MIT

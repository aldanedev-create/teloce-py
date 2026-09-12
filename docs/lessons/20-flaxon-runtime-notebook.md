# Lesson 20: Build a Flaxon notebook with the standalone runtime

This small example adds Teloce behavior to HTML rendered by Flaxon and Jinax. It is useful for beginners because there is no compiler configuration and no frontend build tool: Python serves the page, the standalone runtime finds the mount element, browser state makes the notebook interactive, and an explicit signal drives the save-status indicator.

The complete example is in [`examples/flaxon-runtime-notebook`](../../examples/flaxon-runtime-notebook/).

## What you will build

The notebook has:

- a Flaxon and Jinax HTML shell;
- a list of notes;
- a new-note action;
- note selection;
- title and body editing;
- save and delete actions;
- reactive `v-if`, `v-for`, interpolation, and event handlers;
- a health endpoint at `/api/health`.

This version keeps data in browser memory so the runtime is easy to understand. Refreshing the page resets the sample notes. Later, replace the state with IndexedDB for local persistence or call a Flaxon API backed by SQLite/PostgreSQL for durable data.

## Step 1: create the project

```text
runtime-notebook/
├── app.py
├── build.py
├── requirements.txt
├── templates/index.html
└── dist/teloce-standalone.js   # generated, do not edit
```

Install dependencies:

```bash
python -m pip install flaxon teloce-py
```

## Step 2: copy the runtime during the build

Create `build.py`:

```python
from importlib.resources import files
from pathlib import Path
import shutil

ROOT = Path(__file__).parent
DIST = ROOT / 'dist'

DIST.mkdir(parents=True, exist_ok=True)
source = files('teloce.runtime').joinpath('standalone.js')
destination = DIST / 'teloce-standalone.js'
with source.open('rb') as input_file, destination.open('wb') as output_file:
    shutil.copyfileobj(input_file, output_file)
```

`standalone.js` is a browser file inside the installed Teloce-Py package. `importlib.resources` finds it reliably in a virtual environment, wheel, or normal source installation. Never import it from a hard-coded path inside `site-packages`.

## Step 3: serve the runtime from Flaxon

Create `app.py`:

```python
import mimetypes
from pathlib import Path

from flaxon import Flaxon
from flaxon.http.response import Response
from flaxon.jinax import Jinax

ROOT = Path(__file__).parent
DIST = (ROOT / 'dist').resolve()
app = Flaxon('runtime-notebook', debug=True)
app.use_templates(Jinax(str(ROOT / 'templates'), auto_reload=True))

for path in DIST.rglob('*'):
    if not path.is_file():
        continue
    relative = path.relative_to(DIST).as_posix()
    media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'

    async def serve_asset(request, file_path=path, content_type=media_type):
        return Response(file_path.read_bytes(), media_type=content_type)

    app.get(f'/assets/{relative}')(serve_asset)

@app.get('/')
async def home(request):
    return await request.render('index.html', {'title': 'Flaxon Notebook'})

@app.get('/api/health')
async def health():
    return {'ok': True, 'service': 'runtime-notebook'}
```

The asset route exposes `dist/teloce-standalone.js` as `/assets/teloce-standalone.js`. The browser can only use the runtime after the Python server gives it a URL. The signals example also exposes `dist/signals.js` and `dist/scheduler.js` as browser modules.

## Step 4: mount the runtime in Jinax

Create `templates/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
  </head>
  <body>
    <div id="app">
      {% raw %}
      <h1>Runtime notebook</h1>
      <button @click="add">Add a note</button>
      <p v-if="notes.length === 0">No notes yet.</p>
      <button v-for="note in notes" :key="note.id" @click="select(note.id)">{{ note.title }}</button>
      {% endraw %}
    </div>

    <script src="/assets/teloce-standalone.js"></script>
    <script>
      teloce.createApp('#app', {
        notes: [{ id: 1, title: 'First note' }],
        nextId: 2,
        add() {
          this.notes.push({ id: this.nextId, title: 'New note' })
          this.nextId++
        },
        select(id) {
          console.log('Selected note:', id)
        }
      })
    </script>
  </body>
</html>
```

The `{{ title }}` in the document head is Jinax server interpolation. The `{{ note.title }}` inside the mounted application is Teloce interpolation. Keep that distinction in mind: Jinax runs in Python before the response reaches the browser; Teloce runs in the browser after the runtime mounts. The `{% raw %}` block prevents Jinax from trying to evaluate Teloce expressions on the server.

## Add signals to the notebook

The complete example uses explicit signals for a small piece of shared browser state: the save-status label. The build copies `signals.js` and its `scheduler.js` dependency into `dist/`, and the page imports them as an ES module:

```html
<p id="save-state">Ready</p>
<script type="module">
  import { createSignal, createEffect } from '/assets/signals.js'

  const saveState = createSignal('Ready')
  const label = document.querySelector('#save-state')
  const saveEffect = createEffect(() => { label.textContent = saveState() })

  saveState.set('Editing')
  saveState.set('Saved')
</script>
```

The notebook calls `saveState.set('Editing')` when a note is selected, `saveState.set('New note')` when creating one, and `saveState.set('Saved')` after saving. Component-style notebook data still uses the standalone runtime proxy; the signal is useful because it is independently observable by the status effect. In a larger application, keep the effect object and call `saveEffect.stop()` when the page or feature is destroyed.

## Step 5: run the complete notebook example

```bash
python build.py
python -m flaxon run app:app --reload
```

Open <http://127.0.0.1:8000>. Use the browser DevTools Network tab to confirm:

```text
GET /                    200
GET /assets/teloce-standalone.js  200
GET /api/health          200
```

The full repository example uses a sidebar, form, selection, save, delete, responsive CSS, and a browser-memory note store. Start with that example when you want a complete copy-pasteable notebook rather than the tiny learning version.

## How the runtime makes it reactive

`createApp('#app', initialState)` does the following:

1. finds the `#app` element;
2. captures its initial HTML;
3. wraps the state in a reactive proxy;
4. renders interpolation and directives;
5. attaches event listeners;
6. rerenders when a state property or nested array/object changes.

For text fields, the full standalone runtime rerenders the mount root after state changes. The complete example therefore reads the title and body from the form when Save is clicked instead of rerendering on every keystroke. This keeps typing stable and is a useful pattern for small editors.

## Moving from memory to real storage

For one user's offline notebook, use IndexedDB in a browser service and load saved notes before mounting. For shared notes, send changes to Flaxon:

```html
<script>
async function saveToServer(note) {
  const response = await fetch('/api/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(note)
  })
  if (!response.ok) throw new Error('Could not save note')
  return response.json()
}
</script>
```

Validate title/body lengths and permissions in Python. Client reactivity improves the interface; it is not a security boundary.

## Troubleshooting this example

- If the page is static, run `python build.py` and confirm the runtime URL returns JavaScript.
- If the page is blank, confirm `id="app"` exists before `teloce.createApp()` runs.
- If notes do not update, check the browser console and verify event method names.
- If the runtime URL is `404`, confirm Flaxon registered the generated `dist` file before serving requests.
- If typing jumps or clears, avoid `v-model` for every keystroke in a root that fully rerenders; read form values on Save as this example does.
- If data disappears after refresh, that is expected for this learning version; add IndexedDB or a Python database.

For compiled `.vel` components instead of server-rendered HTML, read [How Teloce-Py works](16-how-teloce-works.md) and [Signals and reactivity](19-signals-and-reactivity.md).

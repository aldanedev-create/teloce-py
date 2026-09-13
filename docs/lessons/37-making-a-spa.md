# Lesson 37: Make a single-page app with Teloce-Py

This lesson shows how to build a real single-page application (SPA) with
multiple .vel pages, a Python backend, and Teloce's automatic file-based
router.

The fast workflow is:

```text
create static/js/pages/HomePage.vel -> run the Python app -> open the browser
```

You do not need to hand-write a JavaScript route table for conventional page
names. Teloce discovers the pages, compiles them, and generates the browser
router.

## What a SPA is

A single-page application loads one HTML shell. Navigation changes the visible
page without requesting a new HTML document. Python still handles API
requests, authentication, database access, background jobs, and security.

| Layer | Responsibility |
|---|---|
| Python framework | HTML shell, APIs, authentication, database, jobs |
| Teloce build | Compile .vel files and generate browser modules |
| Generated router | Match URLs and mount or unmount page components |
| .vel pages | Interactive UI, local state, events, and presentation |
| Browser | DOM, hash/history, fetch, storage, and user interaction |

The router is not an authorization system. Every protected Python endpoint
must authenticate and authorize its request independently.

## Recommended project structure

```text
my-spa/
├── app.py
├── teloce.config.json
├── static/
│   └── js/
│       ├── App.vel
│       └── pages/
│           ├── HomePage.vel
│           └── SettingsPage.vel
└── templates/
    └── index.html
```

The pages directory is the important part. A project with static/js/pages
containing at least one .vel or .js page automatically gets
dist/static/js/router.js.

## Page filenames become routes

| Source page | Browser route |
|---|---|
| pages/HomePage.vel | / |
| pages/index.vel | / |
| pages/SettingsPage.vel | /settings |
| pages/account/ProfilePage.vel | /account/profile |
| pages/projects/[id].vel | /projects/:id |
| pages/docs/[...path].vel | /docs/*path |
| pages/[[slug]].vel | /:slug? |

The Page suffix is removed from a URL. A dynamic filename in square brackets
becomes a route parameter. Keep reusable controls in components, not pages.

## Step 1: Create App.vel

Create static/js/App.vel:

```html
<script>
import AppHeader from "./components/AppHeader.vel";
import router from "./router.js";
import router from "./router.js";

export default {
  components: { AppHeader },
  data() {
    return { stopRouter: null };
  },
  methods: {
    navigate(path) {
      router.push(path);
    }
  },
  mounted() {
    const outlet = document.querySelector("#router-view");
    if (!outlet) throw new Error("SPA outlet #router-view was not found");
    this.stopRouter = router.mount(outlet);
  },
  beforeUnmount() {
    this.stopRouter?.();
    router.destroy();
  }
};
</script>

<template>
  <div class="app-shell">
    <AppHeader title="Learning Hub" @navigate="navigate"></AppHeader>
    <main id="router-view" aria-live="polite"></main>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; background: #f5f7fb; color: #172033; }
main { max-width: 72rem; margin: auto; padding: 2rem 5vw; }
</style>
```

The HTML shell mounts App.js once. App.vel then mounts the active page inside
router-view. This avoids replacing the whole application shell during
navigation.

## Reuse components across SPA pages

Put shared UI in static/js/components. Import a .vel component from App.vel,
register it in the components object, and use its element in the template.
Teloce resolves the source import to the generated JavaScript module during
the build.

Create static/js/components/AppHeader.vel:

```html
<script>
export default {
  props: {
    title: String
  }
};
</script>

<template>
  <header class="topbar">
    <a class="brand" href="#/" @click.prevent="$emit('navigate', '/')">
      {{ title }}
    </a>
    <nav aria-label="Main navigation">
      <a href="#/" @click.prevent="$emit('navigate', '/')">Home</a>
      <a href="#/settings" @click.prevent="$emit('navigate', '/settings')">Settings</a>
      <a href="#/projects/42" @click.prevent="$emit('navigate', '/projects/42')">Project 42</a>
    </nav>
  </header>
</template>

<style scoped>
.topbar { display: flex; justify-content: space-between; gap: 1rem; padding: 1rem 5vw; background: #172033; color: white; }
.brand { color: white; font-weight: 800; text-decoration: none; }
nav { display: flex; flex-wrap: wrap; gap: 1rem; }
nav a { color: #cbd5e1; text-decoration: none; }
nav a:hover { color: white; }
</style>
```

App.vel now uses the component:

```html
<script>
import AppHeader from "./components/AppHeader.vel";

export default {
  components: { AppHeader },
  methods: {
    navigate(path) {
      router.push(path);
    }
  }
};
</script>

<template>
  <AppHeader title="Learning Hub" @navigate="navigate"></AppHeader>
</template>
```

In the full App.vel example above, navigate calls the imported router. The
child emits an event and the parent decides what navigation should happen.
This keeps the header reusable in another SPA with a different router or
navigation policy.

Components can also receive page data:

```html
<RepoCard :repository="repository" @open="openRepository"></RepoCard>
```

The parent registers RepoCard and provides the repository prop. The child can
emit open with $emit('open', repository.id). Keep components focused: pages
coordinate route and API state, while components render reusable UI.

## Step 2: Create HomePage.vel

Create static/js/pages/HomePage.vel:

```html
<script>
export default {
  data() {
    return {
      count: 0,
      message: "This view was compiled from HomePage.vel"
    };
  },
  methods: {
    addPoint() {
      this.count += 1;
    }
  }
};
</script>

<template>
  <section class="page">
    <p class="eyebrow">Teloce SPA</p>
    <h1>Build without a route table.</h1>
    <p>{{ message }}</p>
    <button type="button" @click="addPoint">Points: {{ count }}</button>
    <p><a href="#/settings">Open settings</a></p>
  </section>
</template>

<style scoped>
.page { padding: 2rem 0; }
.eyebrow { color: #5267d9; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
h1 { max-width: 36rem; font-size: clamp(2rem, 6vw, 4rem); line-height: 1; }
button { border: 0; border-radius: .6rem; padding: .7rem 1rem; background: #5267d9; color: white; cursor: pointer; }
</style>
```

## Step 3: Create SettingsPage.vel

Create static/js/pages/SettingsPage.vel:

```html
<script>
export default {
  data() {
    return { compact: false, saved: false };
  },
  methods: {
    save() {
      this.saved = true;
    }
  }
};
</script>

<template>
  <section class="page">
    <p class="eyebrow">Settings</p>
    <h1>Page state is isolated.</h1>
    <label>
      <input type="checkbox" v-model="compact">
      Use compact layout
    </label>
    <p v-if="compact">Compact mode is enabled.</p>
    <p v-else>Comfortable mode is enabled.</p>
    <button type="button" @click="save">Save preference</button>
    <span v-if="saved" role="status"> Saved locally.</span>
    <p><a href="#/">Back home</a></p>
  </section>
</template>

<style scoped>
.page { padding: 2rem 0; }
.eyebrow { color: #5267d9; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
label { display: flex; align-items: center; gap: .5rem; margin: 1.5rem 0; }
button { border: 0; border-radius: .6rem; padding: .7rem 1rem; background: #172033; color: white; cursor: pointer; }
</style>
```

The links use hash URLs because hash mode is the default. The router listens
for hash changes, resolves the matching page, unmounts the previous page, and
mounts the new one.

## Step 4: Add a dynamic page

Create static/js/pages/projects/[id].vel:

```html
<script>
export default {
  props: { id: String }
};
</script>

<template>
  <section>
    <p class="eyebrow">Project</p>
    <h1>Project {{ id }}</h1>
    <p>The id value came from the /projects/:id route parameter.</p>
    <a href="#/">Back home</a>
  </section>
</template>

<style scoped>
section { padding: 2rem 0; }
.eyebrow { color: #5267d9; font-weight: 800; text-transform: uppercase; }
</style>
```

Open #/projects/42. The router matches projects/:id and passes id=42 to the
component. Keep authorization and project lookup on the Python API; a browser
route parameter is never trusted.

## Step 5: Add the HTML shell

Create templates/index.html:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Learning Hub</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module">
      import { mount } from "{{ url_for('static', filename='js/App.js') }}";
      mount("#app");
    </script>
  </body>
</html>
```

The server must serve the compiled dist/static directory. It must not point
the browser at source .vel files.

## Step 6: Connect Flask

Create app.py:

```python
from pathlib import Path

from flask import Flask, jsonify, render_template
from teloce.build import build_project


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

app = Flask(
    __name__,
    static_folder=str(DIST / "static"),
    template_folder=str(ROOT / "templates"),
)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "learning-hub"})


if __name__ == "__main__":
    build_project(
        ROOT,
        out_dir=DIST,
        options={"dev": True, "clean": True, "source_maps": True},
    )
    app.run(debug=True, port=5000)
```

Install and run:

```bash
python -m pip install teloce-py Flask
python app.py
```

Open http://127.0.0.1:5000. Click Home, Settings, and Project 42. The Python
health endpoint remains available at /api/health.

## Configuration

Automatic discovery is the default. A configuration file can make the choice
visible to a team:

```json
{
  "build": {
    "spa": "auto",
    "spa_mode": "hash",
    "shared_runtime": true,
    "source_maps": true
  }
}
```

The normal commands are:

```bash
teloce dev
teloce build
teloce build --spa
```

Use build --spa when a missing pages directory should be a build error. Use
build --no-spa for a deliberately multi-page build. A project without pages
remains a normal Teloce application.

## Custom route names

Conventional filenames need no route configuration. If an existing component
has a descriptive filename that does not express its URL, add one override:

```json
{
  "build": {
    "spa": "auto",
    "spa_routes": {
      "RepoPage.js": "/repo/:id"
    }
  }
}
```

The key is the compiled logical page filename relative to the pages directory.
The value is the browser route. Use this for legacy URLs or compatibility with
an existing application. For a fully convention-based project, no route table
is needed.

## Hash mode and history mode

Hash mode produces URLs such as:

```text
http://127.0.0.1:5000/#/settings
```

This is the safest default for Flask, FastAPI, Django, and Vercel because the
server only needs to return the shell at /. Refreshing keeps the same document.

History mode produces clean URLs such as /settings:

```json
{
  "build": {
    "spa": "auto",
    "spa_mode": "history",
    "spa_base": "/"
  }
}
```

The server or hosting platform must rewrite every client route to the shell.
Without that fallback, clicking can work while refreshing /settings returns
404. Hash mode is usually the right first deployment choice.

## FastAPI and Django

The generated browser assets are framework-neutral. FastAPI should mount
dist/static at /static and return the same HTML shell:

```python
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory=DIST / "static"), name="static")
```

Django should include the generated directory in static files, then run the
Teloce build before collectstatic:

```python
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "dist" / "static"]
```

The browser entry point remains:

```html
<script type="module">
  import { mount } from "/static/js/App.js";
  mount("#app");
</script>
```

Hash mode avoids a catch-all route in both frameworks. History mode requires a
framework or platform fallback.

## Add backend data

Fetch data from a Python endpoint in a page component:

```html
<script>
export default {
  data() {
    return { status: "Loading...", items: [] };
  },
  async mounted() {
    try {
      const response = await fetch("/api/items");
      if (!response.ok) throw new Error("API request failed");
      this.items = await response.json();
      this.status = "Loaded";
    } catch (error) {
      this.status = error.message || "Could not load items";
    }
  }
};
</script>

<template>
  <section>
    <p>{{ status }}</p>
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.name }}</li>
    </ul>
  </section>
</template>
```

Do not put database credentials, authorization decisions, or private API keys
in a .vel file. Browser code is public.

## Cleanup when navigating

The router unmounts the previous page before mounting the next one. Release
every resource created by a page:

```html
<script>
export default {
  data() {
    return { seconds: 0, timer: null };
  },
  mounted() {
    this.timer = window.setInterval(() => {
      this.seconds += 1;
    }, 1000);
  },
  beforeUnmount() {
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }
};
</script>
```

Apply the same rule to event listeners, signal effects, WebSockets, media
streams, editors, observers, and Three.js resources. Without cleanup,
repeated navigation can duplicate work and leak memory.

## Testing checklist

```bash
teloce build
python -m pytest -q
node --check dist/static/js/App.js
node --check dist/static/js/router.js
```

Then test in a real browser:

1. Load the root page.
2. Open every navigation link.
3. Confirm each URL and page content.
4. Confirm the previous page is removed.
5. Exercise buttons, forms, loading states, and API errors.
6. Refresh in hash mode.
7. Open a dynamic route such as #/projects/42.
8. Check the Network panel for 404 responses.
9. Check the console for module and lifecycle errors.
10. Navigate repeatedly to detect duplicate timers or listeners.

## Troubleshooting

### Blank screen

Confirm that App.js, router.js, and the page modules exist under dist/static.
Confirm that the HTML shell mounts App.js and that App.vel contains
router-view. Inspect the browser Network panel and run node --check on the
generated modules.

### Router file is 404

The framework is probably serving the source static directory instead of
dist/static. Point the framework static directory at the build output.

### Navigation does nothing

Check the hash URL and the generated const routes declaration. A custom page
filename may need spa_routes. A route parameter must use a bracket filename
such as projects/[id].vel.

### Clean URL refresh returns 404

History mode is active without a server fallback. Switch to hash mode or
rewrite every client route to the HTML shell.

## What this proves

This workflow demonstrates a practical boundary:

- developers organize pages as .vel files;
- Teloce compiles the pages and generates the router;
- the shared runtime is reused by generated components;
- Python remains free to use Flask, FastAPI, Django, or Flaxon;
- the result is ordinary browser JavaScript and CSS;
- Node.js is not required at runtime.

For larger applications, add reusable components, a service layer for API
calls, route tests, lazy loading for large screens, asset hashing, source maps,
and bundle-size reporting.

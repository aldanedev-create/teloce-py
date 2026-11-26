# Router

The generated router supports route parameters, optional parameters, wildcards, query strings, navigation, history, and reactive route state. Keep authorization on the Python server; browser routing is not access control.

Use the router for client view state and normal Python endpoints for data. Test navigation and refresh behavior in a real browser.

## Minimal setup

For a normal SPA, you usually do not write a route table at all. Create page
components under static/js/pages and run the ordinary build:

```text
static/
└── js/
    ├── App.vel
    └── pages/
        ├── HomePage.vel
        └── SettingsPage.vel
```

```bash
teloce build
```

Teloce automatically compiles the pages and generates
dist/static/js/router.js. The default file conventions are:

| Page file | Generated route |
|---|---|
| pages/HomePage.vel or pages/index.vel | / |
| pages/SettingsPage.vel | /settings |
| pages/repo/[id].vel | /repo/:id |
| pages/docs/[...path].vel | /docs/*path |

The generated router uses hash mode by default, so it works on ordinary Flask,
FastAPI, Django, and serverless hosting without a history fallback. Add one
mount in the application shell:

```html
<div id="router-view"></div>
<script type="module">
  import router from "/static/js/router.js";
  router.mount(document.querySelector("#router-view"));
</script>
```

Set "spa": false in teloce.config.json, or use teloce build --no-spa, when
the pages directory is intentionally not a client-side application.

For advanced applications that need explicit metadata, use the declarative
helper instead of the low-level compiler and generator APIs:

```python
from teloce.router import generate_router

generate_router("dist/static/js/router.js", {
    "/": "./pages/HomePage.js",
    "/repo/:id": "./pages/RepoPage.js",
})
```

JavaScript module paths are imported automatically and their component names
are derived from the filenames. Use a route object when you need metadata or
props:

```python
generate_router("dist/static/js/router.js", {
    "/": {"component": "HomePage", "import": "./pages/HomePage.js"},
    "/repo/:id": {"component": "RepoPage", "import": "./pages/RepoPage.js", "props": True},
})
```

Use `RouterCompiler` and `RouterGenerator` directly only when building a
custom router pipeline or framework integration.

## Route concepts

The generated router supports routes such as:

```text
/                 home
/users/:id        required parameter
/posts/:slug?     optional parameter
/docs/*           wildcard path
```

Query values are separate from path parameters. A route can read the current
path, params, query, and full URL, then navigate with push, replace, back,
forward, or a numeric history step.

The router is a browser view mechanism, not a security mechanism. The Python
server must validate the user and authorize every data request, including
requests made after client-side navigation. Configure server fallback routes
if refreshing a client route should return the application shell.

## Lifecycle and lazy routes

Unmount the previous view before mounting the next one. Component disposers,
event listeners, timers, subscriptions, editors, and WebGL resources must be
released from the component lifecycle. Lazy components should be used for
infrequently opened screens; keep the initial route small and show a loading
and error state for dynamic imports. See the [runtime reference](runtime-reference.md)
and [troubleshooting guide](troubleshooting.md) for failure diagnosis.

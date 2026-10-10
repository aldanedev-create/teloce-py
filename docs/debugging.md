# Debugging `.vel` applications

Teloce applications have several layers. Debug the layer that owns the failure:

```text
.vel source -> compiler -> generated JavaScript/CSS -> browser runtime -> Python API -> database/deployment
```

## Start with the compiler

```bash
teloce doctor --verbose
teloce lint --strict
teloce build --out-dir dist --source-map
```

Fix the first diagnostic before changing later files. Confirm that the entry component and every imported `.vel` file appear in the build summary.

For an isolated component:

```python
from teloce.compiler import compile_file

result = compile_file("static/js/App.vel")
if not result["success"]:
    for diagnostic in result["diagnostics"]:
        print(diagnostic)
```

## Where `.vel` files go

In the standard project layout, `.vel` files belong under the browser source directory, usually `static/js/`:

```text
my-app/
├── app.py                  # Python server
├── templates/index.html    # HTML shell and mount point
├── static/
│   ├── js/
│   │   ├── App.vel         # entry component
│   │   └── components/
│   │       └── SearchCard.vel
│   └── images/
└── dist/                   # optional generated output
```

The exact directory can be changed by project configuration, but the important rule is consistency: the compiler source root, the import paths, and the server's static route must agree. Do not put `.vel` files in `templates/`; templates are server-rendered HTML/Jinja/Jinax. Do not put application `.vel` source in `dist/` or `public/` if those directories are generated output.

An import is relative to the importing `.vel` file:

```html
<script>
import SearchCard from './components/SearchCard.vel'
import EmptyState from './components/EmptyState.vel'
</script>
```

The source-to-output relationship normally looks like:

```text
static/js/App.vel                    -> dist/static/js/App.js
static/js/components/SearchCard.vel  -> dist/static/js/components/SearchCard.js
static/js/components/SearchCard.css  -> dist/static/js/components/SearchCard.css
```

Always edit the `.vel` source. Generated `.js` and `.css` files are evidence for debugging, not files to maintain manually. If the generated file is missing, first check discovery and the build output directory. If it exists but the browser cannot load it, check the Python static route and the URL shown in DevTools Network.

## Follow one feature through every layer

For a missing search result, button, or animation, trace it in this order:

1. Is the `.vel` file in the discovered source root?
2. Did `teloce lint --strict` report a parser or import error?
3. Did `teloce build` generate the expected module?
4. Does the HTML shell mount the correct generated module or router?
5. Does the browser request the module with status `200` and JavaScript content type?
6. Did the component mount hook run?
7. Did an API request return the shape the template expects?
8. Did a reactive update rerender or replace the DOM you were inspecting?

This prevents changing Python, CSS, and `.vel` code at the same time and losing the original cause.

## Use the debug dashboard

```bash
teloce debug
teloce debug --port 9000 --host 127.0.0.1 --no-open
```

Open `http://127.0.0.1:9000`. The local dashboard shows the project root, Python and Teloce versions, discovered `.vel` paths, compile diagnostics, pass/error/warning totals, and a Refresh action.

Its JSON endpoints are useful in scripts and CI:

```bash
curl http://127.0.0.1:9000/api/health
curl http://127.0.0.1:9000/api/project
curl http://127.0.0.1:9000/api/diagnostics
```

The dashboard is a diagnostics inspector. It does not inspect live component state, browser storage, server logs, or production traffic. Keep it bound to localhost.

## Check the browser boundary

Use DevTools Console, Network, and Application tabs. Verify generated `.js` and `.css` files return `200`, inspect API response JSON, and check service workers, Cache Storage, and IndexedDB.

Test a user flow, not only page load:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("http://127.0.0.1:5000")
    field = page.locator("input[aria-label='Search']")
    field.fill("python")
    assert field.input_value() == "python"
    page.locator("form.search-form button[type=submit]").click()
    browser.close()
```

If typing clears, a parent `@input` handler is probably changing reactive state on every keystroke. Use `v-model` locally and a separate custom event with `@input.stop` for suggestions.

For a compiled component, add temporary browser logs at lifecycle boundaries:

```html
<script>
export default {
  mounted() { console.log('mounted SearchPage') },
  updated() { console.log('updated SearchPage') },
  beforeUnmount() { console.log('unmounting SearchPage') }
}
</script>
```

Remove noisy logs before release or guard them behind a development flag. If `mounted` never appears, the problem is usually discovery, import resolution, router selection, or the mount target—not the API.

## Check API and Python separately

```bash
curl http://127.0.0.1:5000/api/health
curl "http://127.0.0.1:5000/api/search?q=python"
```

If the API is correct but the UI is empty, compare the response shape with the expressions in the `.vel` template. An API returning `{ "results": [...] }` must be assigned with `this.results = data.results`.

## Check deployment

```bash
vercel logs <deployment-url>
vercel env ls
```

Common production failures are Python metadata allowing 3.10 while a dependency requires 3.11+, missing `Jinja2` for template rendering, setuptools discovering `public/` as a Python package, an absent Neon schema, or a service worker serving an old bundle.

After a browser-runtime fix, increment the service-worker cache name, redeploy, and hard-refresh. Never put database URLs or cron secrets in `.vel`, JavaScript, screenshots, or Git.

For Vercel or another serverless host, verify the deployed artifacts directly:

```bash
curl -I https://your-app.example/static/js/App.js
curl -I https://your-app.example/static/css/App.css
curl https://your-app.example/api/health
```

An HTML `200` response for a JavaScript URL is still a failure. The response must be JavaScript with the correct path and content type. Also confirm that the deployment actually ran the Teloce build; a local `dist/` folder does not prove the host generated it.

## Expert: inspect generated code safely

Use generated code to answer specific questions:

```bash
rg -n "export default|mount\(|data-teloce-event|data-v-" dist/static/js
node --check dist/static/js/App.js
```

Do not “fix” generated code directly. Reproduce the problem in the `.vel` source, fix the compiler input, rebuild, and compare the generated output. Source maps should point browser stack traces back to the component source.

## Checklist

- [ ] `teloce doctor --verbose` passes.
- [ ] `teloce lint --strict` passes.
- [ ] Every `.vel` import resolves.
- [ ] `teloce build` reports zero failed files.
- [ ] Generated assets return `200`.
- [ ] API endpoints work without the UI.
- [ ] Browser typing, clicks, loops, and empty states are tested.
- [ ] IndexedDB and service-worker caches are checked.
- [ ] Deployment logs and environment variables are checked.
- [ ] The fix is retested in a fresh browser context.


## Runtime diagnostics and host integration

The shared runtime exposes an error hook and `teloce:error` browser events.
Flaxon can combine these with compile/SSR errors in its development dashboard.
See [SSR and hydration](ssr-and-hydration.md) for the diagnostic contract,
source mapping limitations and production boundaries.

# Optional first-party plugins

These modules ship inside `teloce-py`, but builds include only modules you enable.
They work without Flaxon. They do not replace server validation, authorization,
SEO content rendered on the server, or an application-specific offline sync design.

## Configure a Flaxon application

```python
from flaxon import Flaxon

app = Flaxon("project-manager", debug=True)
app.use_teloce(
    ui_dir="ui",
    plugins={
        "forms": True,
        "i18n": {
            "locale": "en",
            "fallback": "en",
            "messages": {
                "en": {"welcome": "Welcome, {name}", "tasks": {"one": "{count} task", "other": "{count} tasks"}},
                "es": {"welcome": "Hola, {name}", "tasks": {"one": "{count} tarea", "other": "{count} tareas"}},
            },
        },
        "accessibility": True,
        "head": {
            "title": "Project manager",
            "description": "Manage projects and tasks",
            "pages": {"/projects": {"title": "Your projects", "description": "Your project dashboard"}},
        },
        "pwa": {
            "name": "Project manager",
            "short_name": "Projects",
            "start_url": "/",
            "scope": "/",
            "theme_color": "#0f172a",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        },
    },
)
```

Provide real icon files at those URLs and mount their static directory. HTTPS (or
localhost) is required for service workers. PWA registration is disabled in development.
Browser installation eligibility depends on the manifest, icons and browser rules;
setting `pwa=True` alone does not guarantee an installation prompt.

Flaxon serves `/teloce-sw.js`, sets its allowed scope, adds the manifest link, initializes
plugins before mounting components, and connects Head/accessibility to its Teloce router.
Per-page `request.compile(..., meta={...})` overrides Head defaults in the initial HTML.
Omit a plugin, use `False`, or use `{"enabled": False}` to disable it. No extra pip package
is needed. This requires the matching new Teloce and Flaxon versions containing this integration.

## Forms

Browser modules are available as `globalThis.telocePlugins` after initialization.
The API is explicit: `v-model` updates component state; copy that value into the form
before submitting. Forms do not intercept requests or attach authentication headers.

```js
const { createForm, required, email, minLength } = globalThis.telocePlugins.forms;
const form = createForm(
  { email: "", password: "" },
  { email: [required, email], password: [required, minLength(8)] },
);
form.set("email", "person@example.com");
form.set("password", "example-password");
form.touch("email");

const unsubscribe = form.subscribe(() => {
  // Copy status into a component field or signal so its UI reacts.
  console.log(form.status.errors, form.status.submitting);
});

await form.submit(async values => {
  const response = await fetch("/api/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!response.ok) {
    form.setServerErrors(await response.json());
    return;
  }
  return response.json();
});
unsubscribe(); // Do this when the owning component unmounts.
```

`validate()` returns a boolean. Validation is synchronous; rules return an error string
or null. Duplicate submissions are ignored. Submission flags reset even when the handler
throws; catch failures in your UI. Values are plain structured-cloneable data.
`setServerErrors` accepts a field dictionary or an `errors`/`detail` array with `loc` or
`field` paths. Unknown paths become `_form` errors. `reset()` clears values, touched fields
and errors; resetting while submitting raises an error.

## Internationalization

```js
const i18n = globalThis.telocePlugins.i18n;
i18n.t("welcome", { name: "Aldane" });
i18n.t("tasks", { count: 2 });
i18n.number(1200, { style: "currency", currency: "JMD" });
i18n.date(new Date(), { dateStyle: "long" });
i18n.setLocale("es");
const unsubscribe = i18n.subscribe(() => {
  document.documentElement.lang = i18n.locale;
  // Update translated component fields/signals here.
});
```

Messages are text, not HTML. Named placeholders and `Intl.PluralRules` categories are
supported; this is not a full ICU MessageFormat parser. Missing translations use the
fallback locale, then the key. Subscriptions must be removed on component cleanup.

## Accessibility

```js
const a11y = globalThis.telocePlugins.accessibility;
a11y.announce("Task saved");
a11y.focus(document.querySelector("h1"));
const close = a11y.openDialog(document.querySelector("dialog"));
// Later:
close();
```

Use a labelled native `<dialog>` containing your normal buttons/forms. `showModal()`
provides browser keyboard containment and Escape handling; close restores focus to the
opener when it is still present. Router completion announces the current document title.
This does not supply missing labels, color contrast, or a complete accessible design.

## Head / SEO

```js
const head = globalThis.telocePlugins.head;
head.set({
  title: "Project: Website",
  description: "Tasks for your website project",
  canonical: "https://example.com/projects/website",
  ogTitle: "Website project",
  ogDescription: "A project dashboard",
  ogImage: "https://example.com/static/share.png",
});
```

`set` replaces the plugin-owned metadata using defaults plus the current page.
`og:title`, `og:description`, and `og:image` names are also accepted. URLs must be HTTP(S).
Tags are created with DOM APIs; strings are not injected as HTML. Router paths can map to
metadata through `head.pages`; dynamic projects call `set` after their data loads.
For discoverable content use SSR and Flaxon's per-page metadata; client-side tags alone
cannot guarantee crawler indexing.

## PWA updates and caching

```js
document.addEventListener("teloce:pwa-update", () => {
  // Show your own 'Update available' button.
});
const pwa = await globalThis.telocePlugins.pwa;
if (pwa?.updateAvailable) pwa.activateUpdate();
await pwa?.checkForUpdate();
```

Registration happens asynchronously and does not block application mounting. Unsupported
browsers return null; registration failures emit `teloce:pwa-error`. The update controller
has `registration`, `updateAvailable`, `checkForUpdate`, `activateUpdate` and `destroy`.
Activation is explicit, without an automatic refresh that could erase unfinished forms.
Reload after choosing to activate a waiting update. No install-prompt UI is supplied.

The worker precaches emitted JS/CSS and a generic offline page. It ignores non-GET requests,
cross-origin requests, query-bearing asset requests and all non-allowlisted API/data URLs.
Navigation stays network-first and is not cached; network failure shows the static offline
page. Sessions, Admin responses and private user data are never added by this worker.
Offline database edits, queues and conflict resolution are not provided. Cache cleanup is
namespaced by asset base and scope, and deletes only this application's old caches.

## Using another Python framework

```python
from teloce.build import build_project

result = build_project(".", "dist", options={
    "plugins": {"forms": True, "i18n": {"locale": "en"}},
    "public_path": "/static/",
})
```

Read `result["plugins"]["entry"]` (also in `manifest.json`), serve the output folder and
initialize plugins before mounting your component:

```js
import { installPlugins, connectPlugins } from "/static/teloce-plugins/index.js";
const plugins = await installPlugins();
// Mount your component/router here, then:
const disconnect = connectPlugins(plugins, router);
```

For PWA, also add a manifest link and serve the emitted worker at your configured
`workerURL` with an appropriate `Service-Worker-Allowed` header. Flaxon supplies those
steps automatically; other frameworks must do them explicitly. Runtime module factories
can also be imported directly from their emitted files for per-component instances.
Call instance cleanup methods and router disconnect functions when their owners unmount.

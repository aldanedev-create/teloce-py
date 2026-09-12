# Teloce-Py and Flaxon lessons

This learning path teaches the complete workflow: write a `.vel` Single File Component, compile it with Teloce-Py, connect it to a Python application, and grow it into a real Flaxon application or desktop-style web app.

## Learning path

1. [Your first `.vel` component](01-first-vel.md)
2. [Templates, directives, events, and state](02-vel-building-blocks.md)
3. [Components, CSS, JavaScript, and reusable design](03-components-and-design.md)
4. [Build a Flaxon application with Python](04-flaxon-apps.md)
5. [Create a real OS-style simulation](05-os-simulation.md)
6. [Production delivery and developer workflow](06-production.md)
7. [Django: admin dashboards and imported components](07-django.md)
8. [FastAPI: an async CMS with imported components](08-fastapi.md)
9. [Flask: a server-rendered app with imported components](09-flask.md)
10. [What the Flaxon OS production build proves](10-production-case-study.md)
11. [PWA and MSIX packaging](11-pwa-and-msix.md)
12. [Build a small search engine with `.vel`](12-search-engine-showcase.md)
13. [CSS animation and Three.js in `.vel`](13-animation-and-threejs.md)
14. [Build a demo UI framework with `.vel`](14-demo-framework.md)
15. [Create a reusable Teloce plugin](15-plugin-authoring.md)
16. [How Teloce-Py works under the hood](16-how-teloce-works.md)
17. [The Teloce CLI from first build to production](17-cli-workflow.md)
18. [Build the Teloce Motion Lab showcase](18-teloce-showcase.md)
19. [Signals, reactivity, and the browser runtime](19-signals-and-reactivity.md)
20. [Build a Flaxon notebook with the standalone runtime](20-flaxon-runtime-notebook.md)
21. [Runtime file reference and router guide](21-runtime-files-and-router.md)
22. [Build a working Vel IDE with `.vel` and Flask](22-build-a-vel-ide.md)
23. [Production architecture, SSR, security, and release verification](23-production-architecture.md)
24. [Lazy loading with a real developer toolbox](24-lazy-loading-developer-toolbox.md)
25. [TypeScript in `.vel` components](25-typescript-in-vel.md)
26. [Build a real CRUD API application](26-crud-api.md)
27. [Production debugging workflow](27-production-debugging.md)
28. [Optimized Teloce project structure](file-structure.md)
29. [Fast Dev-Facts](fast-dev-facts.md)
30. [Configure a production Teloce build](28-teloce-config.md)
31. [Shared runtime and small component bundles](shared%20runtime.md)
32. [TypeScript in `.vel`: a complete practical guide](29-ts-tutoiral.md)
33. [TypeScript extras for real Teloce projects](30-Extra-ts.md)
34. [Advanced TypeScript architecture with Teloce](31-advanced-ts.md)
35. [Transitions and animation directives](32-transitions-and-animations.md)
36. [Signals inside `.vel` components](36-signals-in-vel.md)

## What you can build

`.vel` files are useful for dashboards, forms, admin tools, study systems, media interfaces, browser IDEs, PWAs, monitoring consoles, and desktop-style web applications. Python remains responsible for the server, APIs, data, authentication, background jobs, and framework integration; the `.vel` layer owns interactive browser UI.

Teloce-Py is designed to make the fast path small:

```text
write .vel -> run the compiler -> serve the generated JavaScript -> use Python normally
```

You do not need to replace Flask, FastAPI, Django, or another Python framework. Teloce-Py generates browser assets that any framework can serve.

When an application behaves unexpectedly, use the [debugging guide](../debugging.md) and [troubleshooting guide](../troubleshooting.md). They include the real problems found while building the Flaxon OS and PySeek applications.

## Original and compatible APIs

The original Teloce API remains useful:

```html
<button @click="count++">Clicked {{ count }} times</button>
<if condition="visible">Shown when visible</if>
<for item="task" in="tasks">{{ task.title }}</for>
```

Compatible aliases are also available in modern components:

```html
<button @click="count++">Clicked {{ count }} times</button>
<p v-if="visible">Shown when visible</p>
<article v-for="task in tasks" :key="task.id">{{ task.title }}</article>
```

Keep the syntax style that fits your existing Teloce project. The original API is not removed when aliases are used.

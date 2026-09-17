# Lesson 47: static components, SSR, and embed builds

Static rendering is useful for content that does not need browser state. It
uses an injected Jinax/Jinja-compatible engine and never executes `.vel`
browser scripts.

```python
import asyncio
from teloce import render_static_component

source = """<template><Card title=\"Report\" /></template>
<script>throw new Error('never runs on the server');</script>"""
card = "<template><article><h2>{{ title }}</h2></article></template>"
html = asyncio.run(render_static_component(source, components={"Card": card}, engine=jinax_engine))
```

The component map is an explicit allow-list. Child props become Jinax/Jinja
context variables, and a recursive import is rejected. Use normal build mode
for interactive components.

For an embeddable chart, configure `teloce.config.json`:

```json
{
  "build": {
    "embed": { "enabled": true, "remove_chrome": true, "aspect_ratio": "16/9" }
  }
}
```

The generated entrypoint removes marked chrome, applies a safe aspect ratio,
and emits a guarded resize message for the parent iframe. Validate the
parent origin in your host page if messages are used for layout.

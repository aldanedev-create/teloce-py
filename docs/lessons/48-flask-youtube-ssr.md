# Lesson 48: Flask YouTube library with Teloce SSR

This lesson builds a small Flask application that stores YouTube links and
renders the video library on the server with Teloce. The browser receives HTML
first, then hydrates the same page with the generated JavaScript bundle.

The application validates every submitted URL and emits only
`youtube-nocookie.com/embed/<video-id>` iframe URLs. It uses no Node.js and no
framework adapter beyond Flask's normal HTTP routes.

## 1. Create the project

```text
flask-youtube-ssr/
  app.py
  requirements.txt
  ui/
    App.html
```

`requirements.txt`:

```text
Flask>=3.0,<4
teloce-py
```

Install on Windows PowerShell, Command Prompt, macOS, or Linux:

```bash
python -m pip install -r requirements.txt
```

On Windows, `py -m pip install -r requirements.txt` is equivalent when the
Python launcher is installed.

## 2. Add the component

Create `ui/App.html`:

```html
<template>
  <main class="library">
    <p class="eyebrow">Teloce SSR + Flask</p>
    <h1>YouTube library</h1>
    <p>These cards arrive as server-rendered HTML.</p>
    <form method="post" action="/add">
      <label>YouTube link <input name="url" type="url" required></label>
      <label>Title <input name="title" type="text" required></label>
      <button type="submit">Add video</button>
    </form>
    <p>{{ videos.length }} saved video(s)</p>
    <section v-for="video in videos" :key="video.id">
      <iframe
        :src="video.embed_url"
        :title="video.title"
        loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowfullscreen></iframe>
      <h2>{{ video.title }}</h2>
    </section>
  </main>
</template>

<script>
export default { data() { return { videos: [] }; } };
</script>

<style scoped>
.library { max-width: 62rem; margin: 3rem auto; padding: 0 1.25rem; font-family: system-ui, sans-serif; }
.eyebrow { color: #e85d3f; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
form { display: grid; gap: .75rem; grid-template-columns: 1fr 1fr auto; margin: 2rem 0; }
label { display: grid; gap: .35rem; font-weight: 700; }
input { border: 1px solid #9db5bd; border-radius: .35rem; font: inherit; padding: .7rem; }
button { background: #176b87; border: 0; border-radius: .35rem; color: white; cursor: pointer; font: inherit; padding: .7rem 1rem; }
section { border: 1px solid #d5e0e3; border-radius: .5rem; margin-top: 1.25rem; overflow: hidden; }
iframe { aspect-ratio: 16 / 9; border: 0; display: block; width: 100%; }
h2 { font-size: 1rem; padding: 0 1rem; }
@media (max-width: 700px) { form { grid-template-columns: 1fr; } }
</style>
```

## 3. Add the Flask host

Create `app.py`:

```python
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flask import Flask, redirect, request, url_for
from teloce.build import build_project
from teloce.server import Renderer, SSRRequest

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEOS = [{
    "id": "dQw4w9WgXcQ",
    "title": "Example video",
    "embed_url": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
}]


def youtube_video_id(raw_url: str) -> str:
    parsed = urlsplit(str(raw_url).strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("Use a YouTube watch, short, youtu.be, or embed URL")
    if parsed.hostname == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        parts = parsed.path.strip("/").split("/")
        candidate = parts[1] if len(parts) == 2 and parts[0] in {"embed", "shorts", "live"} else ""
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError("The URL does not contain a valid YouTube video ID")
    return candidate


def normalize_video(raw_url: str, title: str) -> dict[str, str]:
    video_id = youtube_video_id(raw_url)
    title = " ".join(str(title).split())
    if not title or len(title) > 160:
        raise ValueError("Title must contain 1 to 160 characters")
    return {
        "id": video_id,
        "title": title,
        "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}",
    }


def build_renderer() -> Renderer:
    build_project(ROOT, DIST, options={
        "mode": "production",
        "production": True,
        "html_mode": True,
        "source_roots": ["ui"],
        "ssr": True,
        "ssr_entries": ["ui/App.html"],
        "bundle": True,
        "bundler": "minifyjs",
        "minify": True,
        "tree_shake": True,
        "code_splitting": True,
        "hash_assets": True,
        "clean": True,
    })
    return Renderer(DIST, cache_size=16, cache_ttl=10)


def create_app(renderer: Renderer | None = None) -> Flask:
    renderer = renderer or build_renderer()
    app = Flask(__name__, static_folder=str(DIST), static_url_path="/assets")

    @app.get("/")
    def index():
        result = renderer.render(
            "ui/App.html", {"videos": list(VIDEOS)},
            request=SSRRequest(path=request.path),
        )
        client = renderer.entries["ui/App.html"]["client"].replace("\\", "/")
        styles = sorted(
            str(item["output"])
            for item in renderer.manifest["files"]
            if str(item.get("output", "")).endswith(".css")
        )
        css = "".join(
            f'<link rel="stylesheet" href="{url_for("static", filename=path)}">'
            for path in styles
        )
        document = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>YouTube library</title>' + css + '</head><body>'
            '<div id="app" data-teloce-ssr="1">' + result.html + '</div>'
            '<script type="module">import { hydrate } from '
            + json.dumps(url_for("static", filename=client))
            + '; hydrate("#app",' + result.props_json + ");</script>"
            '</body></html>'
        )
        return document

    @app.post("/add")
    def add():
        try:
            video = normalize_video(request.form.get("url", ""), request.form.get("title", ""))
        except ValueError as error:
            return f"<h1>Invalid video</h1><p>{html.escape(str(error))}</p>", 400
        VIDEOS.append(video)
        renderer.clear_cache()
        return redirect(url_for("index"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5003, debug=False)
```

## 4. Run it

```bash
python app.py
```

Windows:

```powershell
py app.py
```

Open <http://127.0.0.1:5003>. The initial page already contains the iframe
HTML before hydration. Submit another YouTube watch, Shorts, `youtu.be`, live,
or embed URL and Flask redirects back to the SSR page.

## 5. What the production build does

The build sends the generated graph through MinifyJS's esbuild engine:

```text
App.html and Teloce runtime
        -> dependency graph
        -> tree shaking
        -> ESM bundle and code splitting
        -> compression and mangling
        -> hashed JavaScript and CSS
        -> SSR manifest points at the final client bundle
```

Intermediate JavaScript files may remain in `dist/` for compatibility, but the
manifest's `ssr.entries["ui/App.html"]["client"]` is the browser entry. Deploy
that bundle, every emitted chunk, and every stylesheet.

For production, replace the in-memory `VIDEOS` list with a database, add CSRF
protection to `POST /add`, add authentication and rate limits, and serve Flask
behind a production WSGI server.

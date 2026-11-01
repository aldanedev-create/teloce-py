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
VIDEOS = [
    {
        "id": "dQw4w9WgXcQ",
        "title": "Example video",
        "embed_url": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    }
]


def youtube_video_id(raw_url: str) -> str:
    parsed = urlsplit(str(raw_url).strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("Use a YouTube watch, short, youtu.be, or embed URL")
    host = parsed.hostname
    if host == "youtu.be":
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
    clean_title = " ".join(str(title).split())
    if not clean_title or len(clean_title) > 160:
        raise ValueError("Title must contain 1 to 160 characters")
    return {
        "id": video_id,
        "title": clean_title,
        "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}",
    }


def build_renderer() -> Renderer:
    build_project(
        ROOT,
        DIST,
        options={
            "mode": "production",
            "production": True,
            "html_mode": True,
            "source_roots": ["ui"],
            "ssr": True,
            "ssr_entries": ["ui/App.html"],
            "bundle": True,
            "bundler": "minifyjs",
            "minify": True,
            "hash_assets": True,
            "code_splitting": True,
            "tree_shake": True,
            "packages": "bundle",
            "external": [],
            "define": {"DEBUG": "false"},
            "drop": ["debugger"],
            "report": "minifyjs-report.json",
            "clean": True,
        },
    )
    return Renderer(DIST, cache_size=16, cache_ttl=10)


def create_app(renderer: Renderer | None = None) -> Flask:
    renderer = renderer or build_renderer()
    app = Flask(__name__, static_folder=str(DIST), static_url_path="/assets")

    @app.get("/")
    def index():
        result = renderer.render(
            "ui/App.html",
            {"videos": list(VIDEOS)},
            request=SSRRequest(path=request.path, query=request.args.to_dict()),
        )
        client = renderer.entries["ui/App.html"]["client"].replace("\\", "/")
        styles = sorted(
            str(item.get("output", ""))
            for item in renderer.manifest.get("files", [])
            if str(item.get("output", "")).endswith(".css")
        )
        css = "".join(
            f'<link rel="stylesheet" href="{url_for("static", filename=path)}">'
            for path in styles
        )
        script_url = json.dumps(url_for("static", filename=client))
        document = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>YouTube library</title>"
            + css
            + '</head><body><div id="app" data-teloce-ssr="1">'
            + result.html
            + '</div><script type="module">import { hydrate } from '
            + script_url
            + '; hydrate("#app",'
            + result.props_json
            + ");</script></body></html>"
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
    print("Serving http://127.0.0.1:5003/")
    app.run(host="127.0.0.1", port=5003, debug=False)

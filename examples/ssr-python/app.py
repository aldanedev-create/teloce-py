from __future__ import annotations

import argparse
import html
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from teloce.build import build_project
from teloce.server import Renderer, SSRRequest

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def build() -> Renderer:
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
            "bundle": False,
            "minify": True,
            "hash_assets": True,
            "clean": True,
            "source_maps": False,
        },
    )
    return Renderer(DIST, cache_size=32, cache_ttl=30)


def page(renderer: Renderer, request_path: str) -> bytes:
    result = renderer.render(
        "ui/App.html",
        {
            "title": "Server-rendered Python UI",
            "description": "HTML is rendered before the browser loads JavaScript.",
            "name": "",
            "items": [
                {"id": "python", "label": "No Node.js required"},
                {"id": "portable", "label": "Works with any Python web host"},
            ],
        },
        request=SSRRequest(path=request_path),
    )
    client = renderer.entries["ui/App.html"]["client"].replace("\\", "/")
    styles = []
    for item in renderer.manifest.get("files", []):
        output = str(item.get("output", ""))
        if output.endswith(".css"):
            styles.append(
                '<link rel="stylesheet" href="/'
                + html.escape(output.replace("\\", "/"), quote=True)
                + '">'
            )
    script_url = json.dumps("/" + client.lstrip("/"))
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        + "".join(result.head)
        + "".join(styles)
        + "</head><body><div id=\"app\" data-teloce-ssr=\"1\">"
        + result.html
        + "</div><script type=\"module\">import { hydrate } from "
        + script_url
        + "; hydrate(\"#app\","
        + result.props_json
        + ");</script></body></html>"
    )
    return document.encode("utf-8")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, renderer: Renderer, **kwargs):
        self.renderer = renderer
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_GET(self):  # noqa: N802 - standard library handler API
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            data = page(self.renderer, path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, format, *args):
        print(format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Teloce Python SSR example")
    parser.add_argument("--build-only", action="store_true", help="Build and exit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    renderer = build()
    print(f"Built SSR entry: {renderer.entries['ui/App.html']['artifact']}")
    if args.build_only:
        return
    server = ThreadingHTTPServer(
        (args.host, args.port),
        lambda *handler_args: Handler(*handler_args, renderer=renderer),
    )
    print(f"Serving http://{args.host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

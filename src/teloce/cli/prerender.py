"""Export a manifest entry as hydrated static HTML with explicit public data."""

from __future__ import annotations

import html
import json
from pathlib import Path

from teloce.server import Renderer


def prerender_command(args):
    """Render an already-built entry; return a useful nonzero status on failure."""
    try:
        root = Path(args.build_dir).resolve()
        output = (root / args.output).resolve()
        output.relative_to(root)
        renderer = Renderer(root)
        data = (
            json.loads(Path(args.data).read_text(encoding="utf-8")) if args.data else {}
        )
        result = renderer.render(args.entry, data)
        client = renderer.entries[args.entry]["client"]
        client_url = "/" + client
        script_url = json.dumps(client_url).replace("<", "\\u003c")
        styles = sorted(
            {
                item.get("output", "")
                for item in renderer.manifest.get("files", [])
                if str(item.get("output", "")).endswith(".css")
            }
        )
        css = "".join(
            f'<link rel="stylesheet" href="/{html.escape(path, quote=True)}">'
            for path in styles
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + css
            + '</head><body><div id="app" data-teloce-ssr="1">'
            + result.html
            + '</div><script type="module">import { hydrate } from '
            + script_url
            + ';hydrate("#app",'
            + result.props_json
            + ");</script></body></html>",
            encoding="utf-8",
        )
        print(f"Prerendered {args.entry} to {output}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"Prerender failed: {error}")
        return 1

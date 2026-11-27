"""Optional in-memory builds: no ``dist/`` folder is left behind.

The normal build runs into a temporary folder, the files are loaded into a dict, and the folder is deleted.
Disk stays the default (``teloce build`` is how you make a deployable artifact); use this for development,
tests, read-only or embedded setups, and single-process servers.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional

from teloce.build import build_project

__all__ = ["MemoryBuild", "build_in_memory"]

_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".json": "application/json", ".map": "application/json",
          ".html": "text/html; charset=utf-8"}


def _content_type(path: str) -> str:
    return _TYPES.get(Path(path).suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"


class MemoryBuild:
    """The files of a build, keyed by their path inside the output folder (``static/js/App.js``)."""

    def __init__(self, files: Dict[str, bytes], result: Optional[dict] = None):
        self.files = files
        self.result = result or {}
        self._etags = {name: '"' + hashlib.sha1(data).hexdigest()[:20] + '"' for name, data in files.items()}

    @property
    def manifest(self) -> dict:
        return json.loads(self.files["manifest.json"]) if "manifest.json" in self.files else {}

    def read(self, path: str) -> Optional[bytes]:
        return self.files.get(path)

    def _lookup(self, url_path: str, root: str) -> Optional[str]:
        key = (root.strip("/") + "/" if root else "") + url_path.lstrip("/")
        return key if key in self.files else None  # a dict lookup cannot be tricked by ".." segments

    def wsgi_app(self, root: str = "static", max_age: int = 0) -> Callable:
        """WSGI app serving ``<root>/...`` files. Mount it at the URL prefix you want (for example ``/static``)."""

        def app(environ, start_response):
            if environ["REQUEST_METHOD"] not in ("GET", "HEAD"):
                start_response("405 Method Not Allowed", [("Allow", "GET, HEAD")])
                return [b""]
            key = self._lookup(environ.get("PATH_INFO", ""), root)
            if key is None:
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"Not found"]
            etag = self._etags[key]
            headers = [("ETag", etag), ("Cache-Control", f"public, max-age={max_age}" if max_age else "no-cache"),
                       ("X-Content-Type-Options", "nosniff")]
            if environ.get("HTTP_IF_NONE_MATCH") == etag:
                start_response("304 Not Modified", headers)
                return [b""]
            data = self.files[key]
            start_response("200 OK", headers + [("Content-Type", _content_type(key)), ("Content-Length", str(len(data)))])
            return [b"" if environ["REQUEST_METHOD"] == "HEAD" else data]

        return app

    def asgi_app(self, root: str = "static", max_age: int = 0) -> Callable:
        """ASGI app with the same behavior. Mount it with ``app.mount("/static", build.asgi_app())``."""

        async def app(scope, receive, send):
            if scope["type"] != "http":
                return
            key = self._lookup(scope.get("path", ""), root)
            if scope["method"] not in ("GET", "HEAD") or key is None:
                status = 405 if scope["method"] not in ("GET", "HEAD") else 404
                await send({"type": "http.response.start", "status": status, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
            etag = self._etags[key]
            headers = [(b"etag", etag.encode()), (b"x-content-type-options", b"nosniff"),
                       (b"cache-control", (f"public, max-age={max_age}" if max_age else "no-cache").encode())]
            if dict(scope.get("headers") or []).get(b"if-none-match") == etag.encode():
                await send({"type": "http.response.start", "status": 304, "headers": headers})
                await send({"type": "http.response.body", "body": b""})
                return
            data = self.files[key]
            headers += [(b"content-type", _content_type(key).encode()), (b"content-length", str(len(data)).encode())]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else data})

        return app


def build_in_memory(root_dir, options: Optional[dict] = None) -> MemoryBuild:
    """Build a project and keep the output in memory. Raises ``RuntimeError`` if any component fails."""
    with tempfile.TemporaryDirectory(prefix="teloce-build-") as tmp:
        result = build_project(root_dir, out_dir=tmp, options={"clean": True, **(options or {})})
        out = Path(tmp)
        files = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    return MemoryBuild(files, result)

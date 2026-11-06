"""Serve the PWA plugin files with the headers a service worker needs, in any framework.

A browser lets a service worker control only the folder it is served from. The PWA plugin
emits ``teloce-plugins/sw.js`` but registers it for the whole site (``scope: "/"``), so the
worker must be sent with ``Service-Worker-Allowed: /``. Plain static file servers don't do
that, which is why a PWA built with Teloce can silently fail to register outside Flaxon.

:class:`PwaFiles` is a tiny, locked-down file server for exactly those files. It is a WSGI
and an ASGI application, so it mounts into Flask, FastAPI, Django or anything else::

    from teloce.plugins.pwa_server import PwaFiles

    pwa = PwaFiles("dist")                      # the folder passed to build_project()
    # Mount at the URL the plugin files are served from (public_path + "teloce-plugins"):
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/static/teloce-plugins": pwa.wsgi_app})

It serves only the files the plugin emits (``.js``, ``.webmanifest``, ``.html``, ``.png``),
never follows paths outside that folder, and answers only GET and HEAD.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

__all__ = ["PwaFiles", "PwaResponse"]

_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
}
_STATUS = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}


@dataclass
class PwaResponse:
    status: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""


class PwaFiles:
    """Serve the files in ``<directory>/teloce-plugins`` with service-worker-safe headers.

    ``directory`` is the build output folder (or the ``teloce-plugins`` folder itself).
    ``scope`` is the ``Service-Worker-Allowed`` value; by default it is read from the built
    manifest, falling back to ``"/"``.
    """

    def __init__(self, directory: str | Path, *, scope: str | None = None):
        base = Path(directory)
        self.root = (base / "teloce-plugins" if (base / "teloce-plugins").is_dir() else base).resolve()
        self.scope = scope or self._manifest_scope()

    def _manifest_scope(self) -> str:
        try:
            scope = json.loads((self.root / "manifest.webmanifest").read_text(encoding="utf-8")).get("scope")
        except (OSError, ValueError):
            return "/"
        return scope if isinstance(scope, str) and scope.startswith("/") else "/"

    def _locate(self, path: str) -> Path | None:
        path = path.split("?", 1)[0].replace("\\", "/")
        if "\x00" in path:
            return None
        parts = [part for part in path.split("/") if part]
        if parts and parts[0] == "teloce-plugins":
            parts = parts[1:]
        if not parts or any(part in (".", "..") or part.startswith(".") for part in parts):
            return None
        candidate = self.root.joinpath(*parts)
        if candidate.suffix not in _TYPES:
            return None
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)  # symlinks and traversal cannot escape the folder
        except (OSError, ValueError):
            return None
        return resolved if resolved.is_file() else None

    def get(self, path: str, method: str = "GET") -> PwaResponse:
        """Framework-neutral lookup: returns the status, headers and body to send."""
        method = method.upper()
        if method not in ("GET", "HEAD"):
            return PwaResponse(405, [("Allow", "GET, HEAD"), ("Content-Type", "text/plain")], b"Method Not Allowed")
        file = self._locate(path)
        if file is None:
            return PwaResponse(404, [("Content-Type", "text/plain")], b"Not Found")
        body = file.read_bytes()
        headers = [
            ("Content-Type", _TYPES[file.suffix]),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-cache"),  # revalidate: a stale worker would never update
            ("X-Content-Type-Options", "nosniff"),
        ]
        if file.name == "sw.js":
            headers.append(("Service-Worker-Allowed", self.scope))
        return PwaResponse(200, headers, b"" if method == "HEAD" else body)

    # ---- WSGI ---------------------------------------------------------------------------
    @property
    def wsgi_app(self) -> Callable[..., list[bytes]]:
        def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
            response = self.get(environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "GET"))
            start_response(f"{response.status} {_STATUS[response.status]}", response.headers)
            return [response.body]

        return app

    # ---- ASGI ---------------------------------------------------------------------------
    @property
    def asgi_app(self) -> Callable[..., Awaitable[None]]:
        async def app(scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
            if scope["type"] == "lifespan":
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            if scope["type"] != "http":
                raise RuntimeError("PwaFiles.asgi_app only serves HTTP requests")
            path = scope.get("path", "")
            root = scope.get("root_path", "")
            if root and path.startswith(root):
                path = path[len(root):]
            response = self.get(path, scope.get("method", "GET"))
            await send({
                "type": "http.response.start", "status": response.status,
                "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in response.headers],
            })
            await send({"type": "http.response.body", "body": response.body})

        return app

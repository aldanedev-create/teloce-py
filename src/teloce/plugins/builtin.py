"""Optional first-party browser modules and conservative PWA build artifacts."""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import struct
import zlib
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

NAMES = {"forms", "i18n", "accessibility", "head", "pwa"}


def normalize_plugins(value: Any) -> dict[str, dict[str, Any]]:
    """Validate opt-in configuration without enabling disabled modules."""
    if value is None or value is False:
        return {}
    if not isinstance(value, dict) or set(value) - NAMES:
        raise ValueError("plugins must map forms, i18n, accessibility, head or pwa to options")
    enabled = {}
    for name, options in value.items():
        if options is False or options is None:
            continue
        if options is True:
            options = {}
        if not isinstance(options, dict):
            raise ValueError(f"plugins.{name} must be a boolean or options dictionary")
        if options.get("enabled") is False:
            continue
        json.dumps(options, allow_nan=False)
        enabled[name] = dict(options)
    return enabled


def _safe_url(value: str) -> str:
    if any(ord(char) < 32 for char in value) or "\\" in value:
        raise ValueError("Plugin URLs cannot contain control characters or backslashes")
    parsed = urlsplit(value)
    if parsed.scheme not in {"", "http", "https"} or value.startswith("//"):
        raise ValueError("Plugin URLs must be relative or HTTP(S)")
    return value


def _parse_color(value: Any, default: tuple[int, int, int] = (15, 23, 42)) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)) if len(text) == 6 else default
    except ValueError:
        return default


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


@lru_cache(maxsize=16)
def placeholder_icon(size: int, color: tuple[int, int, int]) -> bytes:
    """A solid-colour PNG with a simple ring mark inside the maskable safe zone.

    Installable browsers require 192px and 512px icons. These stand-ins make a fresh build
    installable; applications should replace them with real artwork.
    """
    background = bytes((*color, 255)) * size
    light = tuple(255 if sum(color) < 384 else 15 for _ in range(3))
    centre = (size - 1) / 2
    outer, inner, dot = size * 0.30, size * 0.22, size * 0.09
    lo, hi = max(0, int(centre - outer - 2)), min(size, int(centre + outer + 3))
    rows: list[bytes] = []
    for y in range(size):
        if not lo <= y < hi:
            rows.append(background)
            continue
        row = bytearray(background)
        for x in range(lo, hi):
            distance = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
            # Anti-aliased coverage of the ring [inner, outer] plus the centre dot.
            coverage = max(
                min(1.0, max(0.0, min(distance - inner + 0.5, outer - distance + 0.5))),
                min(1.0, max(0.0, dot - distance + 0.5)),
            )
            if coverage > 0:
                row[x * 4:x * 4 + 3] = bytes(round(c * (1 - coverage) + l * coverage) for c, l in zip(color, light))
        rows.append(bytes(row))
    return _png(size, size, rows)


def emit_plugins(output: Path, results: dict[str, Any], options: dict[str, Any],
                 transform: Callable[[str], str] | None = None) -> dict[str, Any] | None:
    """Emit only configured modules, plus explicit static-only offline caching."""
    enabled = normalize_plugins(options.get("plugins"))
    directory = output / "teloce-plugins"
    if directory.is_symlink():
        raise ValueError("Plugin output directory must not be a symbolic link")
    if directory.exists():
        shutil.rmtree(directory)
    if not enabled:
        return None
    directory.mkdir(parents=True)
    artifacts = []

    def write(name: str, content: str) -> None:
        if transform and name.endswith(".js") and name != "sw.js":
            content = transform(content)
        path = directory / name
        path.write_text(content, encoding="utf-8")
        item = {"input": "<plugin>", "output": path.relative_to(output).as_posix(), "size": path.stat().st_size}
        results["files"].append(item)
        results["total_bytes"] += item["size"]
        artifacts.append(item["output"])

    def write_bytes(name: str, content: bytes) -> None:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        item = {"input": "<plugin>", "output": path.relative_to(output).as_posix(), "size": path.stat().st_size}
        results["files"].append(item)
        results["total_bytes"] += item["size"]
        artifacts.append(item["output"])

    warnings: list[str] = []
    imports, setup = [], []
    factories = {"forms": "createForm", "i18n": "createI18n", "accessibility": "createAccessibility", "head": "createHead", "pwa": "registerPwa"}
    for name, config in enabled.items():
        source = files("teloce.runtime").joinpath("plugins", name + ".js").read_text(encoding="utf-8")
        write(name + ".js", source)
        factory = factories[name]
        if name == "forms":
            imports.append("import * as forms from './forms.js';")
            setup.append("api.forms = forms;")
        elif name == "pwa":
            imports.append("import {registerPwa} from './pwa.js';")
            settings = dict(config)
            # Register for the manifest scope unless told otherwise; the browser default (the worker's
            # own folder) would control nothing.
            settings.setdefault("scope", _safe_url(str(config.get("scope", "/"))))
            # Service workers cache aggressively, so development builds skip them unless the
            # application opts in with {"pwa": {"enabled": True}}.
            settings["enabled"] = bool(config.get("enabled", not options.get("dev", False)))
            setup.append(f"api.pwa = registerPwa({json.dumps(settings)}).catch(error => {{ console.error(error); document.dispatchEvent(new CustomEvent('teloce:pwa-error', {{detail:error}})); return null; }});")
        else:
            imports.append(f"import {{{factory}}} from './{name}.js';")
            setup.append(f"api.{name} = {factory}({json.dumps(config)});")
            if name == "head":
                # A server-rendered <title> wins; the configured default applies when the page has none.
                setup[-1] = f"api.head = createHead({{...{json.dumps(config)}, ...initialHead, title:document.title||{json.dumps(str(config.get('title', '')))}}});"
    # PWA failures must not prevent the application itself from mounting.
    routes = enabled.get("head", {}).get("pages", {})
    bootstrap = "\n".join(imports) + "\nexport async function installPlugins(initialHead = {}) {\nconst api = {};\n" + "\n".join(setup) + "\nglobalThis.telocePlugins = api;\nreturn api;\n}\n"
    bootstrap += "export function connectPlugins(api, router) {\n"
    bootstrap += "const pages = " + json.dumps(routes) + ";\n"
    bootstrap += "const update = route => { const path = route?.path || location.pathname; api.head?.set(pages[path] || {}); api.accessibility?.announce(document.title); };\n"
    bootstrap += "if (!router?.afterEach) return () => {};\nreturn router.afterEach(update);\n}\n"
    write("index.js", bootstrap)
    descriptor: dict[str, Any] = {"version": 1, "enabled": list(enabled), "entry": "teloce-plugins/index.js", "assets": artifacts}
    if "pwa" in enabled:
        pwa = enabled["pwa"]
        name = str(pwa.get("name", "Teloce application"))
        scope = _safe_url(str(pwa.get("scope", "/")))
        worker_url = _safe_url(str(pwa.get("workerURL", "./sw.js")))
        icons = list(pwa.get("icons") or [])
        for icon in icons:
            _safe_url(icon["src"])
        if not icons:
            color = _parse_color(pwa.get("theme_color", "#0f172a"))
            for size in (192, 512):
                write_bytes(f"icons/icon-{size}.png", placeholder_icon(size, color))
                # Relative to the manifest, so it works wherever the build is served.
                icons.append({"src": f"icons/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png", "purpose": "any maskable"})
            warnings.append("pwa: no icons configured, so placeholder 192px and 512px icons were generated; "
                            "set plugins.pwa.icons to your own artwork before release")
        manifest = {"name": name, "short_name": str(pwa.get("short_name", name)), "start_url": _safe_url(str(pwa.get("start_url", "/"))), "scope": scope, "display": str(pwa.get("display", "standalone")), "theme_color": pwa.get("theme_color", "#0f172a"), "background_color": pwa.get("background_color", "#ffffff"), "icons": icons}
        if pwa.get("description"):
            manifest["description"] = str(pwa["description"])
        write("manifest.webmanifest", json.dumps(manifest))
        write("offline.html", "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Offline</title><h1>You are offline</h1><p>Reconnect to continue using " + html.escape(name) + ".</p></html>")
        base = _safe_url(str(options.get("public_path", "/"))).rstrip("/") + "/"
        if not base.startswith("/") or base.startswith("//"):
            raise ValueError("PWA public_path must be an absolute same-origin path")
        offline = base + "teloce-plugins/offline.html"
        # Never include server-rendered pages, API URLs, source maps or model data.
        paths = [item["output"] for item in results["files"] if str(item.get("output", "")).endswith((".js", ".css"))]
        assets = sorted({base + path for path in paths} | {offline})
        version = hashlib.sha256("".join(hashlib.sha256((output / item["output"]).read_bytes()).hexdigest() for item in results["files"] if (output / item["output"]).is_file()).encode()).hexdigest()[:16]
        prefix = "teloce-static-" + hashlib.sha256((base + scope).encode()).hexdigest()[:12] + "-"
        worker = "const PREFIX=" + json.dumps(prefix) + ";const CACHE=PREFIX+" + json.dumps(version) + ";const ASSETS=" + json.dumps(assets) + ";const OFFLINE=" + json.dumps(offline) + ";\n"
        worker += "self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(async cache=>{await cache.add(OFFLINE);await Promise.allSettled(ASSETS.filter(url=>url!==OFFLINE).map(url=>cache.add(url)));})));\n"
        worker += "self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE).map(key=>caches.delete(key))))));\n"
        worker += "self.addEventListener('message',event=>{if(event.data?.type==='TELOCE_SKIP_WAITING')self.skipWaiting()});\n"
        worker += "self.addEventListener('fetch',event=>{const request=event.request,url=new URL(request.url);if(request.method!=='GET'||url.origin!==self.location.origin)return;if(request.mode==='navigate'){event.respondWith(fetch(request).catch(async()=>(await caches.match(OFFLINE))||new Response('Offline',{status:503})));return;}if(url.search||!ASSETS.includes(url.pathname))return;event.respondWith(caches.open(CACHE).then(async cache=>(await cache.match(request))||fetch(request)));});\n"
        write("sw.js", worker)
        descriptor["pwa"] = {"manifest": "teloce-plugins/manifest.webmanifest", "worker": "teloce-plugins/sw.js", "worker_url": worker_url, "scope": scope}
        if warnings:
            descriptor["warnings"] = warnings
    return descriptor

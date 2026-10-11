"""Optional first-party browser modules and conservative PWA build artifacts."""
from __future__ import annotations

import hashlib
import html
import json
import shutil
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
            settings["enabled"] = not options.get("dev", False)
            setup.append(f"api.pwa = registerPwa({json.dumps(settings)}).catch(error => {{ document.dispatchEvent(new CustomEvent('teloce:pwa-error', {{detail:error}})); return null; }});")
        else:
            imports.append(f"import {{{factory}}} from './{name}.js';")
            setup.append(f"api.{name} = {factory}({json.dumps(config)});")
            if name == "head":
                setup[-1] = f"api.head = createHead({{...{json.dumps(config)}, ...initialHead, title:document.title}});"
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
        manifest = {"name": name, "short_name": str(pwa.get("short_name", name)), "start_url": _safe_url(str(pwa.get("start_url", "/"))), "scope": scope, "display": "standalone", "theme_color": pwa.get("theme_color", "#0f172a"), "background_color": pwa.get("background_color", "#ffffff"), "icons": pwa.get("icons", [])}
        for icon in manifest["icons"]:
            _safe_url(icon["src"])
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
        worker += "self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));\n"
        worker += "self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE).map(key=>caches.delete(key))))));\n"
        worker += "self.addEventListener('message',event=>{if(event.data?.type==='TELOCE_SKIP_WAITING')self.skipWaiting()});\n"
        worker += "self.addEventListener('fetch',event=>{const request=event.request,url=new URL(request.url);if(request.method!=='GET'||url.origin!==self.location.origin)return;if(request.mode==='navigate'){event.respondWith(fetch(request).catch(async()=>(await caches.match(OFFLINE))||new Response('Offline',{status:503})));return;}if(url.search||!ASSETS.includes(url.pathname))return;event.respondWith(caches.open(CACHE).then(async cache=>(await cache.match(request))||fetch(request)));});\n"
        write("sw.js", worker)
        descriptor["pwa"] = {"manifest": "teloce-plugins/manifest.webmanifest", "worker": "teloce-plugins/sw.js", "worker_url": worker_url, "scope": scope}
    return descriptor

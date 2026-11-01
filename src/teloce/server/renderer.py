"""Render precompiled SSR artifacts without importing application objects or JavaScript."""

from __future__ import annotations

import html
import asyncio
import inspect
import json
import math
import time
from dataclasses import dataclass
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from teloce.ast.elements import VOID_ELEMENTS
from teloce.server.expressions import UNDEFINED, evaluate, string, truthy


@dataclass(frozen=True)
class RenderResult:
    html: str
    props_json: str
    assets: tuple[str, ...] = ()
    diagnostics: tuple[dict, ...] = ()
    head: tuple[str, ...] = ()
    csp_nonce: str | None = None


@dataclass(frozen=True)
class SSRRequest:
    """Framework-neutral request metadata available only during server render."""

    method: str = "GET"
    scheme: str = "http"
    host: str = "localhost"
    path: str = "/"
    query: Mapping[str, object] = None
    headers: Mapping[str, object] = None
    cookies: Mapping[str, object] = None
    csp_nonce: str | None = None

    def scope(self):
        return public_data({
            "method": self.method,
            "scheme": self.scheme,
            "host": self.host,
            "path": self.path,
            "query": dict(self.query or {}),
            "headers": dict(self.headers or {}),
            "cookies": dict(self.cookies or {}),
        })


def _request_scope(request):
    if request is None:
        return None
    if isinstance(request, SSRRequest):
        return request.scope()
    if type(request) is dict:
        return public_data(request)
    raise ValueError("SSR request context must be an SSRRequest or plain JSON object")


class SSRRenderError(ValueError):
    def __init__(self, message, *, component, location=None):
        self.diagnostic = {
            "category": "ssr",
            "message": message,
            "component": component,
            **(location or {}),
        }
        super().__init__(f"{component}: {message}")


def public_data(value, *, depth=0, budget=None):
    budget = budget if budget is not None else [100000]
    budget[0] -= 1
    if depth > 64 or budget[0] < 0:
        raise ValueError("Public data exceeds its depth or item limit")
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 9007199254740991:
            raise ValueError("Use strings for nonfinite or unsafe JSON numbers")
        return value
    if type(value) is list:
        return [public_data(item, depth=depth + 1, budget=budget) for item in value]
    if type(value) is dict:
        if any(
            not isinstance(key, str) or key in {"__proto__", "constructor", "prototype"}
            for key in value
        ):
            raise ValueError("Public data requires safe string keys")
        return {
            key: public_data(item, depth=depth + 1, budget=budget)
            for key, item in value.items()
        }
    raise ValueError(
        "SSR accepts only plain JSON public data; convert application objects explicitly"
    )


def props_json(value):
    output = json.dumps(public_data(value), ensure_ascii=False, allow_nan=False)
    return (
        output.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def attribute(name, value):
    if value is None or value is UNDEFINED or value is False:
        return ""
    if name.lower().startswith("on") or name.lower() in {"srcdoc", "innerhtml"}:
        raise ValueError("Unsafe SSR attribute")
    if name in {"href", "src", "action", "formaction", "xlink:href", "poster"}:
        normalized = "".join(c for c in string(value) if ord(c) > 32)
        if "\\" in normalized or urlsplit(normalized).scheme.lower() not in {
            "",
            "http",
            "https",
            "mailto",
            "tel",
        }:
            raise ValueError("Unsafe SSR URL")
    if name == "class" and isinstance(value, dict):
        value = " ".join(key for key, enabled in value.items() if truthy(enabled))
    if name == "class" and isinstance(value, list):
        value = " ".join(string(item) for item in value if truthy(item))
    if isinstance(value, dict) and name == "style":
        raise ValueError("SSR style objects are not yet supported")
    boolean = {
        "disabled",
        "checked",
        "selected",
        "multiple",
        "readonly",
        "required",
        "autofocus",
        "hidden",
    }
    if name in boolean:
        return f" {name}" if truthy(value) else ""
    return f' {name}="{html.escape(string(value), quote=True)}"'


class Renderer:
    """Load manifest-linked render programs once and render explicit public snapshots."""

    def __init__(
        self,
        build_dir,
        *,
        max_output=2_000_000,
        max_iterations=10000,
        cache_size=0,
        cache_ttl=0,
    ):
        self.root = Path(build_dir).resolve()
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        ssr = self.manifest.get("ssr") or {}
        if ssr.get("version") != 1:
            raise ValueError("Unsupported or missing SSR manifest version")
        self.entries = ssr["entries"]
        self.programs = {}
        self.cache_size = max(0, min(int(cache_size), 256))
        self.cache_ttl = max(0.0, float(cache_ttl))
        self._cache = OrderedDict()
        self._cache_times = {}
        self._cache_bytes = 0
        self.max_output = max_output
        self.max_iterations = max_iterations
        loaded = {}
        for entry, item in self.entries.items():
            path = (self.root / item["artifact"]).resolve()
            path.relative_to(self.root)
            if path not in loaded:
                loaded[path] = json.loads(path.read_text())
            program = loaded[path]
            if program.get("version") != 1:
                raise ValueError("Unsupported SSR artifact version")
            self.programs[entry] = program

    def render(self, entry, context=None, *, request=None):
        if context is not None and type(context) is not dict:
            raise ValueError("SSR public props must be a plain JSON object")
        data = public_data({} if context is None else context)
        request_data = _request_scope(request)
        payload = props_json(data)
        if len(payload.encode()) > self.max_output:
            raise ValueError("Public state exceeds output limit")
        request_payload = props_json(request_data) if request_data is not None else ""
        if isinstance(request, SSRRequest) and request.csp_nonce:
            request_payload += "\0" + request.csp_nonce
        cache_key = (entry, payload, request_payload)
        if cache_key in self._cache:
            if self.cache_ttl and time.monotonic() - self._cache_times[cache_key] >= self.cache_ttl:
                expired = self._cache.pop(cache_key)
                self._cache_times.pop(cache_key, None)
                self._cache_bytes -= len(expired.html.encode()) + len(
                    expired.props_json.encode()
                )
            else:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]
        parts = []
        head_parts = []
        active_parts = parts
        size = 0
        steps = 0

        def write(value):
            nonlocal size
            size += len(value.encode())
            if size > self.max_output:
                raise ValueError("SSR output limit exceeded")
            active_parts.append(value)

        def render_nodes(nodes, scope, program, stack, slots=None):
            nonlocal active_parts, steps
            if len(stack) > 64:
                raise ValueError("SSR component nesting limit exceeded")
            for node in nodes:
                steps += 1
                if steps > self.max_iterations * 100:
                    raise ValueError("SSR instruction limit exceeded")
                try:
                    op = node["op"]
                    if op == "text":
                        write(node["value"])
                    elif op == "expression":
                        value = evaluate(node["value"], scope)
                        write(
                            html.escape(
                                ""
                                if value is None or value is UNDEFINED
                                else string(value)
                            )
                        )
                    elif op == "if":
                        render_nodes(
                            node["children"]
                            if truthy(evaluate(node["value"], scope))
                            else node["else"],
                            scope,
                            program,
                            stack,
                            slots,
                        )
                    elif op == "for":
                        value = evaluate(node["value"], scope)
                        if value is None or value is UNDEFINED:
                            value = []
                        if not isinstance(value, (list, dict)):
                            raise ValueError(
                                "SSR loops require arrays or plain objects"
                            )
                        if len(value) > self.max_iterations:
                            raise ValueError("SSR iteration limit exceeded")
                        iterable = enumerate(
                            value.values() if isinstance(value, dict) else value
                        )
                        for index, item in iterable:
                            local = {
                                **scope,
                                node["item"]: item,
                                node["index"]: index,
                                "index": index,
                            }
                            render_nodes(node["children"], local, program, stack, slots)
                    elif op == "slot":
                        selected = (slots or {}).get(node["name"])
                        if selected:
                            render_nodes(*selected)
                        else:
                            render_nodes(node["children"], scope, program, stack, slots)
                    elif op in {"component", "dynamic_component"}:
                        child_entry = (
                            node["entry"]
                            if op == "component"
                            else program["imports"].get(
                                string(evaluate(node["component"], scope)), ""
                            )
                        )
                        if child_entry not in self.programs:
                            raise ValueError("Unknown SSR dynamic component")
                        if child_entry in stack:
                            raise ValueError("Recursive SSR component import")
                        child = self.programs[child_entry]
                        props = {
                            **node["attributes"],
                            **{
                                name: evaluate(value, scope)
                                for name, value in node["bindings"].items()
                            },
                        }
                        # Keep the custom host element used by Teloce's browser runtime.
                        tag = node["tag"]
                        write(
                            "<"
                            + tag
                            + ' data-teloce-ssr="1" data-teloce-ssr-boundary="1">'
                        )
                        projected = {}
                        for projected_node in node["children"]:
                            name = projected_node.get("attributes", {}).get(
                                "slot", "default"
                            )
                            projected.setdefault(name, []).append(projected_node)
                        child_slots = {
                            name: (nodes, scope, program, stack, slots)
                            for name, nodes in projected.items()
                        }
                        render_nodes(
                            child["nodes"],
                            {
                                **props,
                                **(
                                    {"request": request_data}
                                    if request_data is not None
                                    else {}
                                ),
                            },
                            child,
                            (*stack, child_entry),
                            child_slots,
                        )
                        write("</" + tag + ">")
                    elif op == "element":
                        attributes = {**node["attributes"]}
                        text = None
                        for name, expr in node["bindings"].items():
                            value = evaluate(expr, scope)
                            if name == "text":
                                text = (
                                    ""
                                    if value is None or value is UNDEFINED
                                    else string(value)
                                )
                            elif name in {"show", "hide"}:
                                if truthy(value) == (name == "hide"):
                                    attributes["hidden"] = True
                            elif name != "key":
                                attributes[name] = value
                        if node["tag"].lower() == "iframe":
                            iframe_url = urlsplit(string(attributes.get("src", "")))
                            if (
                                iframe_url.scheme != "https"
                                or iframe_url.hostname != "www.youtube-nocookie.com"
                                or not iframe_url.path.startswith("/embed/")
                            ):
                                raise ValueError(
                                    "SSR iframes must use YouTube privacy embed URLs"
                                )
                        is_head = node["tag"].lower() in {"title", "meta", "link"}
                        previous_parts = active_parts
                        if is_head:
                            active_parts = []
                        try:
                            write(
                                "<"
                                + node["tag"]
                                + "".join(
                                    attribute(name, value)
                                    for name, value in attributes.items()
                                )
                                + ">"
                            )
                            if node["tag"].lower() not in VOID_ELEMENTS:
                                if text is not None:
                                    write(html.escape(text))
                                else:
                                    render_nodes(
                                        node["children"], scope, program, stack, slots
                                    )
                                write("</" + node["tag"] + ">")
                        finally:
                            if is_head:
                                head_parts.append("".join(active_parts))
                            active_parts = previous_parts
                    else:
                        raise ValueError("Unknown SSR instruction")
                except SSRRenderError:
                    raise
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    OverflowError,
                    RecursionError,
                ) as error:
                    raise SSRRenderError(
                        str(error),
                        component=program["component"],
                        location=node.get("location"),
                    ) from error

        program = self.programs[entry]
        scope = {
            **data,
            **({"request": request_data} if request_data is not None else {}),
        }
        render_nodes(program["nodes"], scope, program, (entry,))
        assets = []
        visited = set()

        def collect_assets(name):
            if name in visited:
                return
            visited.add(name)
            assets.extend(self.entries[name].get("assets", []))
            for child in self.programs[name].get("imports", {}).values():
                collect_assets(child)

        collect_assets(entry)
        result = RenderResult(
            "".join(parts),
            payload,
            tuple(dict.fromkeys(assets)),
            head=tuple(head_parts),
            csp_nonce=request.csp_nonce if isinstance(request, SSRRequest) else None,
        )
        if self.cache_size:
            self._cache[cache_key] = result
            self._cache_times[cache_key] = time.monotonic()
            self._cache_bytes += len(result.html.encode()) + len(payload.encode())
            while len(self._cache) > self.cache_size or self._cache_bytes > 8_000_000:
                removed_key, removed = self._cache.popitem(last=False)
                self._cache_times.pop(removed_key, None)
                self._cache_bytes -= len(removed.html.encode()) + len(
                    removed.props_json.encode()
                )
        return result

    def clear_cache(self, entry=None):
        """Invalidate all cached renders, or only renders for one entry."""
        if entry is None:
            self._cache.clear()
            self._cache_times.clear()
            self._cache_bytes = 0
            return
        for key in list(self._cache):
            if key[0] == entry:
                result = self._cache.pop(key)
                self._cache_times.pop(key, None)
                self._cache_bytes -= len(result.html.encode()) + len(
                    result.props_json.encode()
                )

    async def render_async(
        self, entry, context=None, *, request=None, server_data=None, timeout=None
    ):
        """Resolve host data asynchronously, then render a hydration-safe result.

        ``server_data`` may be a mapping or a callable receiving the normalized
        request scope. Its result is merged over ``context`` and is serialized
        into ``props_json``; request metadata itself is never serialized.
        """
        request_data = _request_scope(request)
        resolved = server_data
        if callable(server_data):
            resolved = server_data(request_data or {})
        if inspect.isawaitable(resolved):
            if timeout is None:
                resolved = await resolved
            else:
                resolved = await asyncio.wait_for(resolved, float(timeout))
        if resolved is None:
            resolved = {}
        if type(resolved) is not dict:
            raise SSRRenderError(
                "Server data must resolve to a plain JSON object", component=entry
            )
        initial = {} if context is None else context
        if type(initial) is not dict:
            raise ValueError("SSR public props must be a plain JSON object")
        return self.render(
            entry,
            {**initial, **resolved},
            request=request,
        )

    async def render_stream(
        self,
        entry,
        context=None,
        *,
        request=None,
        server_data=None,
        chunk_size=65536,
        timeout=None,
    ):
        """Yield rendered HTML in bounded chunks for ASGI/streaming hosts.

        Data resolution and instruction evaluation complete before the first
        chunk. This provides a portable async response interface while keeping
        the renderer's output and security limits deterministic.
        """
        if int(chunk_size) <= 0:
            raise ValueError("SSR stream chunk_size must be positive")
        result = await self.render_async(
            entry,
            context,
            request=request,
            server_data=server_data,
            timeout=timeout,
        )
        size = int(chunk_size)
        for offset in range(0, len(result.html), size):
            yield result.html[offset : offset + size]

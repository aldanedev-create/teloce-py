"""Small, declarative helpers for ordinary Teloce applications."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from teloce.router.compiler import RouterCompiler
from teloce.router.generator import RouterGenerator


def generate_router(
    output: str | Path,
    routes: Mapping[str, str | Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    mode: str = "hash",
    base: str = "/",
    imports: Mapping[str, str] | None = None,
    minify: bool = False,
) -> Path:
    """Generate a router from a small path-to-component declaration.

    The common form is intentionally compact::

        generate_router("dist/static/js/router.js", {
            "/": "./pages/HomePage.js",
            "/repo/:id": "./pages/RepoPage.js",
        })

    JavaScript component paths are imported automatically. Applications that
    already have component variables can use names instead, or supply an
    ``imports={"HomePage": "./pages/HomePage.js"}`` mapping. A mapping value
    may also be ``{"component": "HomePage", "import": "./pages/HomePage.js",
    "props": True}`` when route metadata is needed.

    Args:
        output: Destination JavaScript file.
        routes: A path mapping or RouterCompiler-compatible route objects.
        mode: ``hash`` (safe for ordinary Flask hosting) or ``history``.
        base: Router base path.
        imports: Optional component-name to module-specifier mapping.
        minify: Minify the generated router source.

    Returns:
        The resolved output path.

    Raises:
        ValueError: If the declaration fails router validation.
    """
    output_path = Path(output)
    import_map = dict(imports or {})
    route_definitions: list[dict[str, Any]] = []

    if isinstance(routes, Mapping):
        iterable = []
        for path, value in routes.items():
            if isinstance(value, Mapping):
                route = dict(value)
                route.setdefault("path", path)
            else:
                route = {"path": path, "component": value}
            iterable.append(route)
    else:
        iterable = [dict(route) for route in routes]

    generated_imports: dict[str, str] = {}
    for route in iterable:
        component = route.get("component")
        imported = route.pop("import", None)
        if isinstance(component, str) and component.endswith(".js"):
            imported = imported or component
            component = _component_name(imported)
        if imported:
            generated_imports[str(component)] = str(imported)
        route["component"] = component
        route_definitions.append(route)

    for name, specifier in import_map.items():
        generated_imports.setdefault(str(name), str(specifier))

    config = RouterCompiler().compile(
        {"mode": mode, "base": base, "routes": route_definitions}
    )
    if config is None:
        compiler = RouterCompiler()
        compiler.compile({"mode": mode, "base": base, "routes": route_definitions})
        details = "; ".join(compiler.errors) or "invalid route declaration"
        raise ValueError(f"Teloce router configuration failed: {details}")

    prefix = []
    for name, specifier in generated_imports.items():
        prefix.append(f"import {name} from {json.dumps(specifier)};")
    source = "\n".join(prefix + [RouterGenerator({"minify": minify}).generate(config), ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8")
    return output_path


def generate_spa_router(
    output: str | Path,
    pages_dir: str | Path,
    *,
    mode: str = "hash",
    base: str = "/",
    route_overrides: Mapping[str, str] | None = None,
    minify: bool = False,
) -> Path:
    """Generate a router by discovering compiled page modules on disk.

    Page filenames become routes automatically:

    ``HomePage.js`` or ``index.js`` -> ``/``
    ``SettingsPage.js`` -> ``/settings``
    ``repo/[id].js`` -> ``/repo/:id``
    ``docs/[...path].js`` -> ``/docs/*path``

    ``route_overrides`` is only needed when a filename does not express a
    dynamic route clearly, for example ``{"RepoPage.js": "/repo/:id"}``.
    Hashed implementation files are ignored when a stable production shim is
    present, so the same call works in development and production builds.
    """
    output_path = Path(output)
    pages_path = Path(pages_dir)
    if not pages_path.is_dir():
        raise ValueError(f"SPA pages directory does not exist: {pages_path}")

    overrides = {
        str(key).replace("\\", "/"): value
        for key, value in (route_overrides or {}).items()
    }
    modules = []
    for module in sorted(pages_path.rglob("*.js")):
        relative = module.relative_to(pages_path).as_posix()
        if module.name.endswith(".map") or re.search(r"\.[0-9a-fA-F]{8}\.js$", module.name):
            continue
        modules.append((module, relative))
    if not modules:
        raise ValueError(f"SPA pages directory has no JavaScript page modules: {pages_path}")

    route_definitions: list[dict[str, Any]] = []
    seen_routes: set[str] = set()
    seen_names: set[str] = set()
    for module, relative in modules:
        route = overrides.get(relative) or overrides.get(module.name) or _page_route(relative)
        component = _page_component_name(relative, seen_names)
        if route in seen_routes:
            raise ValueError(f"Duplicate SPA route discovered: {route}")
        seen_routes.add(route)
        specifier = Path(os.path.relpath(module, output_path.parent)).as_posix()
        if not specifier.startswith("."):
            specifier = "./" + specifier
        route_definitions.append({"path": route, "component": component, "import": specifier})

    return generate_router(
        output_path,
        route_definitions,
        mode=mode,
        base=base,
        minify=minify,
    )


def _component_name(specifier: str) -> str:
    """Derive a valid component variable from a JavaScript module path."""
    stem = Path(specifier.split("?", 1)[0]).stem
    stem = re.sub(r"\.[0-9a-fA-F]{8}$", "", stem)
    name = re.sub(r"[^A-Za-z0-9_$]", "", stem)
    if not name or not re.match(r"^[A-Za-z_$]", name):
        raise ValueError(f"Cannot derive a JavaScript component name from {specifier!r}")
    return name


def _page_component_name(relative: str, used: set[str]) -> str:
    """Derive a unique valid component identifier from a page filename."""
    path_parts = list(Path(relative).with_suffix("").parts)
    leaf = path_parts[-1] if path_parts else ""
    if leaf.lower() in {"index", "home", "homepage"} and len(path_parts) > 1:
        parts = [path_parts[-2]]
    elif leaf.startswith("["):
        # Keep the parent in dynamic page names so repo/[id].js is readable
        # as RepoIdPage and does not collide with users/[id].js.
        parts = path_parts
    elif leaf.lower().endswith("page"):
        # A descriptive filename already is the component name. Do not repeat
        # its parent folder (settings/SettingsPage.js).
        parts = [leaf]
    else:
        parts = [leaf] if leaf else []
    if not parts:
        parts = ["HomePage"]
    words = re.findall(r"[A-Za-z0-9_$]+", " ".join(parts)) or ["Page"]
    candidate = "".join(word[:1].upper() + word[1:] for word in words)
    if not candidate.endswith("Page"):
        candidate += "Page"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _page_route(relative: str) -> str:
    """Convert a page module path into a conventional SPA route."""
    segments = list(Path(relative).with_suffix("").parts)
    if segments and segments[-1].lower() in {"index", "home", "homepage"}:
        segments.pop()
    converted: list[str] = []
    for index, segment in enumerate(segments):
        if segment.startswith("[...") and segment.endswith("]"):
            value = "*" + segment[4:-1]
        elif segment.startswith("[[") and segment.endswith("]]"):
            value = ":" + segment[2:-2] + "?"
        elif segment.startswith("[") and segment.endswith("]"):
            value = ":" + segment[1:-1]
        else:
            clean = re.sub(r"Page$", "", segment, flags=re.IGNORECASE) or segment
            value = re.sub(r"(?<!^)([A-Z])", r"-\1", clean).lower()
        # Permit either pages/SettingsPage.js or pages/settings/
        # SettingsPage.js without producing /settings/settings.
        if index == len(segments) - 1 and converted and converted[-1] == value:
            continue
        converted.append(value)
    return "/" + "/".join(part.strip("/") for part in converted if part.strip("/"))

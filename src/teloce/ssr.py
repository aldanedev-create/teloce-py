"""Server-side rendering helpers using Flaxon's Jinax engine.

Teloce keeps browser directives in the emitted module, while this adapter
translates the server-safe subset into Jinax/Jinja syntax. It never executes
component JavaScript on the server; values and actions must be supplied by the
Python host application.
"""

from __future__ import annotations

import re
import inspect
from typing import Any, Mapping


def to_jinax_template(template: str) -> str:
    """Translate safe Teloce server directives to Jinax template syntax."""
    result = str(template)
    result = re.sub(r'\s+v-if="([^"]+)"', r' data-teloce-if="\1"', result)
    # Convert common element-level v-if blocks while preserving the element.
    result = re.sub(
        r'<([A-Za-z][\w:-]*)([^>]*?)data-teloce-if="([^"]+)"([^>]*)>([\s\S]*?)</\1>',
        r'{% if \3 %}<\1\2\4>\5</\1>{% endif %}', result,
    )
    result = re.sub(r'\s+(?:v-for|v-virtual-for)="(?:\(([^)]+)\)|([^\s]+))\s+(?:in|of)\s+([^\"]+)"',
                    lambda match: f' data-teloce-for="{match.group(1) or match.group(2)}|{match.group(3).strip()}"', result)
    result = re.sub(
        r'<([A-Za-z][\w:-]*)([^>]*?)data-teloce-for="([^|]+)\|([^\"]+)"([^>]*)>([\s\S]*?)</\1>',
        r'{% for \3 in \4 %}<\1\2\5>\6</\1>{% endfor %}', result,
    )
    # Event handlers are browser-only. Drop them from SSR output.
    result = re.sub(r'\s+(?:@[\w.-]+|v-on:[\w.-]+)="[^"]*"', '', result)
    result = re.sub(r'\s+v-(?:bind|model|show|text|html)(?::[\w-]+)?="[^"]*"', '', result)
    result = re.sub(r'\s+v-bind="\$attrs"', '', result)
    result = re.sub(r'\s+v-(?:memo|scrolly|step|chart-annotation|poll|live|virtual-for)(?:="[^"]*")?', '', result)
    result = re.sub(r'\s+use:[\w$.-]+(?:="[^"]*")?', '', result)
    result = re.sub(r'\s+(?:poll|interval|poll-target|live|live-target)="[^"]*"', '', result)
    result = re.sub(r'\s+data-teloce-(?:memo|scrolly|step|chart-annotation|virtual-for|virtual-item|virtual-collection|virtual-key|virtual-item-height|virtual-overscan|virtual-min-height|virtual-body)="[^"]*"', '', result)
    result = re.sub(r'\s+data-teloce-(?:if|for)="[^"]*"', '', result)
    result = re.sub(r'\s+>', '>', result)
    return result


async def render_ssr(
    template: str,
    context: Mapping[str, Any] | None = None,
    *,
    engine: Any | None = None,
) -> str:
    """Render a Teloce template through Flaxon's Jinax engine.

    ``template`` is the contents of a ``<template>`` section, not a complete
    ``.vel`` file. Jinax is imported lazily so Teloce remains usable without
    Flaxon installed.
    """
    if engine is None:
        try:
            from flaxon.jinax import Jinax
        except ImportError as exc:  # pragma: no cover - depends on optional host
            raise RuntimeError(
                "SSR requires a Jinax/Jinja-compatible engine; pass engine=... "
                "or install flaxon-framework"
            ) from exc
        engine = Jinax(template_directory=".")
    values = dict(context or {})
    translated = to_jinax_template(template)
    environment = getattr(engine, "environment", engine)
    if hasattr(environment, "from_string"):
        compiled = environment.from_string(translated)
        if hasattr(compiled, "render_async") and getattr(environment, "is_async", False):
            result = compiled.render_async(**values)
        else:
            result = compiled.render(**values)
    elif hasattr(engine, "render"):
        result = engine.render(translated, values)
    else:
        raise TypeError("SSR engine must provide from_string() or render()")
    if inspect.isawaitable(result):
        result = await result
    return str(result)


async def render_static_component(
    source: str,
    context: Mapping[str, Any] | None = None,
    *,
    components: Mapping[str, str] | None = None,
    engine: Any | None = None,
) -> str:
    """Render a complete ``.vel`` source without running its browser script.

    ``components`` is an optional allow-listed map of tag name to child
    ``.vel`` source. It is deliberately explicit: server rendering must not
    import arbitrary files or execute JavaScript discovered in a template.
    """
    match = re.search(r"<template(?:\s[^>]*)?>([\s\S]*?)</template\s*>", str(source), re.I)
    if not match:
        raise ValueError("Static component rendering requires a <template> block")
    template = match.group(1).strip()

    # Expand only an explicit, allow-listed component map. This is deliberately
    # a small template expansion step instead of an import mechanism: the
    # server never follows a path from user markup and never runs component
    # JavaScript. Props become Jinax/Jinja ``with`` variables so a child can
    # use ``{{ title }}`` exactly like a normal server template.
    allowed = {str(name).lower(): (str(name), source) for name, source in (components or {}).items()}

    def prop_bindings(raw_attributes: str) -> str:
        bindings = []
        for attribute in re.finditer(r'([:@]?[-\w]+)(?:\s*=\s*"([^"]*)")?', raw_attributes):
            name, value = attribute.groups()
            if not name or name.startswith("v-") or name.startswith("@"):
                continue
            key = name[1:] if name.startswith(":") else name
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                continue
            if name.startswith(":"):
                bindings.append(f"{key}={value or 'None'}")
            else:
                bindings.append(f"{key}={value!r}")
        return ", ".join(bindings)

    def expand(value: str, active: tuple[str, ...] = ()) -> str:
        result = str(value)
        for lookup, (display_name, child_source) in allowed.items():
            child_match = re.search(r"<template(?:\s[^>]*)?>([\s\S]*?)</template\s*>", child_source, re.I)
            if not child_match:
                raise ValueError(f"Imported static component {display_name!r} has no <template> block")
            child_template = child_match.group(1).strip()
            pair_pattern = re.compile(
                rf"<{re.escape(display_name)}\b([^>]*)>([\s\S]*?)</{re.escape(display_name)}\s*>", re.I
            )
            self_pattern = re.compile(rf"<{re.escape(display_name)}\b([^>]*)/\s*>", re.I)
            if lookup in active and (pair_pattern.search(result) or self_pattern.search(result)):
                raise ValueError(f"Recursive static component import: {' -> '.join((*active, display_name))}")
            if lookup in active:
                continue

            def render_child(child_match: re.Match[str], slot: str = "") -> str:
                nested = expand(child_template, (*active, lookup))
                nested = re.sub(r"<slot(?:\s[^>]*)?/?\s*>", slot, nested, flags=re.I)
                bindings = prop_bindings(child_match.group(1) or "")
                if bindings:
                    return f"{{% with {bindings} %}}{nested}{{% endwith %}}"
                return nested

            result = pair_pattern.sub(render_child, result)
            result = self_pattern.sub(lambda child: render_child(child), result)
        return result

    template = expand(template)
    return await render_ssr(to_jinax_template(template), context, engine=engine)


render_static = render_static_component

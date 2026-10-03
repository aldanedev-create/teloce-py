"""Source-file extension helpers shared by discovery and compilation."""

from __future__ import annotations

import re
from collections.abc import Iterable


DEFAULT_SOURCE_EXTENSIONS = (".vel",)
HTML_SOURCE_EXTENSIONS = (".html", ".vel")


def normalize_source_extensions(
    value: str | Iterable[str] | None = None,
    *,
    html_mode: bool = False,
) -> tuple[str, ...]:
    """Return normalized, unique component extensions.

    HTML mode deliberately retains ``.vel`` support so projects can migrate
    incrementally instead of converting every component in one change.
    """
    raw = HTML_SOURCE_EXTENSIONS if value is None and html_mode else value
    if raw is None:
        raw = DEFAULT_SOURCE_EXTENSIONS
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]

    result: list[str] = []
    for item in raw:
        extension = str(item).strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        if not re.fullmatch(r"\.[a-z0-9]+", extension):
            raise ValueError(f"Invalid Teloce source extension: {item!r}")
        if extension not in result:
            result.append(extension)
    if not result:
        raise ValueError("At least one Teloce source extension is required")
    return tuple(result)


def source_extension_pattern(extensions: Iterable[str]) -> str:
    """Return a regex alternation for normalized extensions."""
    return "(?:" + "|".join(re.escape(item) for item in extensions) + ")"

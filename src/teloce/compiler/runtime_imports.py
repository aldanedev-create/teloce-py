"""Bare ``teloce/...`` imports in component scripts.

A component can write ``import { http } from "teloce/runtime"`` instead of a relative path such as
``"../../teloce-runtime.js"``. The build knows where the shared runtime lives for each component, so the
specifier is rewritten to the right relative URL. This mirrors how Node resolves a package name.
"""

from __future__ import annotations

import json
import posixpath
import re
from typing import List

# Importable names after ``teloce/``. ``runtime`` is the barrel that re-exports everything.
RUNTIME_MODULES = {
    "runtime": None,
    "network": "network.js",
    "signals": "signals.js",
    "data": "data.js",
    "scheduler": "scheduler.js",
    "table": "table.js",
}

_IMPORT_RE = re.compile(
    r"""(?P<head>\b(?:from|import)\s*\(?\s*)(?P<quote>["'])teloce(?:/(?P<sub>[A-Za-z0-9_-]+))?(?P=quote)"""
)


def rewrite_teloce_imports(source: str, runtime_import: str) -> str:
    """Rewrite ``"teloce"`` and ``"teloce/<module>"`` specifiers to URLs relative to the importing file.

    ``runtime_import`` is the relative URL of the shared runtime barrel for the component being compiled.
    Unknown module names are left alone (the compiler reports them separately).
    """
    if not runtime_import or "teloce" not in source:
        return source

    def replace(match: re.Match) -> str:
        sub = match.group("sub") or "runtime"
        if sub not in RUNTIME_MODULES:
            return match.group(0)
        filename = RUNTIME_MODULES[sub]
        target = runtime_import if filename is None else posixpath.join(posixpath.dirname(runtime_import), filename)
        return f"{match.group('head')}{json.dumps(target)}"

    return _IMPORT_RE.sub(replace, source)


def unknown_teloce_imports(source: str) -> List[tuple]:
    """Return ``(offset, specifier)`` for ``teloce/<name>`` imports that are not a known module."""
    found = []
    for match in _IMPORT_RE.finditer(source):
        sub = match.group("sub")
        if sub and sub not in RUNTIME_MODULES:
            found.append((match.start(), f"teloce/{sub}"))
    return found

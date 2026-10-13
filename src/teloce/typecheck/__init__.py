"""Type-check TypeScript in Teloce components and template expressions.

Requires the optional ``pytscheck`` package: ``pip install "teloce-py[typecheck]"``.
"""

from teloce.typecheck.adapter import (
    Finding,
    TypecheckResult,
    TypecheckUnavailable,
    check_project,
    discover_roots,
    free_identifiers,
)

__all__ = [
    "Finding",
    "TypecheckResult",
    "TypecheckUnavailable",
    "check_project",
    "discover_roots",
    "free_identifiers",
]

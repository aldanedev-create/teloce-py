"""Typecheck command - type-check TypeScript in components and template expressions with pytscheck."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def typecheck_command(args: Any) -> int:
    """Run ``teloce typecheck``. Exit codes: 0 clean, 1 type errors found, 2 not available / bad input."""
    from teloce.typecheck import TypecheckUnavailable, check_project, discover_roots

    roots = [Path(p) for p in (args.paths or [])] or discover_roots(Path.cwd())
    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        print(f"error: path not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        result = check_project(
            roots, templates=not args.no_templates, strict=not args.no_strict
        )
    except TypecheckUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "compiler": result.compiler,
                    "findings": [vars(f) for f in result.findings],
                },
                indent=2,
            )
        )
    else:
        for finding in result.findings:
            print(finding.format())
        files = len({f.file for f in result.findings})
        if result.ok:
            print("No type errors found.")
        else:
            print(
                f"\nFound {len(result.findings)} error{'s' if len(result.findings) != 1 else ''} in {files} file{'s' if files != 1 else ''}."
            )
    return 0 if result.ok else 1

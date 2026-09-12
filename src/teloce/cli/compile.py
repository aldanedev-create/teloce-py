"""Compile one .vel component from the command line."""

import json
import sys
from pathlib import Path
from typing import Any

from teloce.compiler.compiler import compile_file


def _default_fix(message: str) -> str | None:
    """Give a useful first action when an older diagnostic lacks suggestions."""
    lowered = message.lower()
    if any(term in lowered for term in ("unclosed", "closing", "end tag", "unterminated")):
        return "Check that every template, script, style, and HTML element has a matching closing tag."
    if "missing <template" in lowered:
        return "Add one <template>...</template> block to the component."
    if "javascript" in lowered or "script" in lowered:
        return "Check the <script> block for balanced braces, parentheses, and quotes; also check every tag has a closing tag."
    return None


def _print_diagnostics(source: Path, diagnostics: dict[str, Any], *, as_json: bool = False) -> None:
    """Print actionable diagnostics while retaining a machine-readable mode."""
    if as_json:
        print(json.dumps(diagnostics, indent=2))
        return

    try:
        source_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        source_lines = []

    stream = sys.stderr
    printed = False
    for level in ("errors", "warnings", "info", "hints"):
        for diagnostic in diagnostics.get(level, []):
            printed = True
            severity = level[:-1].upper() if level.endswith("s") else level.upper()
            code = f" [{diagnostic['code']}]" if diagnostic.get("code") else ""
            filename = diagnostic.get("filename") or str(source)
            line = diagnostic.get("line")
            column = diagnostic.get("column")
            location = filename
            if line:
                location += f":{line}"
                if column:
                    location += f":{column}"
            print(f"{severity}{code} {location}: {diagnostic.get('message', 'Unknown diagnostic')}", file=stream)

            if line and 1 <= line <= len(source_lines):
                source_line = source_lines[line - 1]
                print(f"  {line:>4} | {source_line}", file=stream)
                if column:
                    print(f"       | {' ' * max(column - 1, 0)}^", file=stream)
            suggestions = diagnostic.get("suggestions", []) or []
            if not suggestions:
                fallback = _default_fix(diagnostic.get("message", ""))
                if fallback:
                    suggestions = [fallback]
            for suggestion in suggestions:
                print(f"  Fix: {suggestion}", file=stream)
            for note in diagnostic.get("notes", []) or []:
                print(f"  Note: {note}", file=stream)

    if not printed:
        print("Compilation failed without a structured diagnostic.", file=stream)


def compile_command(args: Any) -> int:
    source = Path(args.source)
    output = Path(args.output) if args.output else source.with_suffix('.js')
    result = compile_file(source, source_maps=args.source_map, dev=False)
    if not result.get('success'):
        _print_diagnostics(source, result.get('diagnostics', {}), as_json=getattr(args, 'json', False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.get('code', ''), encoding='utf-8')
    if result.get('css'):
        output.with_suffix('.css').write_text(result['css'], encoding='utf-8')
    if args.source_map and result.get('map'):
        output.with_suffix(output.suffix + '.map').write_text(
            json.dumps(result['map'], indent=2), encoding='utf-8'
        )
    print(f"Compiled {source} -> {output}")
    return 0

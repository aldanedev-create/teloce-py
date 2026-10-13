"""
Main CLI entry point.

Provides the command-line interface for Teloce.
"""

import sys
import argparse
from typing import Optional

from teloce.cli.dev import dev_command
from teloce.cli.build import build_command
from teloce.cli.prerender import prerender_command
from teloce.cli.watch import watch_command
from teloce.cli.debug import debug_command
from teloce.cli.doctor import doctor_command
from teloce.cli.lint import lint_command
from teloce.cli.typecheck import typecheck_command
from teloce.cli.create import create_command
from teloce.cli.benchmark import benchmark_command
from teloce.cli.compile import compile_command
from teloce.cli.component import component_command
from teloce.version import __version__


def main(args: Optional[list] = None) -> int:
    """
    Main CLI entry point.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    # Windows users often run the CLI with a legacy cp1252 console.  Teloce's
    # status output contains useful Unicode symbols, so make output reliable
    # without requiring users to set PYTHONIOENCODING themselves.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(
        prog='teloce',
        description='Teloce - A Python compiler for .vel Single File Components',
        epilog='For more information, visit https://github.com/aldanedev-create/teloce-py/tree/main/docs'
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'Teloce-Py {__version__}'
    )
    
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to run',
        required=True
    )
    
    prerender_parser = subparsers.add_parser("prerender", help="Export an SSR build entry to hydrated HTML")
    prerender_parser.add_argument("entry", help="Manifest entry, such as ui/App.html")
    prerender_parser.add_argument("--build-dir", default="dist")
    prerender_parser.add_argument("--data", help="JSON file containing public props")
    prerender_parser.add_argument("--output", default="index.html", help="Path within the build directory")

    # Dev command
    dev_parser = subparsers.add_parser('dev', help='Start development server')
    dev_parser.add_argument(
        '-p', '--port',
        type=int,
        default=None,
        help='Port to run on (default: teloce.config.json or 5173)'
    )
    dev_parser.add_argument(
        '-H', '--host',
        default=None,
        help='Host to bind to (default: teloce.config.json or 127.0.0.1)'
    )
    dev_parser.add_argument(
        '--no-hmr',
        action='store_true',
        help='Disable hot module replacement'
    )
    dev_parser.add_argument(
        '--proxy',
        help='Proxy target URL'
    )
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build for production')
    build_parser.add_argument(
        '-o', '--out-dir',
        default=None,
        help='Output directory (default: teloce.config.json or dist)'
    )
    build_parser.add_argument(
        '--minify',
        action='store_true',
        help='Minify output'
    )
    build_parser.add_argument(
        '--no-minify',
        action='store_true',
        help='Disable minification'
    )
    build_parser.add_argument(
        '--source-map',
        action='store_true',
        help='Generate source maps'
    )
    build_parser.add_argument(
        '--direct-dom-updates',
        dest='direct_dom_updates',
        action='store_true',
        help='Enable dependency-aware in-place DOM updates for safe components'
    )
    build_parser.add_argument(
        '--no-direct-dom-updates',
        dest='no_direct_dom_updates',
        action='store_true',
        help='Disable direct DOM updates and use compatibility reconciliation'
    )
    build_parser.add_argument(
        '--strict-direct-dom',
        dest='strict_dependency_analysis',
        action='store_true',
        help='Fail the build when a direct-update expression requires fallback'
    )

    compile_parser = subparsers.add_parser('compile', help='Compile one .vel…6193 tokens truncated…e]]) -> None:
        self._start(tag, attrs, True)

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            name, opened = self._stack.pop()
            if opened:
                self._close_loop()
            if name == tag:
                break

    def handle_data(self, data: str) -> None:
        line, col = self.getpos()
        for m in re.finditer(r"\{\{(.*?)\}\}", data, re.S):
            self._unit(m.group(1), self._position(line, col, data, m.start(1)))


# --------------------------------------------------------------------------- adapter


class _Adapter:
    name = "teloce-sfc"
    protocol_version = "1.0"

    def __init__(self, roots: Sequence[Path], templates: bool) -> None:
        self.roots, self.templates = list(roots), templates
        self.origins: dict[str, list[tuple[tuple[int, int], str] | None]] = {}
        self.template_origin: dict[str, str] = {}
        self.script_origins: dict[
            str, tuple[str, str, str, int, int, tuple[int, int] | None]
        ] = {}
        self.original_text: dict[str, str] = {}

    context: Any = None

    def get_context(self, project_root: str | Path) -> Any:
        return self.context

    def get_sources(self, project_root: str | Path) -> list[Any]:
        from pytscheck import SourceFile

        base = Path(project_root)
        sources = [
            SourceFile(path="teloce-shims.d.ts", text=SHIMS_DTS),
            SourceFile(path="teloce-define.d.ts", text=DEFINE_DTS),
        ]
        files: list[Path] = []
        for root in self.roots:
            for directory, dirs, names in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                files.extend(
                    Path(directory) / name
                    for name in sorted(names)
                    if (Path(directory) / name).is_file()
                )
        by_rel = {p.relative_to(base).as_posix(): p for p in files}
        for rel, path in by_rel.items():
            if path.suffix == ".ts" and self.context is None:
                sources.append(
                    SourceFile(path=rel, text=path.read_text(encoding="utf-8"))
                )
        for rel, path in by_rel.items():
            if path.suffix not in {".html", ".vel"}:
                continue
            text = path.read_text(encoding="utf-8")
            script = _SCRIPT.search(text)
            if not script:
                continue
            body = script.group(2)
            wrapped = rewrite_default_export(body)
            prefix = "".join(
                "\n" if char == "\n" else " " * (len(char.encode("utf-16-le")) // 2)
                for char in text[: script.start(2)]
            )
            padded = prefix + (wrapped if wrapped is not None else body)
            self.original_text[rel] = text
            self.script_origins[rel + ".ts"] = (
                rel,
                text,
                padded,
                len(prefix),
                script.start(2),
                _export_object_span(body),
            )
            sources.append(SourceFile(path=rel + ".ts", text=padded, origin_path=rel))
            template = _TEMPLATE.search(text)
            if self.templates and wrapped is not None and template:
                sources.append(self._template_source(rel, path.name, text, template))
        return sources

    def _template_source(
        self, rel: str, filename: str, text: str, template: re.Match[str]
    ) -> Any:
        from pytscheck import SourceFile

        inner = template.group(1)
        first_line = text[: template.start(1)].count("\n") + 1
        first_col = template.start(1) - (text.rfind("\n", 0, template.start(1)) + 1)
        walker = _TemplateWalker()
        walker.feed(inner)
        walker.close()
        header = [
            f'import __component from "./{filename}.ts";',
            "type Ctx = typeof __component extends { readonly __ctx: infer X } ? X : never;",
            "declare const __ctx: Ctx;",
            "function __template() {",
        ]
        mapped: list[tuple[tuple[int, int], str] | None] = [None] * len(header)
        for origin in walker.origins:
            if origin is None:
                mapped.append(None)
                continue
            (line, col), expr = origin
            mapped.append(
                ((line + first_line - 1, col + (first_col if line == 1 else 0)), expr)
            )
        mapped.append(None)
        path = rel + ".tpl.ts"
        self.origins[path] = mapped
        self.template_origin[path] = rel
        return SourceFile(path=path, text="\n".join(header + walker.out + ["}"]) + "\n")

    @staticmethod
    def _tidy(message: str) -> str:
        """Replace the (very long) generated component type in a message with a readable phrase."""
        return re.sub(
            r"on type '[^']*(?:Computed<|\{ readonly __ctx)[^']*'",
            "on this component",
            message,
        )

    def to_findings(self, errors: Iterable[Any]) -> list[Finding]:
        findings: list[Finding] = []
        for error in errors:
            script = self.script_origins.get(
                getattr(error, "origin_file", None) or error.file
            )
            if script is not None:
                rel, original, generated, prefix, original_start, span = script
                rows = generated.splitlines(keepends=True)
                row = rows[error.line - 1] if 0 < error.line <= len(rows) else ""
                within = len(
                    row.encode("utf-16-le")[: max(0, error.column - 1) * 2].decode(
                        "utf-16-le", errors="ignore"
                    )
                )
                offset = max(
                    0, sum(len(r) for r in rows[: error.line - 1]) + within - prefix
                )
                if span is not None:
                    start, end = span
                    if offset >= end + 9 + 1:
                        offset -= 10
                    elif offset >= start + 9:
                        offset -= 9
                    elif offset >= start:
                        offset = start
                absolute = min(len(original), original_start + offset)
                line = original.count("\n", 0, absolute) + 1
                before = original[original.rfind("\n", 0, absolute) + 1 : absolute]
                column = len(before.encode("utf-16-le")) // 2 + 1
                findings.append(Finding(rel, line, column, error.code, error.message))
                continue
            table = self.origins.get(error.file)
            if table is None:
                findings.append(
                    Finding(
                        error.file, error.line, error.column, error.code, error.message
                    )
                )
                continue
            hit = table[error.line - 1] if 0 < error.line <= len(table) else None
            rel = self.template_origin[error.file]
            if hit is None:
                findings.append(
                    Finding(rel, 1, 1, error.code, self._tidy(error.message))
                )
                continue
            (line, col), expr = hit
            named = re.search(r"Property '([\w$]+)'", error.message)
            if named:
                inside = re.search(
                    r"(?<![\w$])" + re.escape(named.group(1)) + r"(?![\w$])", expr
                )
                if inside:
                    before = expr[: inside.start()]
                    if "\n" in before:
                        line += before.count("\n")
                        col = len(before.rsplit("\n", 1)[1])
                    else:
                        col += len(before)
            original_line = self.original_text[rel].splitlines()[line - 1]
            column = len(original_line[:col].encode("utf-16-le")) // 2 + 1
            findings.append(
                Finding(rel, line, column, error.code, self._tidy(error.message))
            )
        return findings


def discover_roots(start: str | Path) -> list[Path]:
    """Find component folders: ``ui`` and ``modules/*/ui`` under ``start`` (falls back to ``start``)."""
    root = Path(start)
    found = [p for p in [root / "ui", *sorted(root.glob("modules/*/ui"))] if p.is_dir()]
    return found or [root]


def check_project(
    roots: Sequence[str | Path],
    *,
    templates: bool = True,
    strict: bool | None = None,
    project_root: str | Path | None = None,
    tsconfig: str | Path | None = None,
) -> TypecheckResult:
    """Type-check every component and TypeScript file under ``roots`` with pytscheck."""
    import sys

    if sys.version_info < (3, 11):
        raise TypecheckUnavailable(
            "Teloce type checking requires Python 3.11 or newer."
        )
    try:
        import pytscheck
        from pytscheck.adapters import ProjectContext
    except (
        ImportError
    ) as exc:  # pragma: no cover - exercised through monkeypatching in tests
        raise TypecheckUnavailable(
            'pytscheck is not installed. Install it with: pip install "teloce-py[typecheck]"'
        ) from exc
    resolved = list(dict.fromkeys(Path(r).resolve() for r in roots))
    if not resolved:
        raise TypecheckUnavailable("Provide at least one UI directory to check.")
    for root in resolved:
        if not root.is_dir():
            raise TypecheckUnavailable(f"UI path is not a directory: {root}")
    try:
        common_root = Path(os.path.commonpath([str(r) for r in resolved]))
    except ValueError as exc:
        raise TypecheckUnavailable(
            "UI directories must share a filesystem root."
        ) from exc
    root = Path(project_root).resolve() if project_root is not None else common_root
    config = (root / tsconfig).resolve() if tsconfig is not None else None
    if project_root is None and config is None:
        config = next(
            (
                parent / "tsconfig.json"
                for parent in (root, *root.parents)
                if (parent / "tsconfig.json").is_file()
            ),
            None,
        )
        if config is not None:
            root = config.parent
    if not root.is_dir() or any(
        not directory.is_relative_to(root) for directory in resolved
    ):
        raise TypecheckUnavailable("UI directories must be inside the project root.")
    inherited = config is not None or (root / "tsconfig.json").is_file()
    settings: dict[str, object] = {"allowImportingTsExtensions": True}
    if not inherited:
        settings.update(
            {
                "target": "es2022",
                "module": "esnext",
                "moduleResolution": "bundler",
                "lib": ["es2022", "dom"],
                "strict": True,
            }
        )
    if strict is not None:
        settings["strict"] = strict
    adapter = _Adapter(resolved, templates)
    adapter.context = ProjectContext(tsconfig=config, compiler_options=settings)
    from pytscheck.exceptions import PyTSCheckError

    try:
        result = pytscheck.check_project(root, adapter=adapter)
    except (PyTSCheckError, OSError, UnicodeError) as exc:
        raise TypecheckUnavailable(f"Type checking could not run: {exc}") from exc
    return TypecheckResult(
        findings=adapter.to_findings(result.errors),
        compiler=str(getattr(result, "compiler_version", "") or ""),
        elapsed=float(getattr(result, "elapsed_seconds", 0.0) or 0.0),
    )

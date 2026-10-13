"""pytscheck adapter for Teloce single-file components.

Two kinds of virtual TypeScript are generated and checked by pytscheck:

* the ``<script lang="ts">`` block of each component, with line numbers kept identical to the
  ``.html``/``.vel`` file, and the default export wrapped so that ``this`` is typed;
* one function per template that contains an expression statement for every ``{{ }}``,
  ``:attr``, ``v-if``/``v-else-if``/``v-show``/``v-text``/``v-html``/``v-model``, ``v-for`` source
  and ``@event`` handler. Diagnostics are mapped back to the original template position.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Sequence

SKIP_DIRS = {
    "node_modules",
    ".flaxon",
    ".git",
    ".venv",
    "venv",
    "dist",
    "__pycache__",
    ".mypy_cache",
}

DEFINE_DTS = """
type Fn = (...args: any[]) => any;
type Computed<C> = { [K in keyof C]: C[K] extends (...a: any[]) => infer R ? R : never };
declare function __define<P extends string = never, D = {}, C extends Record<string, Fn> = {}, M extends Record<string, Fn> = {}>(
  options: {
    components?: Record<string, unknown>;
    props?: readonly P[];
    data?: () => D;
    computed?: C;
    methods?: M;
    mounted?: () => unknown;
    unmounted?: () => unknown;
  } & ThisType<D & Computed<C> & M & { [K in P]: any }>
): { readonly __ctx: D & Computed<C> & M & { [K in P]: any } };
declare function __forEach<T>(source: readonly T[], cb: (item: T, index: number) => void): void;
declare function __forEach(source: number, cb: (item: number, index: number) => void): void;
declare function __forEach<T extends object>(source: T, cb: (value: T[keyof T], key: string, index: number) => void): void;
"""
SHIMS_DTS = 'declare module "*.html" { const component: any; export default component; }\ndeclare module "*.vel" { const component: any; export default component; }\n'


class TypecheckUnavailable(RuntimeError):
    """Dependency, input, or compiler failure preventing a type-check run."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    column: int
    code: int
    message: str

    def format(self) -> str:
        return f"{self.file}({self.line},{self.column}): error TS{self.code}: {self.message}"


@dataclass
class TypecheckResult:
    findings: list[Finding] = field(default_factory=list)
    compiler: str = ""
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.findings


# --------------------------------------------------------------------------- scanning helpers


def _skip_string(text: str, i: int) -> int:
    quote, i = text[i], i + 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if quote == "`" and text.startswith("${", i):
            end = _match_brace(text, i + 1)
            i = len(text) if end < 0 else end + 1
            continue
        if char == quote:
            return i + 1
        i += 1
    return i


def _match_brace(text: str, i: int) -> int:
    """Return the index of the ``}`` matching the ``{`` at ``text[i]`` (or -1)."""
    depth = 0
    while i < len(text):
        char = text[i]
        if char in "'\"`":
            i = _skip_string(text, i)
            continue
        if text.startswith("//", i):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


_SCRIPT = re.compile(
    r"(<script\b[^>]*\blang\s*=\s*[\"']ts[\"'][^>]*>)(.*?)(</script>)", re.S | re.I
)
_TEMPLATE = re.compile(r"<template\b[^>]*>(.*)</template>", re.S | re.I)


def _export_object_span(body: str) -> tuple[int, int] | None:
    from teloce.javascript.tree_sitter_backend import parse_tree

    tree = parse_tree(body, "ts")
    for statement in tree.root_node.named_children:
        if statement.type != "export_statement":
            continue
        if not any(child.type == "default" for child in statement.children):
            continue
        value = statement.child_by_field_name("value")
        if value is not None and value.type == "object":
            encoded = body.encode("utf-8")
            return (
                len(encoded[: value.start_byte].decode("utf-8")),
                len(encoded[: value.end_byte].decode("utf-8")),
            )
    return None


def rewrite_default_export(body: str) -> str | None:
    """Wrap the actual default object export, ignoring comments and string contents."""
    span = _export_object_span(body)
    if span is None:
        return None
    start, end = span
    return body[:start] + "__define(" + body[start:end] + ")" + body[end:]


# --------------------------------------------------------------------------- template expressions

_KEYWORDS = {
    "true",
    "false",
    "null",
    "undefined",
    "typeof",
    "new",
    "in",
    "of",
    "instanceof",
    "void",
    "delete",
    "this",
}
_GLOBALS = {
    "Math",
    "Number",
    "String",
    "Boolean",
    "Array",
    "Object",
    "JSON",
    "Date",
    "parseInt",
    "parseFloat",
    "isNaN",
    "isFinite",
    "Infinity",
    "NaN",
    "window",
    "document",
    "console",
    "Intl",
    "Symbol",
    "Map",
    "Set",
    "encodeURIComponent",
    "decodeURIComponent",
    "$event",
}
_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def free_identifiers(expr: str, locals_: Iterable[str] = ()) -> list[str]:
    """Names an expression reads from the component (not properties, object keys, loop vars, or globals)."""
    local = set(locals_)
    arrow: set[str] = set()
    for m in re.finditer(r"\(([^()]*)\)\s*=>", expr):
        arrow.update(_IDENT.findall(m.group(1)))
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=>", expr):
        arrow.add(m.group(1))
    found: set[str] = set()
    stack: list[str] = []
    i, n = 0, len(expr)
    while i < n:
        char = expr[i]
        if char in "'\"`":
            quote, i = char, i + 1
            while i < n and expr[i] != quote:
                if quote == "`" and expr[i : i + 2] == "${":
                    end = _match_brace(expr, i + 1)
                    end = n if end < 0 else end
                    found.update(free_identifiers(expr[i + 2 : end], local))
                    i = end + 1
                    continue
                i += 2 if expr[i] == "\\" else 1
            i += 1
            continue
        if char in "([{":
            stack.append(char)
            i += 1
            continue
        if char in ")]}":
            if stack:
                stack.pop()
            i += 1
            continue
        if char.isdigit():
            i += len(re.match(r"\d[\w.]*", expr[i:]).group(0))  # type: ignore[union-attr]
            continue
        match = _IDENT.match(expr, i)
        if match:
            name, end = match.group(0), match.end()
            before, rest = expr[:i].rstrip(), expr[end:].lstrip()
            is_property = before.endswith(".") and not before.endswith("..")
            is_key = bool(
                stack
                and stack[-1] == "{"
                and before
                and before[-1] in "{,"
                and rest.startswith(":")
            )
            if not (
                is_property
                or is_key
                or name in _KEYWORDS
                or name in _GLOBALS
                or name in local
                or name in arrow
            ):
                found.add(name)
            i = end
            continue
        i += 1
    return sorted(found)


class _TemplateWalker(HTMLParser):
    """Emit one TypeScript statement per template expression, remembering where each came from."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.origins: list[tuple[tuple[int, int], str] | None] = []
        self._stack: list[tuple[str, bool]] = []
        self._scopes: list[set[str]] = [set()]

    def _emit(self, line: str, origin: tuple[tuple[int, int], str] | None) -> None:
        for physical in line.split("\n"):
            self.out.append(physical)
            self.origins.append(origin)

    def _locals(self) -> set[str]:
        return set().union(*self._scopes)

    @staticmethod
    def _position(line: int, col: int, raw: str, index: int) -> tuple[int, int]:
        before = raw[:index]
        newlines = before.count("\n")
        return (
            (line + newlines, col + index)
            if newlines == 0
            else (line + newlines, len(before) - before.rfind("\n") - 1)
        )

    def _unit(self, expr: str, loc: tuple[int, int], *, event: bool = False) -> None:
        lead = expr[: len(expr) - len(expr.lstrip())]
        if "\n" in lead:
            loc = (loc[0] + lead.count("\n"), len(lead) - lead.rfind("\n") - 1)
        else:
            loc = (loc[0], loc[1] + len(lead))
        expr = expr.strip()
        if not expr:
            return
        ids = free_identifiers(expr, self._locals())
        pattern = "{ " + ", ".join(ids) + " }" if ids else "{}"
        if event:
            line = f"(({pattern}: Ctx, $event: Event) => {{ {expr}; }})(__ctx, undefined as unknown as Event);"
        else:
            line = f"(({pattern}: Ctx) => {{ void ({expr}); }})(__ctx);"
        self._emit(line, (loc, expr))

    def _open_loop(self, value: str, loc: tuple[int, int]) -> bool:
        match = re.match(
            r"^\s*(?:\(([^)]*)\)|([\w$]+))\s+(?:in|of)\s+(.+)$", value, re.S
        )
        if not match:
            return False
        params = [
            p.strip()
            for p in (match.group(1) or match.group(2)).split(",")
            if p.strip()
        ]
        source = match.group(3).strip()
        ids = free_identifiers(source, self._locals())
        pattern = "{ " + ", ".join(ids) + " }" if ids else "{}"
        self._emit(
            f"__forEach((({pattern}: Ctx) => ({source}))(__ctx), ({', '.join(params)}) => {{",
            ((loc[0], loc[1] + match.start(3)), source),
        )
        self._scopes.append(set(params))
        return True

    def _close_loop(self) -> None:
        self._emit("});", None)
        self._scopes.pop()

    def _start(
        self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool
    ) -> None:
        raw, (line, col) = self.get_starttag_text() or "", self.getpos()
        opened = False
        for name, value in sorted(
            attrs, key=lambda a: a[0] != "v-for"
        ):  # v-for first: it opens a scope
            if value is None:
                continue
            found = re.search(re.escape(name) + r"\s*=\s*([\"'])", raw, re.I)
            loc = self._position(line, col, raw, found.end()) if found else (line, col)
            base = name.split(".", 1)[0]
            if name == "v-for":
                opened = self._open_loop(value, loc)
            elif name.startswith((":", "v-bind:")) or base in {
                "v-if",
                "v-else-if",
                "v-show",
                "v-text",
                "v-html",
                "v-model",
            }:
                self._unit(value, loc)
            elif name.startswith(("@", "v-on:")):
                self._unit(value, loc, event=True)
        if self_closing or tag in _VOID:
            if opened:
                self._close_loop()
        else:
            self._stack.append((tag, opened))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
            if path.suffix == ".ts":
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
    roots: Sequence[str | Path], *, templates: bool = True, strict: bool = True
) -> TypecheckResult:
    """Type-check every component and TypeScript file under ``roots`` with pytscheck."""
    import sys

    if sys.version_info < (3, 11):
        raise TypecheckUnavailable(
            "Teloce type checking requires Python 3.11 or newer."
        )
    try:
        import pytscheck
        from pytscheck import CompilerOptions
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
        project_root = Path(os.path.commonpath([str(r) for r in resolved]))
    except ValueError as exc:
        raise TypecheckUnavailable(
            "UI directories must share a filesystem root."
        ) from exc
    adapter = _Adapter(resolved, templates)
    options = CompilerOptions(
        strict=strict,
        target="es2022",
        module="esnext",
        module_resolution="bundler",
        lib=["es2022", "dom"],
        extra={"allowImportingTsExtensions": True},
    )
    from pytscheck.exceptions import PyTSCheckError

    try:
        result = pytscheck.check_project(project_root, options=options, adapter=adapter)
    except (PyTSCheckError, OSError, UnicodeError) as exc:
        raise TypecheckUnavailable(f"Type checking could not run: {exc}") from exc
    return TypecheckResult(
        findings=adapter.to_findings(result.errors),
        compiler=str(getattr(result, "compiler_version", "") or ""),
        elapsed=float(getattr(result, "elapsed_seconds", 0.0) or 0.0),
    )

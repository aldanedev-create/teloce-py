"""Tree-sitter based TypeScript -> JavaScript type stripping .


Strategy: parse with tree-sitter-typescript, collect the byte ranges of every
type-only construct, and blank them out. Blanked ranges keep their newlines so
line numbers (and therefore source maps) stay stable. Constructs that need real
code generation (enum, namespace, parameter properties, decorators) raise
TSUnsupported instead of silently producing broken output.
"""

from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_typescript as _ts
from tree_sitter import Language, Parser

_TS = Language(_ts.language_typescript())
_TSX = Language(_ts.language_tsx())

# Whole nodes that exist only for the type checker.
_DROP_NODES = {
    "type_annotation",          # ": T" on params, vars, fields, return types
    "type_alias_declaration",   # type X = ...
    "interface_declaration",    # interface X { ... }
    "ambient_declaration",      # declare ...
    "type_parameters",          # <T, U>
    "type_arguments",           # f<T>(x), new Map<K, V>()
    "implements_clause",        # class A implements B
    "function_signature",       # overload signatures
    "method_signature",         # overload signatures in classes
    "abstract_method_signature",
    "index_signature",
    "accessibility_modifier",   # public / private / protected
    "override_modifier",
}
# Single tokens to blank wherever they appear.
_DROP_TOKENS = {"readonly", "abstract", "declare"}

# Need real code generation -> refuse rather than emit wrong JS.
_UNSUPPORTED = {
    "enum_declaration": "enum (use `as const` objects or a const object)",
    "internal_module": "namespace / module",
    "decorator": "decorator",
}


class TSUnsupported(Exception):
    pass


class _Edits:
    def __init__(self, data: bytes):
        self.data = data
        self.items: list[tuple[int, int, bytes]] = []

    def blank(self, start: int, end: int) -> None:
        self.items.append((start, end, b""))  # filled with spaces on apply

    def replace(self, start: int, end: int, text: bytes) -> None:
        self.items.append((start, end, text))

    def apply(self) -> bytes:
        out = bytearray(self.data)
        # Apply right-to-left; skip ranges already covered by a larger edit.
        covered: list[tuple[int, int]] = []
        for start, end, text in sorted(self.items, key=lambda e: (-e[0], e[1] - e[0])):
            if any(s <= start and end <= e for s, e in covered):
                continue
            if text:
                out[start:end] = text
            else:
                chunk = bytes(out[start:end])
                out[start:end] = re.sub(rb"[^\r\n]", b" ", chunk)  # keep newlines
            covered.append((start, end))
        return bytes(out)


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _blank_with_comma(edits: _Edits, node) -> None:
    """Blank a list item and one adjacent comma so the list stays valid."""
    edits.blank(node.start_byte, node.end_byte)
    nxt, prev = node.next_sibling, node.prev_sibling
    if nxt is not None and nxt.type == ",":
        edits.blank(nxt.start_byte, nxt.end_byte)
    elif prev is not None and prev.type == ",":
        edits.blank(prev.start_byte, prev.end_byte)


def transpile(source: str, filename: str = "<ts>", tsx: bool = False) -> str:
    data = source.encode("utf-8")
    parser = Parser(_TSX if tsx else _TS)
    tree = parser.parse(data)
    edits = _Edits(data)

    for node in _walk(tree.root_node):
        t = node.type

        if node.is_error or node.is_missing:
            line = node.start_point[0] + 1
            raise SyntaxError(f"{filename}:{line}: TypeScript syntax error")

        if t in _UNSUPPORTED:
            line = node.start_point[0] + 1
            raise TSUnsupported(f"{filename}:{line}: {_UNSUPPORTED[t]} is not supported")

        if t == "required_parameter" or t == "optional_parameter":
            # constructor(private x: number) -> parameter property
            if any(c.type in ("accessibility_modifier", "readonly") for c in node.children):
                line = node.start_point[0] + 1
                raise TSUnsupported(f"{filename}:{line}: constructor parameter properties are not supported")

        if t in _DROP_NODES:
            edits.blank(node.start_byte, node.end_byte)
            continue

        if t in _DROP_TOKENS and not node.children:
            edits.blank(node.start_byte, node.end_byte)

        elif t == "?" and node.parent is not None and node.parent.type in (
            "optional_parameter", "public_field_definition", "property_signature", "method_definition"
        ):
            edits.blank(node.start_byte, node.end_byte)  # a?: T  /  f?()

        elif t in ("as_expression", "satisfies_expression"):
            expr = node.children[0]
            edits.blank(expr.end_byte, node.end_byte)

        elif t == "non_null_expression":
            bang = node.children[-1]
            edits.blank(bang.start_byte, bang.end_byte)

        elif t == "type_assertion":  # <T>expr  (not valid in .tsx)
            first, last = node.children[0], None
            for c in node.children:
                if c.type == "type_arguments":
                    last = c
            if last is not None:
                edits.blank(node.start_byte, last.end_byte)

        elif t == "import_statement":
            kids = [c.type for c in node.children]
            if "type" in kids[:2]:  # import type ... from
                edits.blank(node.start_byte, node.end_byte)
            else:
                clause = next((c for c in node.children if c.type == "import_clause"), None)
                specs = [n for n in _walk(node) if n.type == "import_specifier"]
                type_specs = [x for x in specs if x.children and x.children[0].type == "type"]
                has_value_binding = clause is not None and any(
                    c.type in ("identifier", "namespace_import") for c in clause.children
                )
                if specs and len(type_specs) == len(specs) and not has_value_binding:
                    edits.blank(node.start_byte, node.end_byte)  # every name was type-only
                else:
                    for x in type_specs:
                        _blank_with_comma(edits, x)

        elif t == "export_statement":
            kids = [c.type for c in node.children]
            if "type" in kids[:3] and "export_clause" in kids:  # export type { A } from ..
                edits.blank(node.start_byte, node.end_byte)
            else:
                decl = node.child_by_field_name("declaration")
                if decl is not None and decl.type in ("type_alias_declaration", "interface_declaration",
                                                       "ambient_declaration"):
                    edits.blank(node.start_byte, node.end_byte)

    # Local .ts specifiers -> .js so the browser can load the emitted file.
    for node in _walk(tree.root_node):
        if node.type in ("import_statement", "export_statement"):
            src = node.child_by_field_name("source")
            if src is None:
                continue
            frag = next((c for c in src.children if c.type == "string_fragment"), None)
            if frag is None:
                continue
            text = data[frag.start_byte:frag.end_byte].decode()
            if text.startswith(".") and re.search(r"\.m?ts$", text):
                new = re.sub(r"\.ts$", ".js", re.sub(r"\.mts$", ".mjs", text))
                edits.replace(frag.start_byte, frag.end_byte, new.encode())

    return edits.apply().decode("utf-8")


def rewrite_ts_specifiers(js: str) -> str:
    """For already-generated JS (e.g. App.vel output): ./x.ts -> ./x.js."""
    return re.sub(r"""((?:from|import)\s*\(?\s*['"]\.{1,2}/[^'"]*?)\.ts(['"])""", r"\1.js\2", js)


def compile_ts_tree(root: Path, out_dir: Path) -> list[str]:
    """Emit a .js file for every .ts under root (skips .d.ts, node_modules, out_dir)."""
    written = []
    root, out_dir = Path(root), Path(out_dir)
    for f in sorted(root.rglob("*.ts")):
        if f.name.endswith(".d.ts") or "node_modules" in f.parts or out_dir in f.parents:
            continue
        rel = f.relative_to(root).with_suffix(".js")
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(transpile(f.read_text(encoding="utf-8"), str(f)), encoding="utf-8")
        written.append(rel.as_posix())
    return written

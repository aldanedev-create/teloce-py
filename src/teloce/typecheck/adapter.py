"""pytscheck adapter for Teloce single-file components.

Two kinds of virtual TypeScript are generated and checked by pytscheck:

* the ``<script lang="ts">`` block of each component, with line numbers kept identical to the
  ``.html``/``.vel`` file, and the default export wrapped so that ``this`` is typed;
* one function per template that contains an expression statement for every ``{{ }}``,
  ``:attr``, ``v-if``/``v-else-if``/``v-show``/``v-text``/``v-html``/``v-model``, ``v-for`` source
  and ``@event`` handler. Diagnostics are mapped back to the original template position.
"""

from __future__ import annotations

import html
import json
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

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
type PropValue<T> = T extends StringConstructor ? string : T extends NumberConstructor ? number :
  T extends BooleanConstructor ? boolean : T extends readonly unknown[] ? PropValue<T[number]> : T extends ArrayConstructor ? unknown[] :
  T extends ObjectConstructor ? Record<string, unknown> : T extends FunctionConstructor ? Fn :
  T extends abstract new (...args: any[]) => infer V ? V : unknown;
type DeclaredProp<T> = T extends { type: infer V } ? PropValue<V> : PropValue<T>;
type OptionalProp<T> = T extends { required: true } | { default: unknown } ? DeclaredProp<T> : DeclaredProp<T> | undefined;
type Props<P> = P extends readonly string[] ? { readonly [K in P[number]]: any } :
  { readonly [K in keyof P]: OptionalProp<P[K]> };
type RequiredProps<P> = { [K in keyof P]: P[K] extends { required: true } ? K : never }[keyof P];
type PublicProps<P> = P extends readonly string[] ? ([P[number]] extends [never] ? Record<string, never> : { [K in P[number]]?: any }) :
  keyof P extends never ? Record<string, never> :
  { [K in RequiredProps<P>]: DeclaredProp<P[K]> } & { [K in Exclude<keyof P, RequiredProps<P>>]?: DeclaredProp<P[K]> };
declare function __checkProps<P>(props: P): void;
declare function __checkSlot<C>(name: C extends { readonly __slots: readonly (infer N)[] } ? N : string): void;
type RuntimeContext<E extends readonly string[]> = {
  $emit(name: E[number], detail?: unknown): void;
  readonly $attrs: Record<string, unknown>;
};
declare namespace __TeloceSignals {
  interface Signal<T> {
    (): T;
    (value: T): T;
    value: T;
    get(): T;
    set(value: T): T;
    update(updater: (value: T) => T): T;
    peek(): T;
    subscribe(listener: ((value: T) => void) | { run(value: T): void }): () => void;
    readonly __teloce_signal: true;
  }
  interface Effect { run(): unknown; stop(): void; stopped: boolean; }
  function createSignal<T>(initial: T): Signal<T>;
  function createSignal(): Signal<undefined>;
  function createComputed<T>(fn: () => T): Signal<T>;
  const createMemo: typeof createComputed;
  function createEffect(fn: () => unknown): Effect;
  function batch<T>(fn: () => T): T;
  function untracked<T>(fn: () => T): T;
  function isSignal(value: unknown): value is Signal<unknown>;
  function isComputed(value: unknown): value is Signal<unknown>;
  function toSignal<T>(value: T | Signal<T>): Signal<T>;
  function getValue<T>(value: T | Signal<T>): T;
}
declare function __define<const P extends readonly string[] | Record<string, unknown> = readonly [], D = {}, C extends Record<string, Fn> = {}, M extends Record<string, Fn> = {}, const E extends readonly string[] = readonly string[], const R extends Record<string, unknown> = {}, const S extends readonly string[] = readonly []>(
  options: {
    name?: string;
    components?: R;
    emits?: E;
    watch?: { [K in keyof D]?: (value: D[K], previous: D[K]) => unknown } & ThisType<D & Computed<C> & M & Props<P> & RuntimeContext<E>>;
    beforeCreate?: () => unknown;
    created?: () => unknown;
    beforeMount?: () => unknown;
    beforeUpdate?: () => unknown;
    updated?: () => unknown;
    activated?: () => unknown;
    deactivated?: () => unknown;
    beforeUnmount?: () => unknown;
    props?: P;
    data?: () => D;
    computed?: C;
    methods?: M;
    mounted?: () => unknown;
    unmounted?: () => unknown;
  } & ThisType<D & Computed<C> & M & Props<P> & RuntimeContext<E>>, slots?: S
): { readonly __ctx: D & Computed<C> & M & Props<P> & RuntimeContext<E>; readonly __props: PublicProps<P>; readonly __components: R; readonly __slots: S };
type ComponentProps<T> = T extends { readonly __props: infer P } ? P : Record<string, unknown>;
type Intersection<U> = (U extends unknown ? (value: U) => void : never) extends (value: infer I) => void ? I : never;
type DynamicProps<C, N extends string> = Intersection<{ [K in keyof C]: K extends string ? Lowercase<K> extends Lowercase<N> ? ComponentProps<C[K]> : never : never }[keyof C]>;
declare function __dynamic<C>(): <N extends (keyof C & string) | Lowercase<keyof C & string>>(name: N, props: DynamicProps<C, NoInfer<N>>) => void;
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
    r"(<script\b[^>]*>)(.*?)(</script>)",
    re.DOTALL | re.IGNORECASE,
)
_TEMPLATE = re.compile(r"<template\b[^>]*>(.*)</template>", re.DOTALL | re.IGNORECASE)


def _export_object_span(body: str) -> tuple[int, int] | None:
    from teloce.javascript.tree_sitter_backend import parse_tree

    tree = parse_tree(body, "ts")
    for statement in tree.root_node.named_children:
        if statement.type != "export_statement":
            continue
        if not any(child.type == "default" for child in statement.children):
            continue
        value = statement.child_by_field_name("value")
        if value is not None and value.type == "identifier":
            encoded = body.encode("utf-8")
            wanted = encoded[value.start_byte : value.end_byte]
            for declaration in tree.root_node.named_children:
                if declaration.type not in {
                    "lexical_declaration",
                    "variable_declaration",
                }:
                    continue
                for item in declaration.named_children:
                    name = item.child_by_field_name("name")
                    if (
                        name is not None
                        and encoded[name.start_byte : name.end_byte] == wanted
                    ):
                        value = item.child_by_field_name("value")
                        break
        if value is not None and value.type == "call_expression":
            arguments = value.child_by_field_name("arguments")
            value = (
                next(
                    (
                        item
                        for item in arguments.named_children
                        if item.type == "object"
                    ),
                    None,
                )
                if arguments
                else None
            )
        if value is not None and value.type == "object":
            encoded = body.encode("utf-8")
            return (
                len(encoded[: value.start_byte].decode("utf-8")),
                len(encoded[: value.end_byte].decode("utf-8")),
            )
    return None


def _component_imports(
    body: str, path: Path, generated: set[Path]
) -> dict[str, tuple[str, str]]:
    """Let TypeScript resolve default/named component imports and project aliases."""
    from teloce.javascript.tree_sitter_backend import parse_tree

    encoded = body.encode("utf-8")
    imports = {}

    def text(node):
        return encoded[node.start_byte : node.end_byte].decode("utf-8")

    for statement in parse_tree(body, "ts").root_node.named_children:
        if statement.type != "import_statement" or any(
            child.type == "type" for child in statement.children
        ):
            continue
        source = statement.child_by_field_name("source")
        clause = next(
            (
                child
                for child in statement.named_children
                if child.type == "import_clause"
            ),
            None,
        )
        if source is None or clause is None:
            continue
        module = text(source)[1:-1]
        if module.endswith((".html", ".vel")):
            module += ".ts"
        for child in clause.named_children:
            if child.type == "identifier":
                imports[text(child).lower()] = (module, "default")
            elif child.type == "namespace_import":
                alias = next(
                    (
                        part
                        for part in child.named_children
                        if part.type == "identifier"
                    ),
                    None,
                )
                if alias is not None:
                    imports[text(alias).lower() + ".*"] = (module, "*")
            elif child.type == "named_imports":
                for item in child.named_children:
                    if any(part.type == "type" for part in item.children):
                        continue
                    name = item.child_by_field_name("name")
                    alias = item.child_by_field_name("alias") or name
                    if name is not None and alias is not None:
                        imports[text(alias).lower()] = (module, text(name))
    # Registered aliases, including namespace members, determine runtime tags.
    span = _export_object_span(body)
    if span is not None:
        option_text = body[span[0] : span[1]]
        options = parse_tree("(" + option_text + ")", "ts")
        option_bytes = ("(" + option_text + ")").encode("utf-8")

        def option_source(node):
            return option_bytes[node.start_byte : node.end_byte].decode("utf-8")

        def walk(node):
            if node.type == "pair" and option_source(
                node.child_by_field_name("key")
            ) in {"components", '"components"', "'components'"}:
                registry = node.child_by_field_name("value")
                if registry is not None and registry.type == "object":
                    for entry in registry.named_children:
                        if entry.type == "shorthand_property_identifier":
                            continue
                        if entry.type != "pair":
                            continue
                        key, value = (
                            entry.child_by_field_name("key"),
                            entry.child_by_field_name("value"),
                        )
                        if key is None or value is None:
                            continue
                        name = option_source(key).strip("\"'").lower()
                        binding = option_source(value).lower()
                        if binding in imports:
                            imports[name] = imports[binding]
                        elif value.type == "member_expression":
                            obj = value.child_by_field_name("object")
                            member = value.child_by_field_name("property")
                            namespace = (
                                imports.get(option_source(obj).lower() + ".*")
                                if obj is not None
                                else None
                            )
                            if namespace and member is not None:
                                imports[name] = (namespace[0], option_source(member))
                return
            for child in node.named_children:
                walk(child)

        walk(options.root_node)
    return {
        name: contract for name, contract in imports.items() if not name.endswith(".*")
    }


def rewrite_default_export(body: str, slots: list[str] | None = None) -> str | None:
    """Wrap the actual default object export, ignoring comments and string contents."""
    span = _export_object_span(body)
    if span is None:
        return None
    start, end = span
    return (
        body[:start]
        + "__define("
        + body[start:end]
        + (", " + json.dumps(slots) if slots is not None else "")
        + ")"
        + body[end:]
    )


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
    """Resolve expression references with lexical scopes from the TypeScript AST."""
    from teloce.javascript.tree_sitter_backend import parse_tree

    source = "(" + expr + ")"
    tree = parse_tree(source, "ts")
    if tree.root_node.has_error:
        source = expr
        tree = parse_tree(source, "ts")
    encoded = source.encode("utf-8")
    found: set[str] = set()

    def text(node):
        return encoded[node.start_byte : node.end_byte].decode("utf-8")

    def bindings(node):
        if node is None:
            return set()
        if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
            return {text(node)}
        if node.type in {
            "pair_pattern",
            "assignment_pattern",
            "required_parameter",
            "optional_parameter",
        }:
            target = (
                node.child_by_field_name("value")
                if node.type == "pair_pattern"
                else (
                    node.child_by_field_name("left")
                    or node.child_by_field_name("pattern")
                )
            )
            return bindings(target)
        if node.type in {"type_annotation", "property_identifier"}:
            return set()
        result = set()
        for child in node.named_children:
            result.update(bindings(child))
        return result

    functions = {
        "arrow_function",
        "function_expression",
        "function_declaration",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    }

    def visit_defaults(node, scope):
        if node is None:
            return
        if node.type in {
            "assignment_pattern",
            "required_parameter",
            "optional_parameter",
            "object_assignment_pattern",
        }:
            value = node.child_by_field_name("right") or node.child_by_field_name(
                "value"
            )
            if value is not None:
                visit(value, scope)
        for child in node.named_children:
            visit_defaults(child, scope)

    def visit(node, scope):
        if node.type in {"comment", "regex", "type_annotation"}:
            return
        if node.type in functions:
            scope = (
                scope
                | bindings(node.child_by_field_name("parameters"))
                | bindings(node.child_by_field_name("parameter"))
            )
            scope |= bindings(node.child_by_field_name("name"))
            visit_defaults(node.child_by_field_name("parameters"), scope)
            visit_defaults(node.child_by_field_name("parameter"), scope)
        if node.type in {
            "statement_block",
            "program",
            "for_statement",
            "for_in_statement",
            "catch_clause",
        }:
            scope = set(scope)
            scope.update(bindings(node.child_by_field_name("parameter")))
            for child in node.named_children:
                declarations = (
                    child.named_children
                    if child.type in {"lexical_declaration", "variable_declaration"}
                    else [child]
                )
                for declaration in declarations:
                    if declaration.type in {
                        "variable_declarator",
                        "function_declaration",
                        "class_declaration",
                    }:
                        scope.update(bindings(declaration.child_by_field_name("name")))
        if node.type in {"identifier", "shorthand_property_identifier"}:
            name = text(node)
            parent = node.parent
            # Declaration identifiers are not reads. Initializers still are.
            if (
                parent is not None
                and parent.type
                in {"variable_declarator", "function_declaration", "class_declaration"}
                and parent.child_by_field_name("name") == node
            ):
                return
            if name not in scope and name not in _GLOBALS and name not in _KEYWORDS:
                found.add(name)
        for child in node.named_children:
            if node.type in functions and child in {
                node.child_by_field_name("parameters"),
                node.child_by_field_name("parameter"),
                node.child_by_field_name("name"),
            }:
                continue
            visit(child, scope)

    visit(tree.root_node, set(locals_))
    return sorted(found)


def _raw_prefix(source: str, decoded_length: int) -> str:
    """Translate a decoded expression offset back through HTML entities."""
    index = consumed = 0
    while index < len(source) and consumed < decoded_length:
        entity = re.match(
            r"&(?:#[xX][0-9a-fA-F]+|#\d+|[A-Za-z][A-Za-z0-9]+);?", source[index:]
        )
        if entity and html.unescape(entity.group()) != entity.group():
            value = html.unescape(entity.group())
            if consumed + len(value) > decoded_length:
                break
            consumed += len(value)
            index += len(entity.group())
        else:
            consumed += 1
            index += 1
    return source[:index]


class _SlotNames(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        if tag == "slot":
            name = dict(attrs).get("name") or "default"
            if name not in self.names:
                self.names.append(name)

    handle_startendtag = handle_starttag


class _TemplateWalker(HTMLParser):
    """Emit one TypeScript statement per template expression, remembering where each came from."""

    def __init__(self, components: dict[str, str] | None = None) -> None:
        super().__init__(convert_charrefs=False)
        self.components = components or {}
        self.source = ""
        self.out: list[str] = []
        self.origins: list[tuple[tuple[int, int], str] | None] = []
        self._stack: list[tuple[str, bool, bool]] = []
        self._branches: list[list[str]] = [[]]
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
        if self.source and lead:
            offset = (
                sum(
                    len(row)
                    for row in self.source.splitlines(keepends=True)[: loc[0] - 1]
                )
                + loc[1]
            )
            lead = _raw_prefix(self.source[offset:], len(lead))
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
            r"^\s*(?:\(([^)]*)\)|([\w$]+))\s+(?:in|of)\s+(.+)$", value, re.DOTALL
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

    def _open_condition(self, expr: str, loc: tuple[int, int]) -> None:
        ids = free_identifiers(expr, self._locals())
        pattern = "{ " + ", ".join(ids) + " }" if ids else "{}"
        self._emit(f"(({pattern}: Ctx) => {{ if ({expr}) {{", (loc, expr))
        self._scopes.append(set(ids))

    def _close_condition(self) -> None:
        self._emit("} })(__ctx);", None)
        self._scopes.pop()

    def _start(
        self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool
    ) -> None:
        raw, (line, col) = self.get_starttag_text() or "", self.getpos()
        if self._stack and self._stack[-1][0] in self.components:
            name = dict(attrs).get("slot") or "default"
            self._emit(
                f"__checkSlot<typeof {self.components[self._stack[-1][0]]}>({json.dumps(name)});",
                ((line, col), raw),
            )
        opened = False
        conditional = False
        values = dict(attrs)
        chain = self._branches[-1]
        condition = None
        if "v-if" in values:
            condition = values["v-if"]
            self._branches[-1] = [condition] if condition else []
        elif "v-else-if" in values and chain:
            value = values["v-else-if"]
            condition = f"!({' || '.join(f'({part})' for part in chain)}) && ({value})"
            chain.append(value or "false")
        elif "v-else" in values and chain:
            condition = f"!({' || '.join(f'({part})' for part in chain)})"
            self._branches[-1] = []
        else:
            self._branches[-1] = []
        ordered = sorted(attrs, key=lambda a: 0 if a[0] == "v-for" else 1)
        # A condition must enclose all bindings and descendants, not just be
        # checked as an unrelated expression statement.
        ordered = sorted(
            ordered,
            key=lambda a: (
                0
                if a[0] == "v-for"
                else 1
                if a[0] in {"v-if", "v-else-if", "v-else"}
                else 2
            ),
        )
        for name, value in ordered:
            if name in {"v-if", "v-else-if", "v-else"} and condition:
                found = re.search(
                    re.escape(name) + r"\s*=\s*([\"'])", raw, re.IGNORECASE
                )
                loc = (
                    self._position(line, col, raw, found.end())
                    if found
                    else (line, col)
                )
                self._open_condition(condition, loc)
                conditional = True
                continue
            if value is None:
                continue
            found = re.search(re.escape(name) + r"\s*=\s*([\"'])", raw, re.IGNORECASE)
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
        if tag in self.components:
            self._component_props(tag, attrs, raw, line, col)
        elif tag == "component":
            selector = values.get(":is") or values.get("v-bind:is")
            if selector:
                self._component_props(tag, attrs, raw, line, col, selector=selector)
        if self_closing or tag in _VOID:
            if conditional:
                self._close_condition()
            if opened:
                self._close_loop()
        else:
            self._stack.append((tag, opened, conditional))
            self._branches.append([])

    def _component_props(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        raw: str,
        line: int,
        col: int,
        selector: str | None = None,
    ) -> None:
        # Keep the validation in the v-for scope opened by _start.
        fields, expressions = [], [selector] if selector else []
        passthrough = {"class", "style", "id", "key", "ref", "slot", "role", "tabindex"}
        for name, value in attrs:
            if selector and name in {":is", "v-bind:is", "is"}:
                continue
            found = re.search(
                r"(?<![\w:-])" + re.escape(name) + r"(?=\s|=|/?>)", raw, re.IGNORECASE
            )
            loc = (
                self._position(line, col, raw, found.start()) if found else (line, col)
            )
            if name.startswith(("@", "v-on:", "data-", "aria-")) or name in passthrough:
                continue
            if name == "v-bind" and value:
                fields.append((f"...({value})", (loc, value)))
                expressions.append(value)
            elif name.startswith((":", "v-bind:")):
                key = name[1:] if name.startswith(":") else name[7:]
                key = re.sub(r"-([a-z])", lambda match: match.group(1).upper(), key)
                if key in passthrough or key.startswith(("data-", "aria-")):
                    continue
                if value:
                    fields.append((f"{json.dumps(key)}: ({value})", (loc, value)))
                    expressions.append(value)
            elif not name.startswith("v-"):
                # Static attributes are strings; bare attributes are empty strings,
                # matching the runtime's getAttribute-based prop extraction.
                fields.append(
                    (
                        f"{json.dumps(re.sub(r'-([a-z])', lambda match: match.group(1).upper(), name))}: {json.dumps(value or '')}",
                        (loc, value or name),
                    )
                )
        ids = sorted(
            set().union(
                *(set(free_identifiers(expr, self._locals())) for expr in expressions)
            )
        )
        pattern = "{ " + ", ".join(ids) + " }" if ids else "{}"
        self._emit(f"(({pattern}: Ctx) => {{", ((line, col), raw))
        self._emit(
            f"__dynamic<typeof __component.__components>()({selector}, {{"
            if selector
            else f"__checkProps<typeof {self.components[tag]} extends {{ readonly __props: infer P }} ? P : Record<string, unknown>>({{",
            ((line, col), raw),
        )
        for prop_field, origin in fields:
            self._emit(prop_field + ",", origin)
        self._emit("});", ((line, col), raw))
        self._emit("})(__ctx);", ((line, col), raw))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, True)

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            name, opened, conditional = self._stack.pop()
            self._branches.pop()
            if conditional:
                self._close_condition()
            if opened:
                self._close_loop()
            if name == tag:
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._branches[-1] = []
            if self._stack and self._stack[-1][0] in self.components:
                self._emit(
                    f'__checkSlot<typeof {self.components[self._stack[-1][0]]}>("default");',
                    (self.getpos(), data),
                )
        line, col = self.getpos()
        for m in re.finditer(r"\{\{(.*?)\}\}", data, re.DOTALL):
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
        self.template_text: dict[str, str] = {}
        self.script_suffix: dict[str, int] = {}

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
        generated = set()
        for path in by_rel.values():
            if path.suffix in {".html", ".vel"}:
                script = _SCRIPT.search(path.read_text(encoding="utf-8"))
                if script and _export_object_span(script.group(2)) is not None:
                    generated.add(path.resolve())
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
            is_js = (
                re.search(
                    r"\blang\s*=\s*[\"'](?:ts|typescript)[\"']",
                    script.group(1),
                    re.IGNORECASE,
                )
                is None
            )
            slot_parser = _SlotNames()
            template_match = _TEMPLATE.search(text)
            if template_match:
                slot_parser.feed(template_match.group(1))
            wrapped = rewrite_default_export(body, slot_parser.names)
            prefix = "".join(
                "\n" if char == "\n" else " " * (len(char.encode("utf-16-le")) // 2)
                for char in text[: script.start(2)]
            )
            padded = prefix + (wrapped if wrapped is not None else body)
            from types import SimpleNamespace

            from teloce.compiler.generator import Generator
            from teloce.sfc.script import ScriptParser

            parsed = ScriptParser().parse(body, filename=str(path))
            imports = Generator(
                {"shared_runtime_import": "teloce-signals"}
            )._generate_signal_imports(SimpleNamespace(script=parsed))
            declarations = []
            for statement in imports:
                for binding in statement.split("{", 1)[1].split("}", 1)[0].split(","):
                    parts = binding.strip().split(" as ")
                    imported, local = parts[0], parts[-1]
                    declarations.append(
                        f"/** @type {{typeof __TeloceSignals.{imported}}} */ const {local} = /** @type {{any}} */ (null);"
                        if is_js
                        else f"declare const {local}: typeof __TeloceSignals.{imported};"
                    )
            padded += "\n" + "\n".join(declarations) + "\n"
            self.original_text[rel] = text
            script_path = rel + (".__script.js" if is_js else ".ts")
            self.script_suffix[script_path] = (
                (len(wrapped) - len(body) - 9) if wrapped is not None else 0
            )
            self.script_origins[script_path] = (
                rel,
                text,
                padded,
                len(prefix),
                script.start(2),
                _export_object_span(body),
            )
            sources.append(SourceFile(path=script_path, text=padded, origin_path=rel))
            if is_js:
                sources.append(
                    SourceFile(
                        path=rel + ".ts",
                        text=f'export {{ default }} from "./{path.name}.__script.js";\nexport * from "./{path.name}.__script.js";\n',
                    )
                )
            template = _TEMPLATE.search(text)
            if self.templates and wrapped is not None and template:
                sources.append(
                    self._template_source(
                        rel,
                        path.name,
                        text,
                        template,
                        _component_imports(body, path, generated),
                    )
                )
        return sources

    def _template_source(
        self,
        rel: str,
        filename: str,
        text: str,
        template: re.Match[str],
        components: dict[str, tuple[str, str]],
    ) -> Any:
        from pytscheck import SourceFile

        inner = template.group(1)
        first_line = text[: template.start(1)].count("\n") + 1
        first_col = template.start(1) - (text.rfind("\n", 0, template.start(1)) + 1)
        names = {tag: f"__child_{index}" for index, tag in enumerate(components)}
        walker = _TemplateWalker(names)
        walker.source = inner
        walker.feed(inner)
        walker.close()
        header = [
            f'import __component from "./{filename}.ts";',
            "type Ctx = typeof __component extends { readonly __ctx: infer X } ? X : never;",
            "declare const __ctx: Ctx;",
            "function __template() {",
        ]
        header[1:1] = [
            f"import {{ {exported} as {names[tag]} }} from {json.dumps(source)};"
            for tag, (source, exported) in components.items()
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
        self.template_text[path] = "\n".join(header + walker.out + ["}"]) + "\n"
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
                    suffix = self.script_suffix.get(
                        getattr(error, "origin_file", None) or error.file, 1
                    )
                    if offset >= end + 9 + suffix:
                        offset -= 9 + suffix
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
                generated_rows = self.template_text.get(error.file, "").splitlines()
                generated_row = (
                    generated_rows[error.line - 1]
                    if error.line <= len(generated_rows)
                    else ""
                )
                generated_column = len(
                    generated_row.encode("utf-16-le")[: (error.column - 1) * 2].decode(
                        "utf-16-le", errors="ignore"
                    )
                )
                start = generated_row.find(expr)
                exact = generated_column - start if start >= 0 else -1
                inside = re.search(
                    r"(?<![\w$])" + re.escape(named.group(1)) + r"(?![\w$])", expr
                )
                if inside:
                    before = expr[: exact if 0 <= exact < len(expr) else inside.start()]
                    original = self.original_text[rel]
                    source_offset = (
                        sum(
                            len(row)
                            for row in original.splitlines(keepends=True)[: line - 1]
                        )
                        + col
                    )
                    before = _raw_prefix(original[source_offset:], len(before))
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
    settings: dict[str, object] = {
        "allowImportingTsExtensions": True,
        "allowJs": True,
        "checkJs": True,
    }
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

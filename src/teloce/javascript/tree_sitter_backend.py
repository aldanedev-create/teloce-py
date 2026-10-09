"""Tree-sitter backend for source-aware JavaScript and TypeScript parsing.

The public Teloce parser API intentionally remains dependency-compatible with
older projects.  This module is the structural backend used when the
Tree-sitter wheels are installed.  It never evaluates source code and it keeps
all source offsets so callers can preserve the author's JavaScript exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from threading import local
from typing import Any

from .parser import (
    JavaScriptSyntaxError,
    JSNode,
    JSProgram,
    JSToken,
    tokenize_javascript,
)

try:  # The imports are optional for source checkouts and constrained installs.
    import tree_sitter_javascript as _javascript
    import tree_sitter_typescript as _typescript
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in minimal installations
    Language = Any  # type: ignore[assignment,misc]
    Parser = Any  # type: ignore[assignment,misc]
    _javascript = None
    _typescript = None
    TREE_SITTER_AVAILABLE = False


class TreeSitterUnavailable(ImportError):
    """Raised when the optional structural parser is not installed."""


@dataclass(frozen=True)
class TreeSitterProgram:
    """A parsed source file and its Tree-sitter tree."""

    source: str
    language: str
    tree: Any

    @property
    def root_node(self) -> Any:
        return self.tree.root_node


_LANGUAGE_ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "tsx": "tsx",
}

_KIND_MAP = {
    "program": "Program",
    "import_statement": "ImportDeclaration",
    "export_statement": "ExportDeclaration",
    "lexical_declaration": "VariableDeclaration",
    "variable_declaration": "VariableDeclaration",
    "variable_declarator": "VariableDeclarator",
    "function_declaration": "FunctionDeclaration",
    "generator_function_declaration": "FunctionDeclaration",
    "class_declaration": "ClassDeclaration",
    "return_statement": "ReturnStatement",
    "throw_statement": "ThrowStatement",
    "if_statement": "IfStatement",
    "for_statement": "ForStatement",
    "for_in_statement": "ForInStatement",
    "for_of_statement": "ForOfStatement",
    "while_statement": "WhileStatement",
    "do_statement": "DoWhileStatement",
    "switch_statement": "SwitchStatement",
    "try_statement": "TryStatement",
    "break_statement": "BreakStatement",
    "continue_statement": "ContinueStatement",
    "debugger_statement": "DebuggerStatement",
    "empty_statement": "EmptyStatement",
    "expression_statement": "ExpressionStatement",
    "statement_block": "BlockStatement",
    "object": "ObjectExpression",
    "array": "ArrayExpression",
    "pair": "Property",
    "method_definition": "MethodDefinition",
    "arrow_function": "ArrowFunctionExpression",
    "function": "FunctionExpression",
    "call_expression": "CallExpression",
    "new_expression": "NewExpression",
    "member_expression": "MemberExpression",
    "subscript_expression": "MemberExpression",
    "assignment_expression": "AssignmentExpression",
    "augmented_assignment_expression": "AssignmentExpression",
    "binary_expression": "BinaryExpression",
    "ternary_expression": "ConditionalExpression",
    "unary_expression": "UnaryExpression",
    "await_expression": "AwaitExpression",
    "yield_expression": "YieldExpression",
    "update_expression": "UpdateExpression",
    "spread_element": "SpreadElement",
    "rest_pattern": "RestElement",
    "identifier": "Identifier",
    "property_identifier": "Identifier",
    "shorthand_property_identifier_pattern": "Identifier",
    "shorthand_property_identifier": "Identifier",
    "formal_parameters": "FormalParameters",
    "arguments": "Arguments",
    "parenthesized_expression": "ParenthesizedExpression",
    "template_string": "TemplateLiteral",
    "template_substitution": "TemplateSubstitution",
    "string": "Literal",
    "number": "Literal",
    "regex": "Literal",
    "true": "Literal",
    "false": "Literal",
    "null": "Literal",
    "undefined": "Identifier",
}

_IGNORED_TOP_LEVEL = {"hash_bang_line", "comment"}


def is_available() -> bool:
    """Return whether the Tree-sitter parser and grammars can be imported."""

    return TREE_SITTER_AVAILABLE


def _canonical_language(language: str) -> str:
    value = str(language or "js").strip().lower()
    try:
        return _LANGUAGE_ALIASES[value]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported JavaScript language {language!r}; use js, jsx, ts, or tsx"
        ) from exc


@lru_cache(maxsize=3)
def _language(language: str) -> Any:
    if not TREE_SITTER_AVAILABLE:
        raise TreeSitterUnavailable(
            "Tree-sitter is unavailable; install tree-sitter, "
            "tree-sitter-javascript, and tree-sitter-typescript"
        )
    canonical = _canonical_language(language)
    if canonical == "javascript":
        return Language(_javascript.language())
    if canonical == "typescript":
        return Language(_typescript.language_typescript())
    return Language(_typescript.language_tsx())


_parser_state = local()


def parse_tree(source: str, language: str = "js") -> TreeSitterProgram:
    """Parse JavaScript/TypeScript without executing it."""

    canonical = _canonical_language(language)
    parsers = getattr(_parser_state, "parsers", None)
    if parsers is None:
        parsers = _parser_state.parsers = {}
    parser = parsers.get(canonical)
    if parser is None:
        parser = parsers[canonical] = Parser(_language(canonical))
    source = str(source)
    encoded = source.encode("utf-8")
    trees = getattr(_parser_state, "trees", None)
    if trees is None:
        trees = _parser_state.trees = OrderedDict()
        _parser_state.tree_bytes = 0
    key = (canonical, source)
    tree = trees.get(key)
    if tree is None:
        tree = parser.parse(encoded)
        # Bound both count and retained source size. Large modules are parsed
        # normally without retaining their trees in a long-running watcher.
        if len(encoded) <= 131072:
            trees[key] = tree
            _parser_state.tree_bytes += len(encoded)
            while len(trees) > 32 or _parser_state.tree_bytes > 1048576:
                old_key, _ = trees.popitem(last=False)
                _parser_state.tree_bytes -= len(old_key[1].encode("utf-8"))
    else:
        trees.move_to_end(key)
    # Tree.edit() is public: callers receive their own tree so edits cannot
    # corrupt cached analysis used by another compiler stage.
    tree = tree.copy()
    return TreeSitterProgram(str(source), canonical, tree)


def _byte_to_char(source: str, byte_offset: int) -> int:
    """Convert Tree-sitter's UTF-8 byte offset to a Python string offset."""

    encoded = source.encode("utf-8")
    return len(encoded[:byte_offset].decode("utf-8", errors="ignore"))


def _point_to_line_column(source: str, point: tuple[int, int]) -> tuple[int, int]:
    row, byte_column = point
    lines = source.splitlines(keepends=True)
    line = lines[row] if 0 <= row < len(lines) else ""
    column = len(line.encode("utf-8")[:byte_column].decode("utf-8", errors="ignore"))
    return row + 1, column + 1


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _first_error(program: TreeSitterProgram) -> Any | None:
    if not program.root_node.has_error:
        return None
    for node in _walk(program.root_node):
        if node.type == "ERROR" or getattr(node, "is_missing", False):
            return node
    return program.root_node


def _unclosed_delimiter_token(source: str) -> JSToken | None:
    """Return the innermost opener left unmatched by the authored source.

    Tree-sitter reports some truncated files as one root ``ERROR`` node rather
    than inserting a missing closing token. The lexical pass is used only to
    improve that diagnostic; it never decides whether valid JavaScript is
    accepted. Strings, comments, and regular-expression literals are already
    handled as opaque tokens by Teloce's lexer.
    """
    pairs = {"{": "}", "[": "]", "(": ")"}
    closers = set(pairs.values())
    stack: list[tuple[str, JSToken]] = []
    try:
        tokens = tokenize_javascript(source)
    except JavaScriptSyntaxError:
        return None
    for token in tokens:
        if token.value in pairs:
            stack.append((pairs[token.value], token))
        elif token.value in closers:
            if not stack or stack[-1][0] != token.value:
                return None
            stack.pop()
    return stack[-1][1] if stack else None


def _error_for(program: TreeSitterProgram, node: Any) -> JavaScriptSyntaxError:
    opener = _unclosed_delimiter_token(program.source)
    if opener is not None:
        return JavaScriptSyntaxError(
            f"Unclosed delimiter {opener.value!r}",
            opener,
            f"Close the {opener.value!r} delimiter before the end of the file.",
        )
    start = _byte_to_char(program.source, node.start_byte)
    end = max(start + 1, _byte_to_char(program.source, node.end_byte))
    line, column = _point_to_line_column(program.source, node.start_point)
    value = program.source[start:end] or str(getattr(node, "type", "syntax error"))
    token = JSToken("error", value, start, end, line, column)
    if getattr(node, "is_missing", False):
        suggestion = f"Add the missing {node.type!r} token."
        message = f"Missing JavaScript token {node.type!r}"
    else:
        suggestion = (
            "Check the syntax immediately before this location and the expected "
            "matching delimiter."
        )
        message = f"Invalid {program.language} syntax near {value!r}"
    return JavaScriptSyntaxError(message, token, suggestion)


def validate_tree(program: TreeSitterProgram) -> TreeSitterProgram:
    """Raise a source-located Teloce error if the tree contains syntax errors."""

    error = _first_error(program)
    if error is not None:
        raise _error_for(program, error)
    return program


def parse_valid_tree(source: str, language: str = "js") -> TreeSitterProgram:
    """Parse and validate a source file."""

    return validate_tree(parse_tree(source, language))


def _node_name(node: Any, source: str) -> str | None:
    if node.type in {"identifier", "property_identifier"}:
        return source[
            _byte_to_char(source, node.start_byte):
            _byte_to_char(source, node.end_byte)
        ]
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return source[
            _byte_to_char(source, name_node.start_byte):
            _byte_to_char(source, name_node.end_byte)
        ]
    if node.type in {"lexical_declaration", "variable_declaration"}:
        for child in _walk(node):
            if child is node:
                continue
            if child.type in {"identifier", "property_identifier"}:
                return source[
                    _byte_to_char(source, child.start_byte):
                    _byte_to_char(source, child.end_byte)
                ]
    return None


def _convert_node(node: Any, source: str) -> JSNode:
    start = _byte_to_char(source, node.start_byte)
    end = _byte_to_char(source, node.end_byte)
    line, column = _point_to_line_column(source, node.start_point)
    kind = _KIND_MAP.get(node.type, node.type)
    named_children = list(node.named_children)
    # Preserve the stable Teloce AST shape for the nodes that existing
    # generator/editor consumers inspect. Tree-sitter exposes a declarator's
    # name and initializer as siblings; Teloce's historical AST stores the
    # initializer as the declarator's only child.
    if node.type in {"variable_declarator"}:
        value_node = node.child_by_field_name("value")
        named_children = [value_node] if value_node is not None else []
    elif node.type in {"function_declaration", "generator_function_declaration", "function"}:
        body_node = node.child_by_field_name("body")
        named_children = [body_node] if body_node is not None else []
    children = tuple(_convert_node(child, source) for child in named_children if child is not None)
    return JSNode(kind, source[start:end], start, end, line, column, children, _node_name(node, source))


def to_teloce_program(program: TreeSitterProgram) -> JSProgram:
    """Convert a validated Tree-sitter tree into Teloce's stable AST shape."""

    body = tuple(
        _convert_node(node, program.source)
        for node in program.root_node.named_children
        if node.type not in _IGNORED_TOP_LEVEL
    )
    return JSProgram(program.source, body)


def parse_as_teloce_program(source: str, language: str = "js") -> JSProgram:
    """Parse source with Tree-sitter and return Teloce's source AST."""

    return to_teloce_program(parse_valid_tree(source, language))


def default_export_object_source(source: str, language: str = "js") -> str | None:
    """Return the object literal in ``export default {}`` safely.

    This handles both a direct object export and a single-call wrapper such as
    ``defineComponent({ ... })``.  It uses AST field spans rather than regular
    expressions, so strings, comments, nested objects, and template literals
    cannot terminate the object early.
    """

    program = parse_valid_tree(source, language)
    for statement in program.root_node.named_children:
        if statement.type != "export_statement":
            continue
        value = statement.child_by_field_name("value")
        if value is None:
            continue
        if value.type == "object":
            return source[
                _byte_to_char(source, value.start_byte):
                _byte_to_char(source, value.end_byte)
            ]
        if value.type == "call_expression":
            arguments = value.child_by_field_name("arguments")
            if arguments is not None:
                for child in arguments.named_children:
                    if child.type == "object":
                        return source[
                            _byte_to_char(source, child.start_byte):
                            _byte_to_char(source, child.end_byte)
                        ]
    return None

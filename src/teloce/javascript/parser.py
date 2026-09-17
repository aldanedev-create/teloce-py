"""Compatibility JavaScript lexical and top-level syntax parser.

The public token and AST classes remain dependency-free compatibility types.
The exported ``parse_javascript`` and ``parse_javascript_language`` functions
prefer the Tree-sitter backend when it is installed, while the legacy lexer
and parsers remain available as an explicit fallback. Neither backend
executes JavaScript or attempts to be a formatter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class JSToken:
    kind: str
    value: str
    start: int
    end: int
    line: int
    column: int


class JavaScriptSyntaxError(ValueError):
    """Raised when JavaScript cannot be tokenized safely."""

    def __init__(self, message: str, token: Optional[JSToken] = None,
                 suggestion: Optional[str] = None):
        self.token = token
        self.suggestion = suggestion
        location = ""
        if token:
            location = f" at line {token.line}, column {token.column}"
        hint = f". {suggestion}" if suggestion else ""
        super().__init__(message + location + hint)


@dataclass(frozen=True)
class JSNode:
    """A source-preserving JavaScript syntax node."""

    kind: str
    source: str
    start: int
    end: int
    line: int
    column: int
    # The original five fields remain the stable construction API. These
    # optional fields expose useful syntax structure to diagnostics, editor
    # tooling, and future transforms without altering emitted source.
    children: tuple["JSNode", ...] = ()
    name: Optional[str] = None


@dataclass(frozen=True)
class JSProgram:
    source: str
    body: tuple[JSNode, ...]


class JavaScriptParser:
    """Parse top-level JavaScript structure without executing it.

    Teloce needs reliable module boundaries before it needs a full optimizing
    JavaScript compiler. This parser validates delimiter nesting and exposes
    source-preserving import/export nodes; nested JavaScript remains intact for
    the browser to execute.
    """

    def __init__(self, source: str):
        self.source = source
        self.tokens = JavaScriptLexer(source).tokenize()

    def parse(self) -> JSProgram:
        stack: list[JSToken] = []
        body: list[JSNode] = []
        start_token: Optional[JSToken] = None
        delimiters = {"{": "}", "[": "]", "(": ")"}
        closing = set(delimiters.values())
        previous: Optional[JSToken] = None
        for index, token in enumerate(self.tokens):
            if token.kind == "eof":
                break
            # Import/export declarations have an automatic-semicolon-insertion
            # boundary at a new line.  Recognising this narrow boundary keeps
            # SFC module discovery correct for idiomatic semicolon-free JS
            # without pretending this module is a complete ECMAScript parser.
            next_token = self.tokens[index + 1] if index + 1 < len(self.tokens) else None
            if (
                start_token is not None
                and not stack
                and previous is not None
                and token.line > previous.line
                and (
                    token.value in {"import", "export", "const", "let", "var", "function", "class"}
                    or (
                        previous.value == "}"
                        and start_token.value in {"function", "class", "export"}
                        and token.value not in {";", ",", ".", ")", "]", "}", "?", ":"}
                    )
                )
                and not (next_token and next_token.value == "(")
                and previous.value not in {
                    "=", "=>", "+", "-", "*", "/", "%", "&&", "||", "??", "?", ":", ",", ".",
                }
            ):
                body.append(self._node(start_token, previous))
                start_token = token
            if start_token is None:
                start_token = token
            if token.value in delimiters:
                stack.append(token)
            elif token.value in closing:
                if not stack or delimiters[stack[-1].value] != token.value:
                    raise JavaScriptSyntaxError(f"Unexpected closing delimiter {token.value!r}", token)
                stack.pop()
            if not stack and token.value == ";" and start_token:
                body.append(self._node(start_token, token))
                start_token = None
            previous = token
        if stack:
            opener = stack[-1]
            raise JavaScriptSyntaxError(f"Unclosed delimiter {opener.value!r}", opener)
        if start_token:
            body.append(self._node(start_token, self.tokens[-1]))
        return JSProgram(self.source, tuple(body))

    def _node(self, first: JSToken, last: JSToken) -> JSNode:
        text = self.source[first.start:last.end]
        stripped = text.lstrip()
        kind = "Statement"
        name: Optional[str] = None
        if re.match(r"import(?:\s|\{)", stripped) and not re.match(r"import\s*\(", stripped):
            kind = "ImportDeclaration"
        elif re.match(r"export\b", stripped):
            kind = "ExportDeclaration"
            declaration = re.match(
                r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)",
                stripped,
            )
            name = declaration.group(1) if declaration else None
        elif re.match(r"(?:async\s+)?function\s+[A-Za-z_$][\w$]*", stripped):
            kind = "FunctionDeclaration"
            match = re.match(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", stripped)
            name = match.group(1) if match else None
        elif re.match(r"class\s+[A-Za-z_$][\w$]*", stripped):
            kind = "ClassDeclaration"
            match = re.match(r"class\s+([A-Za-z_$][\w$]*)", stripped)
            name = match.group(1) if match else None
        elif re.match(r"(?:const|let|var)\b", stripped):
            kind = "VariableDeclaration"
            match = re.match(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)", stripped)
            name = match.group(1) if match else None
        elif re.match(r"return(?:\s|;|$)", stripped):
            kind = "ReturnStatement"
        elif stripped.startswith("{") and stripped.rstrip().endswith("}"):
            kind = "BlockStatement"
        elif stripped:
            kind = "ExpressionStatement"
        return JSNode(kind, text, first.start, last.end, first.line, first.column, name=name)


class JavaScriptLanguageParser:
    """Small, source-preserving recursive-descent JavaScript parser.

    This parser is intentionally an analysis AST, not an evaluator or code
    generator. It covers the language constructs Teloce needs for diagnostics
    and syntax-aware tooling while retaining every original source slice.
    Unknown statements are represented as ``ExpressionStatement`` nodes rather
    than rewritten. Applications needing proposal-specific transforms should
    still hand emitted modules to a dedicated JavaScript tool such as esbuild.
    """

    _BINARY_PRECEDENCE = {
        "=": 1, "+=": 1, "-=": 1, "*=": 1, "/=": 1, "??=": 1,
        "||": 2, "??": 2, "&&": 3, "|": 4, "^": 5, "&": 6,
        "==": 7, "!=": 7, "===": 7, "!==": 7,
        "<": 8, ">": 8, "<=": 8, ">=": 8, "in": 8, "instanceof": 8,
        "<<": 9, ">>": 9, ">>>": 9,
        "+": 10, "-": 10, "*": 11, "/": 11, "%": 11, "**": 12,
    }
    _UNARY = {"!", "~", "+", "-", "typeof", "void", "delete", "await", "yield"}
    _STATEMENT_STARTERS = {"const", "let", "var", "function", "class", "return", "throw", "if", "for", "while", "do", "try", "switch", "break", "continue", "debugger", "import", "export"}

    def __init__(self, source: str):
        self.source = source
        self.tokens = JavaScriptLexer(source).tokenize()
        self.cursor = 0

    @property
    def current(self) -> JSToken:
        return self.tokens[self.cursor]

    def _peek(self, offset: int = 1) -> JSToken:
        index = min(self.cursor + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def _take(self, value: Optional[str] = None) -> JSToken:
        token = self.current
        if value is not None and token.value != value:
            raise JavaScriptSyntaxError(f"Expected {value!r}, found {token.value!r}", token)
        self.cursor += 1
        return token

    def _node(self, kind: str, first: JSToken, last: JSToken,
              children: tuple[JSNode, ...] = (), name: Optional[str] = None) -> JSNode:
        return JSNode(kind, self.source[first.start:last.end], first.start, last.end,
                      first.line, first.column, children, name)

    def parse(self) -> JSProgram:
        body: list[JSNode] = []
        while self.current.kind != "eof":
            body.append(self._parse_statement())
        return JSProgram(self.source, tuple(body))

    def _parse_statement(self) -> JSNode:
        token = self.current
        if token.value == ";":
            return self._node("EmptyStatement", self._take(), token)
        if token.value == "{":
            return self._parse_block()
        if token.value in {"const", "let", "var"}:
            return self._parse_variable()
        if token.value == "function" or (token.value == "async" and self._peek().value == "function"):
            return self._parse_function()
        if token.value == "async" and self._peek().kind == "identifier":
            expression = self._parse_expression()
            last = self._finish_statement(self.tokens[self.cursor - 1])
            return self._node("ExpressionStatement", token, last, (expression,))
        if token.value == "class":
            return self._parse_class()
        if token.value in {"import", "export"}:
            return self._parse_module_declaration()
        if token.value in {"return", "throw"}:
            return self._parse_return_like()
        if token.value == "if":
            return self._parse_if()
        if token.value in {"for", "while"}:
            return self._parse_loop()
        if token.value == "do":
            first = self._take()
            child = self._parse_statement()
            if self.current.value == "while":
                self._take()
                self._consume_balanced("(")
                if self.current.value == ";":
                    last = self._take()
                else:
                    last = self.tokens[self.cursor - 1]
            else:
                last = self.tokens[self.cursor - 1]
            return self._node("DoWhileStatement", first, last, (child,))
        if token.value in {"break", "continue", "debugger"}:
            first = self._take()
            last = self._finish_statement(first)
            return self._node(f"{first.value.capitalize()}Statement", first, last)
        if token.value in {"try", "switch"}:
            return self._parse_compound_keyword()
        expression = self._parse_expression()
        last = self._finish_statement(self.tokens[self.cursor - 1])
        return self._node("ExpressionStatement", token, last, (expression,))

    def _parse_block(self) -> JSNode:
        first = self._take("{")
        children: list[JSNode] = []
        while self.current.kind != "eof" and self.current.value != "}":
            children.append(self._parse_statement())
        if self.current.kind == "eof":
            raise JavaScriptSyntaxError("Unclosed block", first)
        last = self._take("}")
        return self._node("BlockStatement", first, last, tuple(children))

    def _parse_variable(self) -> JSNode:
        first = self._take()
        declarators: list[JSNode] = []
        while self.current.kind != "eof":
            name_token = self._take()
            if name_token.kind not in {"identifier", "string"}:
                raise JavaScriptSyntaxError("Expected a variable name", name_token)
            children: list[JSNode] = []
            last = name_token
            if self.current.value == "=":
                self._take()
                value = self._parse_expression()
                children.append(value)
                last = self.tokens[self.cursor - 1]
            declarators.append(self._node("VariableDeclarator", name_token, last, tuple(children), name_token.value))
            if self.current.value != ",":
                break
            self._take(",")
        last = self._finish_statement(self.tokens[self.cursor - 1])
        return self._node("VariableDeclaration", first, last, tuple(declarators))

    def _parse_function(self) -> JSNode:
        first = self._take()
        if first.value == "async":
            self._take("function")
        elif first.value != "function":
            raise JavaScriptSyntaxError("Expected function declaration", first)
        if self.current.value == "*":
            self._take()
        name_token = self._take()
        if name_token.kind != "identifier":
            raise JavaScriptSyntaxError("Expected function name", name_token)
        self._consume_balanced("(")
        body = self._parse_block() if self.current.value == "{" else self._opaque_until_statement()
        return self._node("FunctionDeclaration", first, self.tokens[self.cursor - 1], (body,), name_token.value)

    def _parse_class(self) -> JSNode:
        first = self._take("class")
        name = None
        name_token = None
        if self.current.kind == "identifier":
            name_token = self._take()
            name = name_token.value
        while self.current.kind != "eof" and self.current.value != "{":
            self._take()
        if self.current.value != "{":
            raise JavaScriptSyntaxError("Expected class body", self.current)
        body = self._consume_balanced("{")
        return self._node("ClassDeclaration", first, self.tokens[self.cursor - 1], (body,), name)

    def _parse_module_declaration(self) -> JSNode:
        first = self._take()
        last = self._opaque_until_statement()
        kind = "ImportDeclaration" if first.value == "import" else "ExportDeclaration"
        return self._node(kind, first, last)

    def _parse_return_like(self) -> JSNode:
        first = self._take()
        children = ()
        if self.current.value not in {";", "}", ""} and self.current.line == first.line:
            children = (self._parse_expression(),)
        last = self._finish_statement(self.tokens[self.cursor - 1])
        return self._node("ReturnStatement" if first.value == "return" else "ThrowStatement", first, last, children)

    def _parse_if(self) -> JSNode:
        first = self._take("if")
        condition = self._consume_balanced("(")
        consequent = self._parse_statement()
        children = [condition, consequent]
        if self.current.value == "else":
            self._take()
            children.append(self._parse_statement())
        return self._node("IfStatement", first, self.tokens[self.cursor - 1], tuple(children))

    def _parse_loop(self) -> JSNode:
        first = self._take()
        condition = self._consume_balanced("(")
        body = self._parse_statement()
        return self._node("ForStatement" if first.value == "for" else "WhileStatement", first, self.tokens[self.cursor - 1], (condition, body))

    def _parse_compound_keyword(self) -> JSNode:
        first = self._take()
        children: list[JSNode] = []
        if self.current.value == "(" :
            children.append(self._consume_balanced("("))
        if self.current.value == "{" :
            children.append(self._parse_block())
        else:
            children.append(self._opaque_until_statement())
        return self._node(f"{first.value.capitalize()}Statement", first, self.tokens[self.cursor - 1], tuple(children))

    def _parse_expression(self, minimum: int = 0) -> JSNode:
        left = self._parse_unary()
        if minimum == 0 and self.current.value == "=>":
            self._take("=>")
            body = self._parse_block() if self.current.value == "{" else self._parse_expression()
            return self._node("ArrowFunctionExpression", self.tokens_by_offset(left.start), self.tokens[self.cursor - 1], (left, body))
        while self.current.kind != "eof":
            operator = self.current.value
            precedence = self._BINARY_PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                break
            self._take()
            right = self._parse_expression(precedence if operator == "**" else precedence + 1)
            kind = "AssignmentExpression" if precedence == 1 else "LogicalExpression" if operator in {"&&", "||", "??"} else "BinaryExpression"
            left = self._node(kind, self.tokens_by_offset(left.start), self.tokens[self.cursor - 1], (left, right))
        if minimum == 0 and self.current.value == "?":
            self._take()
            yes = self._parse_expression()
            if self.current.value == ":":
                self._take()
            no = self._parse_expression()
            left = self._node("ConditionalExpression", self.tokens_by_offset(left.start), self.tokens[self.cursor - 1], (left, yes, no))
        return left

    def _parse_unary(self) -> JSNode:
        if self.current.value in self._UNARY:
            first = self._take()
            child = self._parse_unary()
            return self._node("UnaryExpression", first, self.tokens[self.cursor - 1], (child,))
        return self._parse_postfix()

    def _parse_postfix(self) -> JSNode:
        node = self._parse_primary()
        while self.current.value in {".", "?.", "[", "(", "++", "--"}:
            first = self.tokens_by_offset(node.start)
            if self.current.value in {".", "?."}:
                self._take()
                property_token = self._take()
                property_node = self._node("Identifier", property_token, property_token, name=property_token.value)
                node = self._node("MemberExpression", first, property_token, (node, property_node))
            elif self.current.value == "[":
                property_node = self._consume_balanced("[")
                node = self._node("MemberExpression", first, self.tokens[self.cursor - 1], (node, property_node))
            elif self.current.value == "(":
                arguments = self._consume_balanced("(")
                node = self._node("CallExpression", first, self.tokens[self.cursor - 1], (node, arguments))
            else:
                update = self._take()
                node = self._node("UpdateExpression", first, update, (node,))
        return node

    def _parse_primary(self) -> JSNode:
        token = self.current
        if token.value == "new":
            first = self._take()
            target = self._parse_primary()
            target = self._parse_postfix_tail(target)
            return self._node("NewExpression", first, self.tokens[self.cursor - 1], (target,))
        if token.value == "...":
            first = self._take()
            argument = self._parse_expression(1)
            return self._node("SpreadElement", first, self.tokens[self.cursor - 1], (argument,))
        if token.value == "(":
            return self._consume_balanced("(")
        if token.value == "[":
            return self._consume_balanced("[")
        if token.value == "{":
            return self._consume_balanced("{")
        if token.kind in {"identifier", "string", "number", "regex", "template"}:
            self._take()
            kind = "Identifier" if token.kind == "identifier" else "Literal"
            return self._node(kind, token, token, name=token.value if kind == "Identifier" else None)
        raise JavaScriptSyntaxError(f"Unexpected token {token.value!r} in expression", token)

    def _parse_postfix_tail(self, node: JSNode) -> JSNode:
        """Parse member/call suffixes after a ``new`` target."""
        while self.current.value in {".", "?.", "[", "("}:
            first = self.tokens_by_offset(node.start)
            if self.current.value in {".", "?."}:
                self._take()
                property_token = self._take()
                property_node = self._node("Identifier", property_token, property_token, name=property_token.value)
                node = self._node("MemberExpression", first, property_token, (node, property_node))
            elif self.current.value == "[":
                property_node = self._consume_balanced("[")
                node = self._node("MemberExpression", first, self.tokens[self.cursor - 1], (node, property_node))
            else:
                arguments = self._consume_balanced("(")
                node = self._node("CallExpression", first, self.tokens[self.cursor - 1], (node, arguments))
        return node

    def _consume_balanced(self, opening: str) -> JSNode:
        pairs = {"(": ")", "[": "]", "{": "}"}
        closing = pairs[opening]
        first = self._take(opening)
        children: list[JSNode] = []
        stack = [opening]
        while self.current.kind != "eof" and stack:
            token = self.current
            if token.value in pairs:
                nested = self._consume_balanced(token.value)
                children.append(nested)
                continue
            if token.value in pairs.values():
                expected = pairs[stack[-1]]
                if token.value != expected:
                    raise JavaScriptSyntaxError(
                        f"Unexpected closing delimiter {token.value!r}; expected {expected!r}",
                        token, f"Add or remove the matching {expected!r} delimiter")
                stack.pop()
                last = self._take()
                if not stack:
                    return self._node({"(": "ParenthesizedExpression", "[": "ArrayExpression", "{": "ObjectExpression"}[opening], first, last, tuple(children))
                continue
            if token.value not in {",", ":", ";"}:
                try:
                    children.append(self._parse_expression())
                    continue
                except JavaScriptSyntaxError:
                    # Retain proposal-specific syntax as an opaque token, but
                    # never hide delimiter errors or consume the closing token.
                    if self.current.value in pairs.values():
                        raise
            self._take()
        raise JavaScriptSyntaxError(f"Unclosed delimiter {opening!r}", first)

    def _opaque_until_statement(self) -> JSToken:
        first = self.current
        depth = 0
        last = first
        while self.current.kind != "eof":
            # Module declarations have an ASI boundary before a new
            # declaration on the next line (``import x from 'x'\nexport``).
            # Check before consuming the next starter; checking afterwards
            # loses the starter and merges two declarations into one node.
            if (
                depth == 0
                and self.current.line > first.line
                and self.current.value in self._STATEMENT_STARTERS
            ):
                break
            token = self._take()
            last = token
            if token.value in {"(", "[", "{"}:
                depth += 1
            elif token.value in {")", "]", "}"
            }:
                depth = max(0, depth - 1)
            elif token.value == ";" and depth == 0:
                break
        return last

    def _finish_statement(self, fallback: JSToken) -> JSToken:
        if self.current.value == ";":
            return self._take()
        return fallback

    def tokens_by_offset(self, offset: int) -> JSToken:
        for token in self.tokens:
            if token.start == offset:
                return token
        return self.tokens[0]


class JavaScriptLexer:
    """Tokenize JavaScript without interpreting or executing it."""

    _PUNCTUATION = set("{}[]();,.:?")
    _OPERATORS = (
        "===", "!==", ">>>=", "**=", "&&=", "||=", "??=", "=>", "...",
        "==", "!=", ">=", "<=", "++", "--", "&&", "||", "??", "?.",
        "+=", "-=", "*=", "/=", "%=", "**", "<<", ">>", ">>>",
    )

    def __init__(self, source: str):
        self.source = source
        self.index = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[JSToken]:
        tokens: list[JSToken] = []
        while self.index < len(self.source):
            character = self.source[self.index]
            if self.index == 0 and self.source.startswith("#!"):
                self._skip_line_comment()
                continue
            if character.isspace():
                self._advance(character)
                continue
            if self.source.startswith("//", self.index):
                self._skip_line_comment()
                continue
            if self.source.startswith("/*", self.index):
                self._skip_block_comment()
                continue
            start, line, column = self.index, self.line, self.column
            if character in "'\"`":
                value = self._read_string(character)
                tokens.append(JSToken("template" if character == "`" else "string", value, start, self.index, line, column))
                continue
            if character == "/" and self._regex_can_start(tokens):
                value = self._read_regex()
                tokens.append(JSToken("regex", value, start, self.index, line, column))
                continue
            if character.isalpha() or character in "_$":
                value = self._read_identifier()
                tokens.append(JSToken("identifier", value, start, self.index, line, column))
                continue
            if character.isdigit() or (character == "." and self.index + 1 < len(self.source) and self.source[self.index + 1].isdigit()):
                value = self._read_number()
                tokens.append(JSToken("number", value, start, self.index, line, column))
                continue
            operator = next((item for item in self._OPERATORS if self.source.startswith(item, self.index)), None)
            if operator:
                for item in operator:
                    self._advance(item)
                tokens.append(JSToken("operator", operator, start, self.index, line, column))
                continue
            if character in self._PUNCTUATION or character in "+-*/%=!<>|&~^":
                self._advance(character)
                tokens.append(JSToken("punctuation" if character in self._PUNCTUATION else "operator", character, start, self.index, line, column))
                continue
            raise JavaScriptSyntaxError(f"Unexpected character {character!r}", JSToken("unknown", character, start, start + 1, line, column))
        tokens.append(JSToken("eof", "", len(self.source), len(self.source), self.line, self.column))
        return tokens

    @staticmethod
    def _regex_can_start(tokens: list[JSToken]) -> bool:
        """Use token context to distinguish a regex literal from division."""
        if not tokens:
            return True
        previous = tokens[-1]
        if previous.kind == "operator":
            return previous.value not in {"++", "--"}
        if previous.value in {"(", "[", "{", ",", ";", ":", "?", "="}:
            return True
        return previous.value in {
            "return", "throw", "case", "delete", "void", "typeof", "new",
            "in", "of", "else", "do", "yield", "await",
        }

    def _read_regex(self) -> str:
        """Read a JavaScript regex literal, including character classes."""
        start = self.index
        self._advance("/")
        in_class = False
        escaped = False
        while self.index < len(self.source):
            character = self.source[self.index]
            if character in "\r\n":
                raise JavaScriptSyntaxError("Unterminated regular expression literal")
            if escaped:
                escaped = False
                self._advance(character)
                continue
            if character == "\\":
                escaped = True
                self._advance(character)
                continue
            if character == "[":
                in_class = True
            elif character == "]":
                in_class = False
            elif character == "/" and not in_class:
                self._advance(character)
                while self.index < len(self.source) and (self.source[self.index].isalpha()):
                    self._advance(self.source[self.index])
                return self.source[start:self.index]
            self._advance(character)
        raise JavaScriptSyntaxError("Unterminated regular expression literal")

    def _advance(self, value: str) -> None:
        self.index += len(value)
        newlines = value.count("\n")
        if newlines:
            self.line += newlines
            self.column = len(value.rsplit("\n", 1)[-1]) + 1
        else:
            self.column += len(value)

    def _read_string(self, quote: str) -> str:
        start = self.index
        self._advance(quote)
        escaped = False
        while self.index < len(self.source):
            character = self.source[self.index]
            if escaped:
                escaped = False
                self._advance(character)
            elif character == "\\":
                escaped = True
                self._advance(character)
            elif character == quote:
                self._advance(character)
                return self.source[start:self.index]
            else:
                self._advance(character)
        raise JavaScriptSyntaxError(f"Unterminated {quote} literal")

    def _read_identifier(self) -> str:
        start = self.index
        while self.index < len(self.source) and (self.source[self.index].isalnum() or self.source[self.index] in "_$"):
            self._advance(self.source[self.index])
        return self.source[start:self.index]

    def _read_number(self) -> str:
        # Keep the complete ECMAScript numeric token together. In particular,
        # a sign in an exponent belongs to the literal, while a sign after a
        # completed literal is an operator.
        remaining = self.source[self.index:]
        match = re.match(
            r"(?:0[bB][01](?:_?[01])*|0[oO][0-7](?:_?[0-7])*|0[xX][0-9A-Fa-f](?:_?[0-9A-Fa-f])*|(?:\d(?:_?\d)*)?(?:\.(?:\d(?:_?\d)*)?)?(?:[eE][+-]?\d(?:_?\d)*)?)(?:n)?",
            remaining,
        )
        if not match or not match.group(0):
            raise JavaScriptSyntaxError("Invalid numeric literal", JSToken("number", remaining[:1], self.index, self.index + 1, self.line, self.column))
        value = match.group(0)
        # A bare dot is punctuation, not a number. The caller only enters this
        # method for a digit or a dot followed by a digit, but retain the guard
        # for direct future lexer extensions.
        if value == ".":
            raise JavaScriptSyntaxError("Invalid numeric literal")
        self._advance(value)
        return value

    def _skip_line_comment(self) -> None:
        while self.index < len(self.source) and self.source[self.index] != "\n":
            self._advance(self.source[self.index])

    def _skip_block_comment(self) -> None:
        self._advance("/*")
        while self.index < len(self.source) and not self.source.startswith("*/", self.index):
            self._advance(self.source[self.index])
        if self.index >= len(self.source):
            raise JavaScriptSyntaxError("Unterminated block comment")
        self._advance("*/")


def tokenize_javascript(source: str) -> list[JSToken]:
    """Return source-located JavaScript tokens."""
    return JavaScriptLexer(source).tokenize()


def parse_javascript(
    source: str,
    *,
    language: str = "js",
    backend: str = "auto",
) -> JSProgram:
    """Parse top-level JavaScript structure and return a source-located AST.

    Tree-sitter is the default structural backend when installed.  ``legacy``
    retains the dependency-free parser for constrained environments and for
    projects that explicitly need the historical behavior.
    """
    if backend not in {"auto", "tree-sitter", "legacy"}:
        raise ValueError("backend must be 'auto', 'tree-sitter', or 'legacy'")
    if backend != "legacy":
        try:
            from .tree_sitter_backend import parse_as_teloce_program

            return parse_as_teloce_program(source, language)
        except ImportError:
            if backend == "tree-sitter":
                raise
    return JavaScriptParser(source).parse()


def parse_javascript_language(
    source: str,
    *,
    language: str = "js",
    backend: str = "auto",
) -> JSProgram:
    """Parse JavaScript into a source-preserving language-level AST."""
    if backend not in {"auto", "tree-sitter", "legacy"}:
        raise ValueError("backend must be 'auto', 'tree-sitter', or 'legacy'")
    if backend != "legacy":
        try:
            from .tree_sitter_backend import parse_as_teloce_program

            return parse_as_teloce_program(source, language)
        except ImportError:
            if backend == "tree-sitter":
                raise
    return JavaScriptLanguageParser(source).parse()

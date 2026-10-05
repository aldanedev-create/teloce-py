"""
Script parser for .vel components.

Parses the <script> section of a .vel file with full JavaScript/TypeScript
support including ES modules, exports, imports, and component options.
"""

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from teloce.javascript.parser import parse_javascript, tokenize_javascript
from teloce.javascript.ts_transpile import transpile as transpile_ts
from teloce.javascript.tree_sitter_backend import (
    TreeSitterUnavailable,
    default_export_object_source,
)
from teloce.project.extensions import normalize_source_extensions, source_extension_pattern
from teloce.sfc.component import ComponentScript


def _read_ts_balanced(source: str, opening: int, open_char: str = '{', close_char: str = '}') -> int:
    """Return the index after a balanced TS declaration block."""
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index + 1
    return -1


def _remove_typescript_declarations(source: str) -> str:
    """Remove balanced interface/type declarations without truncating them."""
    pattern = re.compile(r'(?m)^\s*(?:export\s+)?(?:interface|type)\s+[A-Za-z_$][\w$]*(?:\s+extends[^\{=]+)?')
    while True:
        match = pattern.search(source)
        if not match:
            return source
        start = match.start()
        cursor = match.end()
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor < len(source) and source[cursor] == '=':
            cursor += 1
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
        if cursor < len(source) and source[cursor] == '{':
            end = _read_ts_balanced(source, cursor)
            if end < 0:
                return source
            cursor = end
        else:
            semicolon = source.find(';', cursor)
            cursor = len(source) if semicolon < 0 else semicolon + 1
        source = source[:start] + source[cursor:]


def _transpile_simple_enums(source: str) -> str:
    """Lower simple TypeScript enums to browser JavaScript objects."""
    pattern = re.compile(r'(?m)^(\s*)(export\s+)?enum\s+([A-Za-z_$][\w$]*)\s*\{')
    cursor = 0
    output = []
    while True:
        match = pattern.search(source, cursor)
        if not match:
            output.append(source[cursor:])
            return ''.join(output)
        output.append(source[cursor:match.start()])
        end = _read_ts_balanced(source, match.end() - 1)
        if end < 0:
            output.append(source[match.start():])
            return ''.join(output)
        body = source[match.end():end - 1]
        members = []
        depth = 0
        quote = None
        start = 0
        for index, char in enumerate(body + ','):
            if quote:
                if char == quote and (index == 0 or body[index - 1] != '\\'):
                    quote = None
            elif char in "'\"`":
                quote = char
            elif char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
            elif char == ',' and depth == 0:
                members.append(body[start:index].strip())
                start = index + 1
        values = []
        next_number = 0
        for member in members:
            if not member:
                continue
            if '=' in member:
                name, value = member.split('=', 1)
                name, value = name.strip(), value.strip()
                values.append(f'{name}: {value}')
                if re.fullmatch(r'-?\d+', value):
                    next_number = int(value) + 1
            else:
                name = member.strip()
                values.append(f'{name}: {next_number}')
                next_number += 1
        exported = 'export ' if match.group(2) else ''
        output.append(f'{match.group(1)}{exported}const {match.group(3)} = {{' + ', '.join(values) + '};')
        cursor = end


def strip_typescript_annotations(source: str) -> str:
    """Remove common TS-only syntax while preserving JavaScript expressions."""
    # Type-only imports/declarations have no browser runtime representation.
    source = _transpile_simple_enums(_remove_typescript_declarations(source))
    source = re.sub(r'(?m)^\s*import\s+type\s+[^;]+;?\s*$', '', source)
    source = re.sub(r'(?m)(import\s*\{)\s*type\s+[A-Za-z_$][\w$]*(?:\s+as\s+[A-Za-z_$][\w$]*)?\s*,?', r'\1', source)
    source = re.sub(r'(?m)import\s*\{\s*\}\s*from\s*[\'\"][^\'\"]+[\'\"]\s*;?', '', source)
    source = re.sub(r'(?m)^\s*(?:export\s+)?type\s+[A-Za-z_$][\w$]*\s*=\s*[^;]+;\s*$', '', source)
    source = re.sub(r'\s+as\s+(?:const|readonly)\b', '', source)
    source = re.sub(r'([A-Za-z_$][\w$]*)\s*<[^>{};()]*>\s*(?=\()', r'\1', source)
    # Assertions such as ``value as User``.  Stop before expression syntax.
    source = re.sub(r'\s+as\s+[A-Za-z_$][\w$]*(?:\s*<[^;,)]+>)?(?:\[\])?(?=\s*[,;.)\]}])', '', source)
    # Parameter annotations and optional parameter markers.
    source = re.sub(r'([A-Za-z_$][\w$]*)\s*\?\s*:\s*[A-Za-z_$][\w$]*(?:\s*<[^>]*>)?(?:\[\])?(?:\s*\|\s*[A-Za-z_$][\w$]*)*', r'\1', source)
    source = re.sub(r'([A-Za-z_$][\w$]*)\s*:\s*[A-Za-z_$][\w$]*(?:\s*<[^>]*>)?(?:\[\])?(?:\s*\|\s*[A-Za-z_$][\w$]*)*(?=\s*[,)=])', r'\1', source)
    # Function return annotations: ``): Promise<T> {`` / ``): void =>``.
    source = re.sub(r'\)\s*:\s*[A-Za-z_$][\w$]*(?:\s*<[^>]*>)?(?:\[\])?(?:\s*\|\s*[A-Za-z_$][\w$]*)*(?=\s*[{=])', ')', source)
    source = re.sub(r'\)\s*:\s*\{[^{}]*\}\s*(?=\{)', ')', source)
    # Variable annotations in the common ``const value: Type =`` form.
    source = re.sub(r'([A-Za-z_$][\w$]*)\s*:\s*[A-Za-z_$][\w$]*(?:\[\])?(?=\s*=)', r'\1', source)
    return source


@dataclass
class ScriptImport:
    """Represents an import statement."""
    source: str
    names: List[str]
    is_default: bool = False
    is_namespace: bool = False
    alias: Optional[str] = None
    line: int = 0


@dataclass
class ScriptExport:
    """Represents an export statement."""
    name: str
    local_name: Optional[str] = None
    is_default: bool = False
    is_type: bool = False
    line: int = 0


@dataclass
class ScriptMethod:
    """Represents a method in the component."""
    name: str
    body: str
    params: List[str]
    is_async: bool = False
    line: int = 0


@dataclass
class ScriptComputed:
    """Represents a computed property in the component."""
    name: str
    body: str
    line: int = 0


@dataclass
class ScriptProp:
    """Represents a prop definition."""
    name: str
    type: Optional[str] = None
    required: bool = False
    default: Optional[str] = None
    validator: Optional[str] = None
    line: int = 0


@dataclass
class ScriptLifecycle:
    """Represents a lifecycle hook."""
    name: str
    body: str
    line: int = 0


class ScriptParser:
    """
    Parses the script section of a .vel component with full JavaScript support.
    """
    
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        self.options = options or {}
        self.source_extensions = normalize_source_extensions(
            self.options.get("source_extensions"),
            html_mode=bool(self.options.get("html_mode", False)),
        )
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.imports: List[ScriptImport] = []
        self.exports: List[ScriptExport] = []
        self.components: Dict[str, str] = {}  # Component name -> import source
        self._method_params: Dict[str, str] = {}
        self._method_async: Dict[str, bool] = {}
        self._lifecycle_params: Dict[str, str] = {}
        self._lifecycle_async: Dict[str, bool] = {}
        self._watch_params: Dict[str, str] = {}
        self._watch_async: Dict[str, bool] = {}
    
    def parse(self, source: str, filename: str = "<input>") -> ComponentScript:
        """
        Parse the script section into a ComponentScript object.
        
        Args:
            source: The script source code
            filename: The source filename
            
        Returns:
            A ComponentScript object.
        """
        self.errors = []
        self.warnings = []
        self.imports = []
        self.exports = []
        self.components = {}
        self._method_params = {}
        self._method_async = {}
        self._lifecycle_params = {}
        self._lifecycle_async = {}
        self._watch_params = {}
        self._watch_async = {}
        
        original_source = source
        script_language = str(self.options.get("lang", "js")).lower()
        is_typescript = script_language in {"ts", "tsx", "typescript"}
        if is_typescript:
            try:
                source = transpile_ts(source, "<script lang=ts>")
            except Exception:
                # Constructs the tree-sitter path rejects (enum, etc.) keep using
                # the legacy lowering so existing components don't regress.
                source = strip_typescript_annotations(source)
        script = ComponentScript(raw=original_source)
        script.module_code = self._extract_module_code(source)
        
        if not source or not source.strip():
            self.warnings.append("Empty script section")
            return script
        
        try:
            # Validate the authored language before lowering TypeScript. The
            # generated JavaScript is validated separately below. Tree-sitter
            # provides structural syntax errors while the original source is
            # still available for accurate diagnostics.
            parse_javascript(original_source, language=script_language)
            if is_typescript:
                parse_javascript(source, language="js")
            # Parse imports
            self._parse_imports(source)
            script.imports = list(self.imports)
            
            # Parse exports
            self._parse_exports(source)

            # Component options must be read from the exported component
            # object, not from helper objects, strings, or functions elsewhere
            # in the module.
            option_source = self._extract_default_export_object(source) or source
            
            # Extract component options
            script.name = self._extract_component_name(option_source)
            script.data = self._extract_data(option_source)
            script.data_body = getattr(self, "_data_body", None)
            script.methods = self._extract_methods(option_source)
            script.method_params = dict(self._method_params)
            script.method_async = dict(self._method_async)
            script.computed = self._extract_computed(option_source)
            script.props = self._extract_props(option_source)
            script.lifecycle = self._extract_lifecycle(option_source)
            script.lifecycle_params = dict(self._lifecycle_params)
            script.lifecycle_async = dict(self._lifecycle_async)
            
            # Extract registered components
            self._extract_components(option_source)
            
            # Extract watch and other options
            script.watch = self._extract_watch(option_source)
            script.watch_params = dict(self._watch_params)
            script.watch_async = dict(self._watch_async)
            script.emits = self._extract_emits(option_source)
            script.query_state = self._scan_object_properties(option_source).get('queryState')
            
        except Exception as e:
            self.errors.append(f"Error parsing script: {str(e)}")
        
        return script

    def _extract_module_code(self, source: str) -> str:
        """Preserve executable module-level code around the component export."""
        code = source
        default_span = None
        try:
            for node in parse_javascript(code).body:
                if node.kind != "ExportDeclaration":
                    continue
                if re.match(r"export\s+default\b", node.source.strip()):
                    default_span = (node.start, node.end)
                    break
        except (TreeSitterUnavailable, ValueError):
            # Syntax diagnostics are emitted by ``parse`` below. Keep module
            # extraction non-throwing so malformed input returns a normal
            # compiler diagnostic rather than an internal pipeline failure.
            default_span = None
        if default_span is not None:
            start, end = default_span
            while end < len(code) and code[end] in ' ;\t\r\n':
                end += 1
            code = code[:start] + code[end:]
        # Local component imports are re-emitted with resolved build URLs by
        # the generator; package imports and ordinary module code remain.
        extensions = source_extension_pattern(self.source_extensions)
        code = re.sub(
            rf'(?m)^\s*import\s+(?:[^\n;]+)\s+from\s+[\'\"]([^\'\"]+{extensions})[\'\"]\s*;?\s*$',
            '', code,
        )
        code = re.sub(
            rf'(?m)^\s*import\s+[\'\"]([^\'\"]+{extensions})[\'\"]\s*;?\s*$',
            '', code,
        )
        return code.strip()

    @staticmethod
    def _matching_token_index(tokens: List[Any], opening: int) -> Optional[int]:
        """Return the token index closing a delimiter at ``opening``."""
        pairs = {'{': '}', '[': ']', '(': ')'}
        opener = tokens[opening].value if 0 <= opening < len(tokens) else None
        if opener not in pairs:
            return None
        stack: List[str] = []
        for index in range(opening, len(tokens)):
            value = tokens[index].value
            if value in pairs:
                stack.append(pairs[value])
            elif value in {'}', ']', ')'}:
                if not stack or stack[-1] != value:
                    return None
                stack.pop()
                if not stack:
                    return index
        return None

    def _extract_default_export_object(self, source: str) -> Optional[str]:
        """Return the object passed as the component's default export.

        Both ``export default { ... }`` and the common
        ``export default defineComponent({ ... })`` form are accepted.
        """
        # Prefer the structural parser. It cannot be confused by braces in a
        # string, regular expression, comment, or template literal. The
        # token-based path below remains as a compatibility fallback when a
        # project deliberately runs without the Tree-sitter wheels.
        try:
            parsed = default_export_object_source(source)
        except TreeSitterUnavailable:
            parsed = None
        if parsed is not None:
            return parsed

        tokens = tokenize_javascript(source)
        for index in range(len(tokens) - 2):
            if tokens[index].value != 'export' or tokens[index + 1].value != 'default':
                continue
            cursor = index + 2
            if tokens[cursor].value == '{':
                opening = cursor
            elif (
                tokens[cursor].kind == 'identifier'
                and cursor + 2 < len(tokens)
                and tokens[cursor + 1].value == '('
                and tokens[cursor + 2].value == '{'
            ):
                opening = cursor + 2
            else:
                return None
            closing = self._matching_token_index(tokens, opening)
            if closing is None:
                return None
            return source[tokens[opening].start:tokens[closing].end]
        return None

    def _scan_object_methods(
        self,
        source: str,
        allowed_names: Optional[Set[str]] = None,
    ) -> Dict[str, Tuple[str, str, bool]]:
        """Read direct method-valued properties from a JavaScript object.

        Supports shorthand methods, ``function`` properties, and block-bodied
        arrow functions while preserving parameters, async, nested bodies,
        regex literals, and template literals.
        """
        tokens = tokenize_javascript(source)
        methods: Dict[str, Tuple[str, str, bool]] = {}
        depth = 0
        index = 0
        while index < len(tokens) and tokens[index].kind != 'eof':
            token = tokens[index]
            if token.value == '{':
                depth += 1
                index += 1
                continue
            if token.value == '}':
                depth -= 1
                index += 1
                continue
            if depth != 1:
                index += 1
                continue

            is_async = False
            key_index = index
            if token.value == 'async':
                is_async = True
                key_index += 1
            if key_index >= len(tokens) or tokens[key_index].kind not in {'identifier', 'string'}:
                index += 1
                continue
            key_token = tokens[key_index]
            try:
                name = ast.literal_eval(key_token.value) if key_token.kind == 'string' else key_token.value
            except (ValueError, SyntaxError):
                index += 1
                continue
            if allowed_names is not None and name not in allowed_names:
                index += 1
                continue

            cursor = key_index + 1
            open_paren = None
            if cursor < len(tokens) and tokens[cursor].value == '(':
                open_paren = cursor
            elif cursor < len(tokens) and tokens[cursor].value == ':':
                cursor += 1
                if cursor < len(tokens) and tokens[cursor].value == 'async':
                    is_async = True
                    cursor += 1
                if cursor < len(tokens) and tokens[cursor].value == 'function':
                    cursor += 1
                    if cursor < len(tokens) and tokens[cursor].kind == 'identifier':
                        cursor += 1
                if cursor < len(tokens) and tokens[cursor].value == '(':
                    open_paren = cursor
            if open_paren is None:
                index += 1
                continue

            close_paren = self._matching_token_index(tokens, open_paren)
            if close_paren is None:
                index += 1
                continue
            cursor = close_paren + 1
            if cursor < len(tokens) and tokens[cursor].value == '=>':
                cursor += 1
            if cursor >= len(tokens) or tokens[cursor].value != '{':
                index += 1
                continue
            close_body = self._matching_token_index(tokens, cursor)
            if close_body is None:
                index += 1
                continue

            params = source[tokens[open_paren].end:tokens[close_paren].start].strip()
            body = source[tokens[cursor].end:tokens[close_body].start].strip()
            methods[str(name)] = (body, params, is_async)
            index = close_body + 1
        return methods

    def _scan_object_properties(self, source: str) -> Dict[str, str]:
        """Return direct ``name: value`` properties from an object literal."""
        tokens = tokenize_javascript(source)
        properties: Dict[str, str] = {}
        depth = 0
        index = 0
        while index < len(tokens) and tokens[index].kind != 'eof':
            token = tokens[index]
            if token.value == '{':
                depth += 1
                index += 1
                continue
            if token.value == '}':
                depth -= 1
                index += 1
                continue
            if not (
                depth == 1
                and token.kind in {'identifier', 'string'}
                and index + 1 < len(tokens)
                and tokens[index + 1].value == ':'
            ):
                index += 1
                continue
            try:
                name = ast.literal_eval(token.value) if token.kind == 'string' else token.value
            except (ValueError, SyntaxError):
                index += 1
                continue
            value_start = index + 2
            cursor = value_start
            stack: List[str] = []
            pairs = {'{': '}', '[': ']', '(': ')'}
            while cursor < len(tokens):
                value = tokens[cursor].value
                if value in pairs:
                    stack.append(pairs[value])
                elif value in {'}', ']', ')'}:
                    if stack and stack[-1] == value:
                        stack.pop()
                    elif not stack and value == '}':
                        break
                if not stack and value == ',':
                    break
                cursor += 1
            if value_start < cursor:
                properties[str(name)] = source[tokens[value_start].start:tokens[cursor - 1].end].strip()
            index = cursor + 1 if cursor < len(tokens) and tokens[cursor].value == ',' else cursor
        return properties
    
    def _parse_imports(self, source: str):
        """Parse imports from source-preserving AST nodes."""
        for node in parse_javascript(source).body:
            if node.kind != "ImportDeclaration":
                continue
            statement = node.source.strip().rstrip(";").strip()
            line = node.line
            side_effect = re.fullmatch(r'import\s*([\'"])(.*?)\1', statement, re.S)
            if side_effect:
                self.imports.append(ScriptImport(side_effect.group(2), [], line=line))
                continue
            match = re.fullmatch(r'import\s+(.+?)\s+from\s+([\'"])(.*?)\2', statement, re.S)
            if not match:
                raise ValueError(f"Invalid import declaration: {statement}")
            bindings, source_path = match.group(1).strip(), match.group(3)
            default_name = None
            if bindings.startswith("*"):
                namespace = re.fullmatch(r'\*\s+as\s+([A-Za-z_$][\w$]*)', bindings)
                if not namespace:
                    raise ValueError(f"Invalid namespace import: {statement}")
                self.imports.append(ScriptImport(source_path, ["*"], is_namespace=True, alias=namespace.group(1), line=line))
                continue
            if bindings.startswith("{"):
                named = bindings
            else:
                default_name, _, named = bindings.partition(",")
                default_name = default_name.strip()
                if not re.fullmatch(r'[A-Za-z_$][\w$]*', default_name):
                    raise ValueError(f"Invalid default import: {statement}")
                self.imports.append(ScriptImport(source_path, [default_name], is_default=True, line=line))
                if default_name[0].isupper():
                    self.components[default_name] = source_path
            if named.strip():
                if not (named.strip().startswith("{") and named.strip().endswith("}")):
                    raise ValueError(f"Invalid named import: {statement}")
                for part in named.strip()[1:-1].split(","):
                    part = part.strip()
                    if not part:
                        continue
                    pieces = re.split(r'\s+as\s+', part)
                    imported = pieces[0].strip()
                    alias = pieces[-1].strip() if len(pieces) > 1 else None
                    self.imports.append(ScriptImport(source_path, [imported], alias=alias, line=line))
    
    def _parse_exports(self, source: str):
        """Parse top-level export statements from the structural AST."""
        for node in parse_javascript(source).body:
            if node.kind != "ExportDeclaration":
                continue
            statement = node.source.strip().rstrip(";").strip()
            if re.match(r"export\s+default\b", statement):
                self.exports.append(ScriptExport("default", is_default=True, line=node.line))
                continue

            declaration = re.match(
                r"export\s+(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)",
                statement,
            )
            if declaration:
                self.exports.append(ScriptExport(declaration.group(1), line=node.line))
                continue

            export_list = re.match(r"export\s*\{([\s\S]*)\}(?:\s+from\s+['\"][^'\"]+['\"])?$", statement)
            if not export_list:
                continue
            for name_part in export_list.group(1).split(","):
                name_part = name_part.strip()
                if not name_part:
                    continue
                pieces = re.split(r"\s+as\s+", name_part, maxsplit=1)
                local_name = pieces[0].strip()
                exported_name = pieces[-1].strip()
                self.exports.append(
                    ScriptExport(
                        exported_name,
                        local_name=local_name if len(pieces) > 1 else None,
                        is_default=exported_name == "default",
                        line=node.line,
                    )
                )
    
    def _extract_component_name(self, source: str) -> Optional[str]:
        """Extract component name from the script."""
        name_value = self._scan_object_properties(source).get('name')
        if name_value:
            try:
                value = ast.literal_eval(name_value)
                if isinstance(value, str):
                    return value
            except (ValueError, SyntaxError):
                pass
        
        # Check for name in exported const
        const_pattern = r'export\s+const\s+(\w+)\s*=\s*{'
        match = re.search(const_pattern, source)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_data(self, source: str) -> Optional[str]:
        """Extract data function from the script."""
        self._data_body = None

        # Read the complete method body first.  The old fast path only
        # matched ``data() { return { ... } }`` and silently dropped data
        # functions that declared a local value before returning their
        # object.  That is valid, common JavaScript and produced a component
        # with no data at all.  The token-based scanner handles nested
        # objects, callbacks, strings, regexes, and compact formatting.
        method = self._scan_object_methods(source, allowed_names={"data"}).get("data")
        if method:
            body, _params, _is_async = method
            self._data_body = body.strip()
            body_tokens = tokenize_javascript(self._data_body)
            depth = 0
            for index, token in enumerate(body_tokens):
                if token.value in {"{", "[", "("}:
                    depth += 1
                    continue
                if token.value in {"}", "]", ")"}:
                    depth = max(0, depth - 1)
                    continue
                if token.value != "return" or depth != 0:
                    continue
                cursor = index + 1
                while cursor < len(body_tokens) and body_tokens[cursor].kind == "whitespace":
                    cursor += 1
                if cursor < len(body_tokens) and body_tokens[cursor].value == "(":
                    cursor += 1
                if cursor < len(body_tokens) and body_tokens[cursor].value == "{":
                    closing = self._matching_token_index(body_tokens, cursor)
                    if closing is not None:
                        return self._data_body[body_tokens[cursor].start:body_tokens[closing].end].strip()
            # A data method without a returned object is still preserved so
            # the generator can emit a useful function and the normal parser
            # diagnostics can explain any runtime result.
            return None

        # data() { return { ... } }
        match = re.search(r'data\s*\(\s*\)\s*{\s*return\s*{', source)
        if match:
            opening = source.find('{', match.start() + match.group(0).rfind('return'))
            value = self._read_balanced(source, opening)
            if value is not None:
                return value.strip()
        
        # data: () => ({ ... }) / data: () => ({ nested: { ... } })
        arrow_match = re.search(r'data\s*:\s*\(\)\s*=>\s*', source)
        if arrow_match:
            start = arrow_match.end()
            while start < len(source) and source[start].isspace():
                start += 1
            if start < len(source) and source[start] == '(':
                wrapped = self._read_balanced_pair(source, start, '(', ')')
                if wrapped:
                    value = wrapped[1:-1].strip()
                    if value.startswith('{'):
                        object_value = self._read_balanced_pair(value, 0, '{', '}')
                        if object_value:
                            return object_value.strip()
            elif start < len(source) and source[start] == '{':
                value = self._read_balanced_pair(source, start, '{', '}')
                if value:
                    return value.strip()
        
        return None

    def _read_balanced(self, source: str, opening: int) -> Optional[str]:
        """Read a balanced JavaScript brace expression."""
        return self._read_balanced_pair(source, opening, '{', '}')
    
    def _extract_methods(self, source: str) -> Dict[str, str]:
        """Extract methods from the script."""
        methods = {}
        self._method_params = {}
        self._method_async = {}
        
        # Find methods block
        methods_block = self._extract_block(source, 'methods')
        if methods_block:
            for name, (body, params, is_async) in self._scan_object_methods(methods_block).items():
                methods[name] = body
                self._method_params[name] = params
                self._method_async[name] = is_async
        
        # Also check for methods outside explicit block
        # This handles Vue 3 Composition API style
        function_pattern = r'(?:async\s+)?(\w+)\s*\(\s*([^)]*)\s*\)\s*{\s*([\s\S]*?)\s*}\s*,?'
        for match in re.finditer(function_pattern, source):
            # Skip if inside another block
            context = source[:match.start()]
            if self._is_inside_block(context, ['methods', 'computed', 'props', 'watch']):
                continue
            name = match.group(1)
            # Skip lifecycle hooks
            if name in ['data', 'computed', 'watch', 'beforeMount', 'mounted', 'beforeUpdate', 'updated', 
                        'beforeUnmount', 'unmounted', 'beforeCreate', 'created']:
                continue
            params = match.group(2).strip()
            body = match.group(3).strip()
            if name and body and name not in methods:
                methods[name] = body
                self._method_params[name] = params
                self._method_async[name] = match.group(0).lstrip().startswith("async ")
        
        return methods

    def _read_balanced_pair(self, source: str, opening: int, open_char: str, close_char: str) -> Optional[str]:
        """Read a balanced JS pair from source-located lexical tokens."""
        if opening < 0 or opening >= len(source) or source[opening] != open_char:
            return None
        depth = 0
        for token in tokenize_javascript(source[opening:]):
            if token.value == open_char:
                depth += 1
            elif token.value == close_char:
                depth -= 1
                if depth == 0:
                    return source[opening:opening + token.end]
        return None
    
    def _extract_computed(self, source: str) -> Dict[str, str]:
        """Extract computed properties from the script."""
        computed = {}
        
        # Find computed block
        computed_block = self._extract_block(source, 'computed')
        if computed_block:
            cursor = 0
            while cursor < len(computed_block):
                match = re.search(r'([A-Za-z_$][\w$]*)\s*\(\s*\)\s*\{', computed_block[cursor:])
                if not match:
                    break
                name = match.group(1)
                brace = cursor + match.end() - 1
                body_block = self._read_balanced_pair(computed_block, brace, '{', '}')
                if not body_block:
                    break
                body = body_block[1:-1].strip()
                if name and body:
                    computed[name] = body
                cursor = brace + len(body_block)
            
            # Arrow function computed: name: () => value
            arrow_pattern = r'(\w+)\s*:\s*\(\)\s*=>\s*([^,\n]+)\s*,?'
            for match in re.finditer(arrow_pattern, computed_block):
                name = match.group(1)
                body = f"return {match.group(2).strip()}"
                if name and body and name not in computed:
                    computed[name] = body
        
        # Check for getters in computed
        getter_pattern = r'(\w+)\s*:\s*{\s*get\s*\(\s*\)\s*{\s*([\s\S]*?)\s*}\s*}'
        for match in re.finditer(getter_pattern, source):
            name = match.group(1)
            body = match.group(2).strip()
            if name and body and name not in computed:
                computed[name] = body
        
        return computed
    
    def _extract_props(self, source: str) -> Dict[str, Dict[str, Any]]:
        """Extract props from the script."""
        props = {}
        
        # Find props block
        props_block = self._extract_block(source, 'props')
        if props_block:
            # Parse array props: ['prop1', 'prop2']
            array_match = re.search(r'\[\s*([\s\S]*?)\s*\]', props_block)
            if array_match:
                prop_names = re.findall(r'["\']([^"\']+)["\']', array_match.group(1))
                for name in prop_names:
                    props[name] = {'type': None, 'required': False, 'default': None}
            
            # Parse object props with token boundaries so factory defaults,
            # arrays, nested objects, and validators remain intact.
            if props_block.strip().startswith('{') and props_block.strip().endswith('}'):
                for name, value in self._scan_object_properties(props_block).items():
                    definition = {
                        'type': None,
                        'required': False,
                        'default': None,
                        'validator': None,
                    }
                    value = value.strip()
                    if re.fullmatch(r'[A-Za-z_$][\w$]*', value):
                        definition['type'] = value
                    elif value.startswith('{'):
                        fields = self._scan_object_properties(value)
                        type_value = fields.get('type', '').strip()
                        if type_value.startswith('[') and type_value.endswith(']'):
                            types = [item.strip() for item in type_value[1:-1].split(',') if item.strip()]
                            definition['type'] = '|'.join(types) or None
                        elif type_value:
                            definition['type'] = type_value
                        definition['required'] = fields.get('required', '').strip() == 'true'
                        if 'default' in fields:
                            definition['default'] = fields['default'].strip()
                        if 'validator' in fields:
                            definition['validator'] = fields['validator'].strip()
                    props[name] = definition
        
        return props
    
    def _parse_prop_definitions(self, prop_str: str) -> Dict[str, Dict[str, Any]]:
        """Parse prop definitions from a string."""
        props = {}
        i = 0
        while i < len(prop_str):
            # Skip whitespace
            while i < len(prop_str) and prop_str[i].isspace():
                i += 1
            
            if i >= len(prop_str):
                break
            
            # Read property name
            name_start = i
            while i < len(prop_str) and (prop_str[i].isalnum() or prop_str[i] in '_\'""'):
                i += 1
            name = prop_str[name_start:i].strip()
            name = name.strip("'\"")
            
            if not name:
                break
            
            # Skip to colon
            while i < len(prop_str) and prop_str[i] != ':':
                i += 1
            if i >= len(prop_str):
                break
            i += 1  # Skip ':'
            
            # Parse prop definition
            prop_def = self._parse_prop_definition(prop_str, i)
            if prop_def:
                props[name] = prop_def[0]
                i = prop_def[1]
            
            # Skip comma
            while i < len(prop_str) and prop_str[i] != ',':
                i += 1
            if i < len(prop_str) and prop_str[i] == ',':
                i += 1
        
        return props
    
    def _parse_prop_definition(self, prop_str: str, start: int) -> Tuple[Dict[str, Any], int]:
        """Parse a single prop definition."""
        i = start
        
        # Skip whitespace
        while i < len(prop_str) and prop_str[i].isspace():
            i += 1
        
        if i >= len(prop_str):
            return {}, i
        
        prop_def = {'type': None, 'required': False, 'default': None, 'validator': None}
        
        # Check if it's a type literal (String, Number, etc.)
        if i < len(prop_str) and prop_str[i].isalpha():
            type_start = i
            while i < len(prop_str) and (prop_str[i].isalnum() or prop_str[i] == '_'):
                i += 1
            type_name = prop_str[type_start:i]
            if type_name in ['String', 'Number', 'Boolean', 'Array', 'Object', 'Function', 'Symbol']:
                prop_def['type'] = type_name
                return prop_def, i
        
        # Check for object definition: { type: String, required: true }
        if i < len(prop_str) and prop_str[i] == '{':
            i += 1  # Skip '{'
            
            while i < len(prop_str):
                # Skip whitespace
                while i < len(prop_str) and prop_str[i].isspace():
                    i += 1
                
                if i >= len(prop_str) or prop_str[i] == '}':
                    break
                
                # Read key
                key_start = i
                while i < len(prop_str) and (prop_str[i].isalnum() or prop_str[i] == '_'):
                    i += 1
                key = prop_str[key_start:i]
                
                # Skip to colon
                while i < len(prop_str) and prop_str[i] != ':':
                    i += 1
                if i >= len(prop_str):
                    break
                i += 1  # Skip ':'
                
                # Skip whitespace
                while i < len(prop_str) and prop_str[i].isspace():
                    i += 1
                
                if i >= len(prop_str):
                    break
                
                # Parse value
                if key == 'type':
                    # Parse type
                    if prop_str[i] == '[':
                        # Array of types
                        i += 1
                        types = []
                        while i < len(prop_str) and prop_str[i] != ']':
                            type_start = i
                            while i < len(prop_str) and (prop_str[i].isalnum() or prop_str[i] == '_'):
                                i += 1
                            type_name = prop_str[type_start:i].strip()
                            if type_name:
                                types.append(type_name)
                            while i < len(prop_str) and prop_str[i] in ' ,':
                                i += 1
                        if i < len(prop_str) and prop_str[i] == ']':
                            i += 1
                        prop_def['type'] = '|'.join(types) if types else None
                    else:
                        type_start = i
                        while i < len(prop_str) and (prop_str[i].isalnum() or prop_str[i] == '_'):
                            i += 1
                        type_name = prop_str[type_start:i].strip()
                        if type_name:
                            prop_def['type'] = type_name
                elif key == 'required':
                    # Parse boolean
                    if prop_str[i:i+4] == 'true':
                        prop_def['required'] = True
                        i += 4
                    elif prop_str[i:i+5] == 'false':
                        prop_def['required'] = False
                        i += 5
                elif key == 'default':
                    # Parse default
                    default_start = i
                    if prop_str[i] == '(':
                        # Function default
                        i += 1
                        parens = 1
                        while i < len(prop_str) and parens > 0:
                            if prop_str[i] == '(':
                                parens += 1
                            elif prop_str[i] == ')':
                                parens -= 1
                            i += 1
                        prop_def['default'] = prop_str[default_start:i]
                    else:
                        while i < len(prop_str) and prop_str[i] not in '},':
                            i += 1
                        prop_def['default'] = prop_str[default_start:i].strip()
                elif key == 'validator':
                    # Preserve the complete function/arrow expression.
                    validator_start = i
                    depth = 0
                    quote = None
                    escaped = False
                    while i < len(prop_str):
                        char = prop_str[i]
                        if quote:
                            if escaped:
                                escaped = False
                            elif char == '\\':
                                escaped = True
                            elif char == quote:
                                quote = None
                        elif char in "'\"`":
                            quote = char
                        elif char in '([{':
                            depth += 1
                        elif char in ')]}':
                            if depth == 0:
                                break
                            depth -= 1
                        elif char == ',' and depth == 0:
                            break
                        i += 1
                    prop_def['validator'] = prop_str[validator_start:i].strip()
                
                # Skip to comma or end
                while i < len(prop_str) and prop_str[i] not in ',}':
                    i += 1
                if i < len(prop_str) and prop_str[i] == ',':
                    i += 1
            
            if i < len(prop_str) and prop_str[i] == '}':
                i += 1
        
        return prop_def, i
    
    def _extract_lifecycle(self, source: str) -> Dict[str, str]:
        """Extract lifecycle hooks from the script."""
        lifecycle = {}
        self._lifecycle_params = {}
        self._lifecycle_async = {}

        lifecycle_hooks = [
            'beforeMount', 'mounted', 'beforeUpdate', 'updated',
            'beforeUnmount', 'unmounted', 'beforeCreate', 'created',
            'activated', 'deactivated', 'errorCaptured'
        ]

        entries = self._scan_object_methods(source, set(lifecycle_hooks))
        for hook, (body, params, is_async) in entries.items():
            lifecycle[hook] = body
            self._lifecycle_params[hook] = params
            self._lifecycle_async[hook] = is_async

        return lifecycle
    
    def _extract_watch(self, source: str) -> Dict[str, str]:
        """Extract watch properties from the script."""
        watch = {}
        self._watch_params = {}
        self._watch_async = {}
        
        watch_block = self._extract_block(source, 'watch')
        if watch_block:
            for prop, (body, params, is_async) in self._scan_object_methods(watch_block).items():
                watch[prop] = body
                self._watch_params[prop] = params
                self._watch_async[prop] = is_async

            # Object-form watchers: ``value: { async handler(...) {}, deep: true }``.
            tokens = tokenize_javascript(watch_block)
            depth = 0
            index = 0
            while index < len(tokens) and tokens[index].kind != 'eof':
                token = tokens[index]
                if token.value == '{':
                    depth += 1
                elif token.value == '}':
                    depth -= 1
                elif (
                    depth == 1
                    and token.kind in {'identifier', 'string'}
                    and index + 2 < len(tokens)
                    and tokens[index + 1].value == ':'
                    and tokens[index + 2].value == '{'
                ):
                    closing = self._matching_token_index(tokens, index + 2)
                    if closing is not None:
                        try:
                            prop = ast.literal_eval(token.value) if token.kind == 'string' else token.value
                        except (ValueError, SyntaxError):
                            prop = None
                        nested = watch_block[tokens[index + 2].start:tokens[closing].end]
                        handlers = self._scan_object_methods(nested, {'handler'})
                        if prop is not None and 'handler' in handlers:
                            body, params, is_async = handlers['handler']
                            watch[str(prop)] = body
                            self._watch_params[str(prop)] = params
                            self._watch_async[str(prop)] = is_async
                        index = closing
                index += 1
        
        return watch
    
    def _extract_emits(self, source: str) -> List[str]:
        """Extract emits from the script."""
        emits = []
        
        # Find emits block
        emits_block = self._extract_block(source, 'emits')
        if emits_block:
            # Array emits: ['event1', 'event2']
            array_match = re.search(r'\[\s*([\s\S]*?)\s*\]', emits_block)
            if array_match:
                event_names = re.findall(r'["\']([^"\']+)["\']', array_match.group(1))
                emits.extend(event_names)
        
        return emits
    
    def _extract_components(self, source: str):
        """Extract component registrations from the script."""
        # Find components block
        comp_block = self._extract_block(source, 'components')
        if comp_block:
            # Parse component registrations
            comp_pattern = r'(\w+)\s*:\s*(\w+)'
            for match in re.finditer(comp_pattern, comp_block):
                local_name = match.group(1)
                import_name = match.group(2)
                # Check if the import is in our imports
                for imp in self.imports:
                    if import_name in imp.names or imp.alias == import_name:
                        self.components[local_name] = imp.source
                        break
    
    def _extract_block(self, source: str, block_name: str) -> Optional[str]:
        """Extract a named block from the source."""
        start_match = self._find_property(source, block_name)
        if start_match is None:
            return None

        start = start_match

        # Find the block content
        while start < len(source) and source[start].isspace():
            start += 1
        if start >= len(source):
            return None
        
        # Check if it's an object or array
        char = source[start]
        if char == '{':
            # Object block
            return self._extract_object_block(source, start)
        elif char == '[':
            # Array block
            return self._extract_array_block(source, start)
        
        return None

    @staticmethod
    def _find_property(source: str, name: str) -> Optional[int]:
        """Find a top-level-looking ``name:`` outside JS strings/comments.

        Option extraction is intentionally lightweight, but it must not let
        documentation strings such as ``"computed: { fake: true }"`` become
        component options. This scanner only identifies the property; the
        existing balanced readers still parse its value.
        """
        quote = None
        escaped = False
        line_comment = block_comment = False
        index = 0
        while index < len(source):
            char = source[index]
            nxt = source[index + 1] if index + 1 < len(source) else ""
            if line_comment:
                if char == "\n": line_comment = False
            elif block_comment:
                if char == "*" and nxt == "/": block_comment = False; index += 1
            elif quote:
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == quote: quote = None
            elif char in "'\"`": quote = char
            elif char == "/" and nxt == "/": line_comment = True; index += 1
            elif char == "/" and nxt == "*": block_comment = True; index += 1
            elif source.startswith(name, index):
                before = source[index - 1] if index else ""
                after_index = index + len(name)
                if (not (before.isalnum() or before in "_$") and
                        (after_index == len(source) or not (source[after_index].isalnum() or source[after_index] in "_$"))):
                    cursor = after_index
                    while cursor < len(source) and source[cursor].isspace(): cursor += 1
                    if cursor < len(source) and source[cursor] == ":":
                        return cursor + 1
            index += 1
        return None
    
    def _extract_object_block(self, source: str, start: int) -> Optional[str]:
        """Extract an object block from the source."""
        return self._read_balanced_pair(source, start, '{', '}')
    
    def _extract_array_block(self, source: str, start: int) -> Optional[str]:
        """Extract an array block from the source."""
        return self._read_balanced_pair(source, start, '[', ']')
    
    def _is_inside_block(self, context: str, block_names: List[str]) -> bool:
        """Check if we're inside a specific block."""
        for block in block_names:
            pattern = rf'{block}\s*:'
            match = re.search(pattern, context)
            if match:
                # Check if the block is closed
                block_start = match.end()
                if block_start < len(context):
                    # Find the matching closing brace
                    return True
        return False
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

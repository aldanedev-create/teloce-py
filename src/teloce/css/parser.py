"""
CSS Parser - parses CSS stylesheets.

Converts CSS source into an AST representation.
"""

from functools import lru_cache
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CSSDeclaration:
    """A CSS declaration (property: value)."""
    property: str
    value: str
    line: int = 0
    column: int = 0


@dataclass
class CSSRule:
    """A CSS rule with selector and declarations."""
    selector: str
    declarations: List[CSSDeclaration] = field(default_factory=list)
    line: int = 0
    column: int = 0
    
    def get_declaration(self, prop: str) -> Optional[str]:
        """Get a declaration value by property name."""
        for decl in self.declarations:
            if decl.property == prop:
                return decl.value
        return None
    
    def has_declaration(self, prop: str) -> bool:
        """Check if a declaration exists."""
        return self.get_declaration(prop) is not None


@dataclass
class CSSAtRule:
    """A CSS at-rule (@media, @keyframes, etc.)."""
    name: str
    value: str = ""
    rules: List[CSSRule] = field(default_factory=list)
    nested_at_rules: List['CSSAtRule'] = field(default_factory=list)
    declarations: List[CSSDeclaration] = field(default_factory=list)
    line: int = 0
    column: int = 0


@dataclass
class CSSStylesheet:
    """A complete CSS stylesheet."""
    rules: List[CSSRule] = field(default_factory=list)
    at_rules: List[CSSAtRule] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)



@lru_cache(maxsize=512)
def _parse_css_cached(source: str):
    parser = CSSParser()
    stylesheet = parser._parse_uncached(source)
    return stylesheet, tuple(parser.errors)


class CSSParser:
    """
    Parses CSS stylesheets into an AST.
    """
    
    def __init__(self):
        self.source: str = ""
        self.position: int = 0
        self.line: int = 1
        self.column: int = 1
        self.errors: List[str] = []
    
    def parse(self, source: str) -> CSSStylesheet:
        """
        Parse a CSS stylesheet.

        Results are memoized by source text: a component's CSS is parsed
        several times during one compile (style validation, generation, and
        scoping) and the resulting tree is treated as read-only everywhere.
        ``self.errors`` is populated exactly as an uncached parse would.
        """
        stylesheet, errors = _parse_css_cached(source)
        self.source = source
        self.position = len(source)
        self.errors = list(errors)
        return stylesheet

    def _parse_uncached(self, source: str) -> CSSStylesheet:
        """
        Parse a CSS stylesheet.
        
        Args:
            source: The CSS source code
            
        Returns:
            A CSSStylesheet object.
        """
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1
        self.errors = []
        
        stylesheet = CSSStylesheet()
        
        while self.position < len(self.source):
            self._skip_whitespace_and_comments()
            
            if self.position >= len(self.source):
                break
            
            if self._peek() == '@':
                at_rule = self._parse_at_rule()
                if at_rule:
                    if at_rule.name == 'media' or at_rule.name == 'supports':
                        stylesheet.at_rules.append(at_rule)
                    else:
                        # Simple at-rule like @import, @charset
                        stylesheet.at_rules.append(at_rule)
            else:
                rule = self._parse_rule()
                if rule:
                    stylesheet.rules.append(rule)
        
        return stylesheet
    
    def _parse_rule(self) -> Optional[CSSRule]:
        """Parse a CSS rule."""
        start_line = self.line
        start_col = self.column
        
        selector = self._read_selector()
        if not selector:
            return None
        
        self._skip_whitespace_and_comments()
        
        if self._peek() != '{':
            self.errors.append(f"Expected '{{' at line {self.line}")
            return None
        
        self._advance()  # Skip '{'
        
        declarations = []
        closed = False
        while self.position < len(self.source):
            self._skip_whitespace_and_comments()
            
            if self._peek() == '}':
                self._advance()
                closed = True
                break
            
            decl = self._parse_declaration()
            if decl:
                declarations.append(decl)
            
            self._skip_whitespace_and_comments()
            
            if self._peek() == ';':
                self._advance()
        
        if not closed:
            self.errors.append(f"Unclosed CSS rule starting at line {start_line}, column {start_col}")

        return CSSRule(
            selector=selector.strip(),
            declarations=declarations,
            line=start_line,
            column=start_col
        )
    
    def _parse_declaration(self) -> Optional[CSSDeclaration]:
        """Parse a CSS declaration."""
        start_line = self.line
        start_col = self.column
        
        prop = self._read_property()
        if not prop:
            return None
        
        self._skip_whitespace_and_comments()
        
        if self._peek() != ':':
            self.errors.append(f"Expected ':' at line {self.line}")
            return None
        
        self._advance()  # Skip ':'
        
        self._skip_whitespace_and_comments()
        
        value = self._read_value()
        if value is None:
            return None
        
        return CSSDeclaration(
            property=prop.strip(),
            value=value.strip(),
            line=start_line,
            column=start_col
        )
    
    def _parse_at_rule(self) -> Optional[CSSAtRule]:
        """Parse a CSS at-rule."""
        start_line = self.line
        start_col = self.column
        
        self._advance()  # Skip '@'
        
        name = self._read_identifier()
        if not name:
            return None
        
        self._skip_whitespace_and_comments()
        
        # Read until a top-level block or statement delimiter. Delimiters in
        # strings and functions (including data URLs) are part of the value.
        value = ""
        quote = ''
        escaped = False
        round_depth = square = 0
        while self.position < len(self.source):
            char = self._peek()
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif quote:
                if char == quote:
                    quote = ''
            elif char in ('"', "'"):
                quote = char
            elif char == '(':
                round_depth += 1
            elif char == ')':
                round_depth = max(0, round_depth - 1)
            elif char == '[':
                square += 1
            elif char == ']':
                square = max(0, square - 1)
            elif (char == '{' or char == ';') and round_depth == 0 and square == 0:
                break
            value += char
            self._advance()
        
        value = value.strip()
        
        # Check if it's a block at-rule (@media, @supports, etc.)
        if self._peek() == '{':
            self._advance()  # Skip '{'

            rules = []
            declarations = []
            nested_at_rules = []

            # These at-rules contain declarations rather than selector rules.
            # Treating their properties as selectors loses valid CSS such as
            # fonts and print-page configuration.
            declaration_block = name.lower() in {
                'font-face', 'page', 'counter-style', 'property',
                'font-feature-values', 'viewport', '-ms-viewport',
                'color-profile', 'font-palette-values',
            }

            if declaration_block:
                closed = False
                while self.position < len(self.source):
                    self._skip_whitespace_and_comments()
                    if self._peek() == '}':
                        self._advance()
                        closed = True
                        break
                    decl = self._parse_declaration()
                    if decl:
                        declarations.append(decl)
                    self._skip_whitespace_and_comments()
                    if self._peek() == ';':
                        self._advance()
                if not closed:
                    self.errors.append(f"Unclosed @{name} block starting at line {start_line}, column {start_col}")
                return CSSAtRule(
                    name=name,
                    value=value,
                    declarations=declarations,
                    line=start_line,
                    column=start_col,
                )
            
            closed = False
            while self.position < len(self.source):
                self._skip_whitespace_and_comments()
                
                if self._peek() == '}':
                    self._advance()
                    closed = True
                    break
                
                # Check for nested at-rule
                if self._peek() == '@':
                    nested = self._parse_at_rule()
                    if nested:
                        nested_at_rules.append(nested)
                    continue
                
                # Parse regular rule
                rule = self._parse_rule()
                if rule:
                    rules.append(rule)
            
            if not closed:
                self.errors.append(f"Unclosed @{name} block starting at line {start_line}, column {start_col}")
            return CSSAtRule(
                name=name,
                value=value,
                rules=rules,
                declarations=declarations,
                nested_at_rules=nested_at_rules,
                line=start_line,
                column=start_col
            )
        elif self._peek() == ';':
            self._advance()  # Skip ';'
            return CSSAtRule(
                name=name,
                value=value,
                line=start_line,
                column=start_col
            )
        
        return None
    
    def _read_selector(self) -> str:
        """Read a CSS selector."""
        start = self.position
        quote = ''
        escaped = False
        square = round_depth = 0
        while self.position < len(self.source):
            char = self._peek()
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif quote:
                if char == quote:
                    quote = ''
            elif char in ('"', "'"):
                quote = char
            elif char == '[':
                square += 1
            elif char == ']':
                square = max(0, square - 1)
            elif char == '(':
                round_depth += 1
            elif char == ')':
                round_depth = max(0, round_depth - 1)
            elif char == '{' and square == 0 and round_depth == 0:
                break
            self._advance()
        
        return self.source[start:self.position].strip()
    
    def _read_property(self) -> str:
        """Read a CSS property name."""
        start = self.position
        
        while self.position < len(self.source):
            char = self._peek()
            if char == ':' or char == ';' or char == '}':
                break
            self._advance()
        
        return self.source[start:self.position].strip()
    
    def _read_value(self) -> Optional[str]:
        """Read a CSS value."""
        start = self.position
        in_string = False
        string_char = None
        escape = False
        parens = 0
        
        while self.position < len(self.source):
            char = self._peek()
            
            if escape:
                escape = False
                self._advance()
                continue
            
            if char == '\\':
                escape = True
                self._advance()
                continue
            
            if in_string:
                if char == string_char:
                    in_string = False
                    string_char = None
                self._advance()
                continue
            
            if char in ('"', "'"):
                in_string = True
                string_char = char
                self._advance()
                continue
            
            if char == '(':
                parens += 1
                self._advance()
                continue
            
            if char == ')':
                parens -= 1
                self._advance()
                continue
            
            if char == ';' and parens == 0:
                break
            
            if char == '}' and parens == 0:
                break
            
            self._advance()
        
        value = self.source[start:self.position].strip()
        return value if value else None
    
    def _read_identifier(self) -> str:
        """Read an identifier."""
        start = self.position
        
        while self.position < len(self.source):
            char = self._peek()
            if not (char.isalnum() or char in '-_'):
                break
            self._advance()
        
        return self.source[start:self.position]
    
    def _skip_whitespace_and_comments(self):
        """Skip whitespace and comments."""
        while self.position < len(self.source):
            char = self._peek()
            
            if char.isspace():
                self._advance()
                continue
            
            if char == '/' and self._peek_offset(1) == '*':
                self._skip_block_comment()
                continue
            
            break
    
    def _skip_block_comment(self):
        """Skip a block comment /* ... */."""
        self._advance()  # Skip '/'
        self._advance()  # Skip '*'
        
        while self.position < len(self.source):
            if self._peek() == '*' and self._peek_offset(1) == '/':
                self._advance()
                self._advance()
                break
            self._advance()
    
    def _peek(self, offset: int = 0) -> str:
        """Peek at a character."""
        pos = self.position + offset
        if pos >= len(self.source):
            return ''
        return self.source[pos]
    
    def _peek_offset(self, offset: int = 1) -> str:
        """Peek ahead by offset."""
        return self._peek(offset)
    
    def _advance(self):
        """Advance to the next character."""
        if self.position < len(self.source):
            char = self.source[self.position]
            if char == '\n':
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.position += 1
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

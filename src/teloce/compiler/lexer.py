"""
Lexical analyzer for Teloce templates.

Converts template source code into tokens.
"""

from enum import Enum, auto
from typing import List, Optional, Any


class TokenType(Enum):
    """Token types for the lexer."""
    
    # HTML tokens
    OPEN_TAG = auto()
    CLOSE_TAG = auto()
    SELF_CLOSE_TAG = auto()
    TEXT = auto()
    COMMENT = auto()
    DOCTYPE = auto()
    
    # Teloce directives
    INTERPOLATION_START = auto()  # {{
    INTERPOLATION_END = auto()    # }}
    INTERPOLATION_EXPR = auto()   # expression text between {{ and }}
    FOR_START = auto()            # <for
    FOR_END = auto()              # </for>
    IF_START = auto()             # <if
    IF_END = auto()               # </if>
    ELSE = auto()                 # <else>
    ELSE_IF = auto()              # <else if>
    SHOW = auto()                 # :show
    HIDE = auto()                 # :hide
    
    # Event directives
    EVENT_CLICK = auto()          # @click
    EVENT_SUBMIT = auto()         # @submit
    EVENT_INPUT = auto()          # @input
    EVENT_CHANGE = auto()         # @change
    EVENT_KEYUP = auto()          # @keyup
    EVENT_KEYDOWN = auto()        # @keydown
    EVENT_FOCUS = auto()          # @focus
    EVENT_BLUR = auto()           # @blur
    EVENT = auto()                # @custom
    
    # Binding directives
    MODEL = auto()                # :model
    CLASS_BIND = auto()           # :class
    STYLE_BIND = auto()           # :style
    SHOW_BIND = auto()            # :show
    HIDE_BIND = auto()            # :hide
    DISABLED_BIND = auto()        # :disabled
    CHECKED_BIND = auto()         # :checked
    VALUE_BIND = auto()           # :value
    HREF_BIND = auto()            # :href
    SRC_BIND = auto()             # :src
    BIND = auto()                 # :custom

    # Transition/animation directives
    TRANSITION_DIRECTIVE = auto()  # transition:fade | in:slide | out:fade | animate:flip

    # Attribute tokens
    ATTRIBUTE_NAME = auto()
    ATTRIBUTE_VALUE = auto()
    EQUALS = auto()
    
    # Expression tokens
    IDENTIFIER = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    NULL = auto()
    
    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQUAL_EQUAL = auto()
    NOT_EQUAL = auto()
    STRICT_EQUAL = auto()
    STRICT_NOT_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    DOT = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    
    # Special
    EOF = auto()


class Token:
    """Represents a token from the lexer."""
    
    def __init__(self, type: TokenType, value: str, line: int = 0, column: int = 0):
        self.type = type
        self.value = value
        self.line = line
        self.column = column
    
    def __repr__(self) -> str:
        return f"Token({self.type}, '{self.value}', {self.line}:{self.column})"


class Lexer:
    """
    Lexical analyzer for Teloce templates.
    
    Converts template source into tokens.
    """
    
    def __init__(self, source: str):
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.errors: List[str] = []
    
    def tokenize(self) -> List[Token]:
        """Tokenize the source string."""
        self.tokens = []
        self.errors = []
        self.position = 0
        self.line = 1
        self.column = 1
        
        while self.position < len(self.source):
            char = self.current_char()
            
            # HTML comments
            if char == '<' and self.peek(1) == '!' and self.peek(2) == '-' and self.peek(3) == '-':
                self._tokenize_comment()
                continue

            if char == '<' and self.source[self.position:self.position + 9].lower() == '<!doctype':
                self._tokenize_doctype()
                continue
            
            # HTML tags
            if char == '<':
                self._tokenize_tag()
                continue
            
            # Interpolation
            if char == '{' and self.peek(1) == '{':
                self._tokenize_interpolation()
                continue
            
            # Closing interpolation
            if char == '}' and self.peek(1) == '}':
                # Skip, handled by interpolation tokenizer
                self.advance()
                self.advance()
                continue
            
            # Text
            self._tokenize_text()
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        
        return self.tokens
    
    def _tokenize_tag(self):
        """Tokenize an HTML or Teloce tag."""
        pos = self.position
        start_line = self.line
        start_col = self.column
        
        self.advance()  # Skip '<'
        
        # Check for closing tag
        if self.current_char() == '/':
            self.advance()
            tag_name = self._read_identifier()
            
            # Check for directive closing
            if tag_name == 'for':
                self.tokens.append(Token(TokenType.FOR_END, f"</{tag_name}>", start_line, start_col))
            elif tag_name == 'if':
                self.tokens.append(Token(TokenType.IF_END, f"</{tag_name}>", start_line, start_col))
            elif tag_name == 'else':
                self.tokens.append(Token(TokenType.ELSE, f"</{tag_name}>", start_line, start_col))
            else:
                self.tokens.append(Token(TokenType.CLOSE_TAG, f"</{tag_name}>", start_line, start_col))
            
            self._skip_until('>')
            self.advance()  # Skip '>'
            return
        
        # Read tag name
        tag_name = self._read_identifier()
        
        # Check for directives
        if tag_name == 'for':
            self.tokens.append(Token(TokenType.FOR_START, tag_name, start_line, start_col))
            self._tokenize_attributes()
            self._skip_until('>')
            self.advance()
            return
        elif tag_name == 'if':
            self.tokens.append(Token(TokenType.IF_START, tag_name, start_line, start_col))
            self._tokenize_attributes()
            self._skip_until('>')
            self.advance()
            return
        elif tag_name == 'else':
            self.tokens.append(Token(TokenType.ELSE, tag_name, start_line, start_col))
            self._skip_until('>')
            self.advance()
            return
        
        # Regular tag
        self.tokens.append(Token(TokenType.OPEN_TAG, tag_name, start_line, start_col))
        self._tokenize_attributes()
        
        # Check for self-closing
        if self.current_char() == '/':
            self.tokens.append(Token(TokenType.SELF_CLOSE_TAG, '/', self.line, self.column))
            self.advance()
        elif tag_name.lower() in self.VOID_ELEMENTS:
            # HTML void elements are self-closing even when written as
            # ``<input>`` or ``<br>``. Treating them as ordinary containers
            # corrupts the AST and causes misleading mismatched-tag errors.
            self.tokens.append(Token(TokenType.SELF_CLOSE_TAG, '/', self.line, self.column))
        
        self._skip_until('>')
        self.advance()  # Skip '>'
    
    def _tokenize_attributes(self):
        """Tokenize tag attributes."""
        while self.position < len(self.source):
            char = self.current_char()
            
            # Skip whitespace
            if char.isspace():
                self.advance()
                continue
            
            if char == '>' or char == '/':
                break
            
            # Event binding (@click)
            if char == '@':
                self.advance()
                event_name = self._read_event_name()
                self.tokens.append(Token(TokenType.EVENT, f"@{event_name}", self.line, self.column - len(event_name) - 1))
                if self.current_char() == '=':
                    self.advance()
                self._tokenize_attribute_value()
                continue
            
            # Binding (:model)
            if char == ':':
                self.advance()
                bind_name = self._read_identifier()
                
                # Check for specific bindings
                if bind_name == 'model':
                    self.tokens.append(Token(TokenType.MODEL, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'class':
                    # Keep the generic BIND token compatible with the public
                    # lexer contract; the parser still receives the name.
                    self.tokens.append(Token(TokenType.BIND, f':{bind_name}', self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'style':
                    self.tokens.append(Token(TokenType.STYLE_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'show':
                    self.tokens.append(Token(TokenType.SHOW_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'hide':
                    self.tokens.append(Token(TokenType.HIDE_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'disabled':
                    self.tokens.append(Token(TokenType.DISABLED_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'checked':
                    self.tokens.append(Token(TokenType.CHECKED_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'value':
                    self.tokens.append(Token(TokenType.VALUE_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'href':
                    self.tokens.append(Token(TokenType.HREF_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                elif bind_name == 'src':
                    self.tokens.append(Token(TokenType.SRC_BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                else:
                    self.tokens.append(Token(TokenType.BIND, bind_name, self.line, self.column - len(bind_name) - 1))
                
                if self.current_char() == '=':
                    self.advance()
                self._tokenize_attribute_value()
                continue
            
            # Regular attribute
            # Vue/Teloce long-form directive spellings.  Keep these as the
            # same public event/binding token kinds as their shorthand forms
            # so the parser has one canonical representation.
            if self.source.startswith('v-on:', self.position):
                start = self.position
                for _ in range(5):
                    self.advance()
                event_name = self._read_event_name()
                self.tokens.append(Token(TokenType.EVENT, f'@{event_name}', self.line, start))
                if self.current_char() == '=':
                    self.advance()
                self._tokenize_attribute_value()
                continue
            if self.source.startswith('v-bind:', self.position):
                start = self.position
                for _ in range(7):
                    self.advance()
                bind_name = self._read_identifier()
                self.tokens.append(Token(TokenType.BIND, bind_name, self.line, start))
                if self.current_char() == '=':
                    self.advance()
                self._tokenize_attribute_value()
                continue
            if self.source.startswith('v-model', self.position):
                start = self.position
                for _ in range(7):
                    self.advance()
                modifiers = ""
                if self.current_char() == '.':
                    modifier_start = self.position
                    while self.position < len(self.source) and (
                        self.current_char().isalnum() or self.current_char() in '-_.'
                    ):
                        self.advance()
                    modifiers = self.source[modifier_start:self.position]
                self.tokens.append(Token(TokenType.MODEL, f'model{modifiers}', self.line, start))
                if self.current_char() == '=':
                    self.advance()
                self._tokenize_attribute_value()
                continue
            # Colon-bearing action attributes are not ordinary identifiers.
            # Keep the complete name so the AST/runtime can support multiple
            # actions on one element (``use:focus use:drag``).
            if self.source.startswith('use:', self.position):
                start = self.position
                for _ in range(4):
                    self.advance()
                while self.position < len(self.source) and (
                    self.current_char().isalnum() or self.current_char() in '-_.:$'
                ):
                    self.advance()
                self.tokens.append(Token(
                    TokenType.ATTRIBUTE_NAME,
                    self.source[start:self.position],
                    self.line,
                    self.column - (self.position - start),
                ))
                if self.current_char() == '=':
                    self.advance()
                    self._tokenize_attribute_value()
                continue
            transition_prefix = self._peek_transition_prefix()
            if transition_prefix:
                start = self.position
                for _ in range(len(transition_prefix) + 1):  # + 1 for the ':'
                    self.advance()
                modifier_name = self._read_identifier()
                self.tokens.append(Token(
                    TokenType.TRANSITION_DIRECTIVE,
                    f'{transition_prefix}:{modifier_name}',
                    self.line, start,
                ))
                if self.current_char() == '=':
                    self.advance()
                    self._tokenize_attribute_value()
                continue

            # Preserve dot-separated modifiers on custom directives. Without
            # this branch ``v-highlight.flash`` becomes two unrelated
            # attributes and the directive receives an empty expression.
            if self.source.startswith('v-', self.position):
                start = self.position
                while self.position < len(self.source) and (
                    self.current_char().isalnum() or self.current_char() in '-_.'
                ):
                    self.advance()
                self.tokens.append(Token(
                    TokenType.ATTRIBUTE_NAME,
                    self.source[start:self.position],
                    self.line,
                    self.column - (self.position - start),
                ))
                if self.current_char() == '=':
                    self.advance()
                    self._tokenize_attribute_value()
                continue

            attr_name = self._read_identifier()
            if not attr_name:
                self.advance()
                continue
            self.tokens.append(Token(TokenType.ATTRIBUTE_NAME, attr_name, self.line, self.column - len(attr_name)))
            
            if self.current_char() == '=':
                self.advance()
                self._tokenize_attribute_value()
    
    def _tokenize_attribute_value(self):
        """Tokenize an attribute value."""
        if self.current_char() == '"':
            self.advance()
            value = self._read_until('"')
            if self.current_char() == '"':
                self.advance()
            self.tokens.append(Token(TokenType.ATTRIBUTE_VALUE, value, self.line, self.column - len(value) - 1))
        elif self.current_char() == "'":
            self.advance()
            value = self._read_until("'")
            if self.current_char() == "'":
                self.advance()
            self.tokens.append(Token(TokenType.ATTRIBUTE_VALUE, value, self.line, self.column - len(value) - 1))
        else:
            # Unquoted value
            value = self._read_until_whitespace()
            if value:
                self.tokens.append(Token(TokenType.ATTRIBUTE_VALUE, value, self.line, self.column - len(value)))
    
    def _tokenize_interpolation(self):
        """Tokenize an interpolation {{ expression }}."""
        start_line = self.line
        start_col = self.column
        
        self.advance()  # Skip '{'
        self.advance()  # Skip '{'
        
        # Skip whitespace
        while self.position < len(self.source) and self.current_char().isspace():
            self.advance()
        
        expression = self._read_until('}}')
        
        # Skip closing braces
        if self.current_char() == '}':
            self.advance()
            if self.current_char() == '}':
                self.advance()
        
        self.tokens.append(Token(TokenType.INTERPOLATION_START, '{{', start_line, start_col))
        self._tokenize_expression(expression)
        self.tokens.append(Token(TokenType.INTERPOLATION_END, '}}', self.line, self.column))
    
    def _tokenize_expression(self, expression: str):
        """Tokenize an expression inside interpolation."""
        # Simple tokenization for expressions
        # This will be expanded for full expression support
        expr = expression.strip()
        if expr:
            self.tokens.append(Token(TokenType.INTERPOLATION_EXPR, expr, self.line, self.column))
    
    def _tokenize_text(self):
        """Tokenize plain text."""
        start_line = self.line
        start_col = self.column
        text = ""
        
        while self.position < len(self.source):
            char = self.current_char()
            
            # Stop at tag or interpolation
            if char == '<':
                break
            if char == '{' and self.peek(1) == '{':
                break
            if char == '}' and self.peek(1) == '}':
                break
            
            text += char
            self.advance()
        
        if text:
            self.tokens.append(Token(TokenType.TEXT, text, start_line, start_col))
    
    def _tokenize_comment(self):
        """Tokenize an HTML comment."""
        start_line = self.line
        start_col = self.column
        
        self.advance()  # Skip '<'
        self.advance()  # Skip '!'
        self.advance()  # Skip '-'
        self.advance()  # Skip '-'
        
        comment = ""
        while self.position < len(self.source):
            char = self.current_char()
            if char == '-' and self.peek(1) == '-' and self.peek(2) == '>':
                self.advance()
                self.advance()
                self.advance()
                break
            comment += char
            self.advance()
        
        self.tokens.append(Token(TokenType.COMMENT, comment, start_line, start_col))

    def _tokenize_doctype(self):
        """Tokenize a document type declaration."""
        start_line, start_col = self.line, self.column
        start = self.position
        self._skip_until('>')
        value = self.source[start:self.position]
        if self.current_char() == '>':
            self.advance()
        self.tokens.append(Token(TokenType.DOCTYPE, value.strip(), start_line, start_col))
    
    def current_char(self) -> str:
        """Get the current character."""
        if self.position >= len(self.source):
            return ''
        return self.source[self.position]
    
    def peek(self, offset: int = 1) -> str:
        """Peek ahead by offset characters."""
        pos = self.position + offset
        if pos >= len(self.source):
            return ''
        return self.source[pos]
    
    def advance(self):
        """Advance to the next character."""
        if self.current_char() == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        self.position += 1
    
    _TRANSITION_PREFIXES = ('transition', 'in', 'out', 'animate')

    def _peek_transition_prefix(self) -> Optional[str]:
        """Return 'transition'/'in'/'out'/'animate' if the source at the
        current position matches PREFIX: followed by an identifier, else
        None. Does not advance the lexer position."""
        for prefix in self._TRANSITION_PREFIXES:
            end = self.position + len(prefix)
            if self.source.startswith(prefix, self.position) and end < len(self.source) and self.source[end] == ':':
                after_colon = end + 1
                if after_colon < len(self.source) and (self.source[after_colon].isalpha() or self.source[after_colon] == '_'):
                    return prefix
        return None

    def _read_identifier(self) -> str:
        """Read an identifier (tag name, attribute name, etc.)."""
        start = self.position
        while self.position < len(self.source) and (self.current_char().isalnum() or self.current_char() in '-_'):
            self.advance()
        return self.source[start:self.position]

    def _read_event_name(self) -> str:
        """Read an event name including dot-separated modifiers."""
        start = self.position
        while self.position < len(self.source) and (self.current_char().isalnum() or self.current_char() in '-_.'):
            self.advance()
        return self.source[start:self.position]
    
    def _read_until(self, delimiter: str) -> str:
        """Read characters until a delimiter is found."""
        start = self.position
        while self.position < len(self.source):
            char = self.current_char()
            if char == delimiter[0] and self.source.startswith(delimiter, self.position):
                break
            self.advance()
        return self.source[start:self.position]
    
    def _read_until_whitespace(self) -> str:
        """Read characters until whitespace is found."""
        start = self.position
        while self.position < len(self.source) and not self.current_char().isspace():
            self.advance()
        return self.source[start:self.position]
    
    def _skip_until(self, delimiter: str):
        """Skip characters until a delimiter is found."""
        while self.position < len(self.source):
            char = self.current_char()
            if char == delimiter[0] and self.source.startswith(delimiter, self.position):
                break
            self.advance()
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

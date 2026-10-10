"""
Expression lexer - tokenizes JavaScript expressions.

Converts expression source code into tokens for parsing.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


class TokenType(Enum):
    """Token types for expression lexer."""
    # Identifiers and literals
    IDENTIFIER = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    NULL = auto()
    UNDEFINED = auto()
    
    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EXPONENT = auto()
    EQUAL = auto()
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
    NULLISH = auto()
    NOT = auto()
    TYPEOF = auto()
    BITWISE_AND = auto()
    BITWISE_OR = auto()
    BITWISE_XOR = auto()
    BITWISE_NOT = auto()
    LEFT_SHIFT = auto()
    RIGHT_SHIFT = auto()
    UNSIGNED_RIGHT_SHIFT = auto()
    
    # Assignment operators
    PLUS_EQUAL = auto()
    MINUS_EQUAL = auto()
    STAR_EQUAL = auto()
    SLASH_EQUAL = auto()
    PERCENT_EQUAL = auto()
    EXPONENT_EQUAL = auto()
    
    # Punctuation
    DOT = auto()
    OPTIONAL_DOT = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    QUESTION = auto()
    
    # Special
    EOF = auto()


@dataclass
class Token:
    """Represents a token."""
    type: TokenType
    value: str
    line: int = 0
    column: int = 0
    
    def __repr__(self) -> str:
        return f"Token({self.type.name}, '{self.value}', {self.line}:{self.column})"


class ExpressionLexer:
    """
    Lexer for JavaScript expressions.
    
    Converts expression source into tokens.
    """
    
    # Keywords
    KEYWORDS = {
        'true': TokenType.BOOLEAN,
        'false': TokenType.BOOLEAN,
        'null': TokenType.NULL,
        'undefined': TokenType.UNDEFINED,
        'typeof': TokenType.TYPEOF,
    }
    
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
            char = self._current_char()
            
            # Skip whitespace
            if char.isspace():
                self._advance()
                continue
            
            # Skip comments
            if char == '/' and self._peek(1) == '/':
                self._skip_line_comment()
                continue
            if char == '/' and self._peek(1) == '*':
                self._skip_block_comment()
                continue
            
            # Numbers
            if char.isdigit() or (char == '.' and self._peek(1).isdigit()):
                self._tokenize_number()
                continue
            
            # Identifiers and keywords
            if char.isalpha() or char == '_' or char == '$':
                self._tokenize_identifier()
                continue
            
            # Strings
            if char == '"' or char == "'":
                self._tokenize_string()
                continue
            
            # Multi-character operators
            if char == '=' and self._peek(1) == '=' and self._peek(2) == '=':
                self._add_token(TokenType.STRICT_EQUAL, '===')
                self._advance()
                self._advance()
                self._advance()
                continue
            
            if char == '!' and self._peek(1) == '=' and self._peek(2) == '=':
                self._add_token(TokenType.STRICT_NOT_EQUAL, '!==')
                self._advance()
                self._advance()
                self._advance()
                continue
            
            if char == '=' and self._peek(1) == '=':
                self._add_token(TokenType.EQUAL_EQUAL, '==')
                self._advance()
                self._advance()
                continue
            
            if char == '!' and self._peek(1) == '=':
                self._add_token(TokenType.NOT_EQUAL, '!=')
                self._advance()
                self._advance()
                continue
            
            if char == '>' and self._peek(1) == '>':
                if self._peek(2) == '>':
                    self._add_token(TokenType.UNSIGNED_RIGHT_SHIFT, '>>>')
                    self._advance()
                    self._advance()
                    self._advance()
                    continue
                self._add_token(TokenType.RIGHT_SHIFT, '>>')
                self._advance()
                self._advance()
                continue
            
            if char == '<' and self._peek(1) == '<':
                self._add_token(TokenType.LEFT_SHIFT, '<<')
                self._advance()
                self._advance()
                continue
            
            if char == '>' and self._peek(1) == '=':
                self._add_token(TokenType.GREATER_EQUAL, '>=')
                self._advance()
                self._advance()
                continue
            
            if char == '<' and self._peek(1) == '=':
                self._add_token(TokenType.LESS_EQUAL, '<=')
                self._advance()
                self._advance()
                continue
            
            if char == '&' and self._peek(1) == '&':
                self._add_token(TokenType.AND, '&&')
                self._advance()
                self._advance()
                continue
            
            if char == '|' and self._peek(1) == '|':
                self._add_token(TokenType.OR, '||')
                self._advance()
                self._advance()
                continue

            if char == '?' and self._peek(1) == '?':
                self._add_token(TokenType.NULLISH, '??')
                self._advance()
                self._advance()
                continue
            
            if char == '+' and self._peek(1) == '=':
                self._add_token(TokenType.PLUS_EQUAL, '+=')
                self._advance()
                self._advance()
                continue
            
            if char == '-' and self._peek(1) == '=':
                self._add_token(TokenType.MINUS_EQUAL, '-=')
                self._advance()
                self._advance()
                continue
            
            if char == '*' and self._peek(1) == '=':
                self._add_token(TokenType.STAR_EQUAL, '*=')
                self._advance()
                self._advance()
                continue
            
            if char == '/' and self._peek(1) == '=':
                self._add_token(TokenType.SLASH_EQUAL, '/=')
                self._advance()
                self._advance()
                continue
            
            if char == '%' and self._peek(1) == '=':
                self._add_token(TokenType.PERCENT_EQUAL, '%=')
                self._advance()
                self._advance()
                continue

            if char == '*' and self._peek(1) == '*' and self._peek(2) == '=':
                self._add_token(TokenType.EXPONENT_EQUAL, '**=')
                self._advance()
                self._advance()
                self._advance()
                continue

            if char == '*' and self._peek(1) == '*':
                self._add_token(TokenType.EXPONENT, '**')
                self._advance()
                self._advance()
                continue
            
            # Single-character operators and punctuation
            if char == '+':
                self._add_token(TokenType.PLUS, '+')
                self._advance()
                continue
            
            if char == '-':
                self._add_token(TokenType.MINUS, '-')
                self._advance()
                continue
            
            if char == '*':
                self._add_token(TokenType.STAR, '*')
                self._advance()
                continue
            
            if char == '/':
                self._add_token(TokenType.SLASH, '/')
                self._advance()
                continue
            
            if char == '%':
                self._add_token(TokenType.PERCENT, '%')
                self._advance()
                continue
            
            if char == '=':
                self._add_token(TokenType.EQUAL, '=')
                self._advance()
                continue
            
            if char == '!':
                self._add_token(TokenType.NOT, '!')
                self._advance()
                continue
            
            if char == '>':
                self._add_token(TokenType.GREATER, '>')
                self._advance()
                continue
            
            if char == '<':
                self._add_token(TokenType.LESS, '<')
                self._advance()
                continue
            
            if char == '&':
                self._add_token(TokenType.BITWISE_AND, '&')
                self._advance()
                continue
            
            if char == '|':
                self._add_token(TokenType.BITWISE_OR, '|')
                self._advance()
                continue
            
            if char == '^':
                self._add_token(TokenType.BITWISE_XOR, '^')
                self._advance()
                continue
            
            if char == '~':
                self._add_token(TokenType.BITWISE_NOT, '~')
                self._advance()
                continue
            
            if char == '.':
                self._add_token(TokenType.DOT, '.')
                self._advance()
                continue
            
            if char == ',':
                self._add_token(TokenType.COMMA, ',')
                self._advance()
                continue
            
            if char == ':':
                self._add_token(TokenType.COLON, ':')
                self._advance()
                continue
            
            if char == ';':
                self._add_token(TokenType.SEMICOLON, ';')
                self._advance()
                continue
            
            if char == '(':
                self._add_token(TokenType.LPAREN, '(')
                self._advance()
                continue
            
            if char == ')':
                self._add_token(TokenType.RPAREN, ')')
                self._advance()
                continue
            
            if char == '[':
                self._add_token(TokenType.LBRACKET, '[')
                self._advance()
                continue
            
            if char == ']':
                self._add_token(TokenType.RBRACKET, ']')
                self._advance()
                continue
            
            if char == '{':
                self._add_token(TokenType.LBRACE, '{')
                self._advance()
                continue
            
            if char == '}':
                self._add_token(TokenType.RBRACE, '}')
                self._advance()
                continue
            
            if char == '?':
                if self._peek(1) == '.':
                    self._add_token(TokenType.OPTIONAL_DOT, '?.')
                    self._advance()
                    self._advance()
                    continue
                self._add_token(TokenType.QUESTION, '?')
                self._advance()
                continue
            
            # Unknown character
            self.errors.append(f"Unexpected character: '{char}' at line {self.line}, column {self.column}")
            self._advance()
        
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens
    
    def _tokenize_number(self):
        """Tokenize a number literal."""
        start_line = self.line
        start_col = self.column
        start_pos = self.position
        has_dot = False
        has_exponent = False
        
        while self.position < len(self.source):
            char = self._current_char()
            if char.isdigit():
                self._advance()
            elif char == '.' and not has_dot and not has_exponent:
                has_dot = True
                self._advance()
            elif char in ('e', 'E') and not has_exponent:
                has_exponent = True
                self._advance()
                if self._current_char() in ('+', '-'):
                    self._advance()
            else:
                break
        
        value = self.source[start_pos:self.position]
        self.tokens.append(Token(TokenType.NUMBER, value, start_line, start_col))
    
    def _tokenize_identifier(self):
        """Tokenize an identifier or keyword."""
        start_line = self.line
        start_col = self.column
        start_pos = self.position
        
        while self.position < len(self.source):
            char = self._current_char()
            if char.isalnum() or char == '_' or char == '$':
                self._advance()
            else:
                break
        
        value = self.source[start_pos:self.position]
        
        # Check if it's a keyword
        if value in self.KEYWORDS:
            self.tokens.append(Token(self.KEYWORDS[value], value, start_line, start_col))
        else:
            self.tokens.append(Token(TokenType.IDENTIFIER, value, start_line, start_col))
    
    def _tokenize_string(self):
        """Tokenize a string literal."""
        start_line = self.line
        start_col = self.column
        quote = self._current_char()
        self._advance()
        
        start_pos = self.position
        escape = False
        
        while self.position < len(self.source):
            char = self._current_char()
            if escape:
                escape = False
                self._advance()
                continue
            
            if char == '\\':
                escape = True
                self._advance()
                continue
            
            if char == quote:
                self._advance()
                break
            
            if char == '\n':
                self.errors.append(f"Unterminated string literal at line {self.line}")
                break
            
            self._advance()
        
        value = self.source[start_pos:self.position - 1]
        self.tokens.append(Token(TokenType.STRING, value, start_line, start_col))
    
    def _skip_line_comment(self):
        """Skip a line comment."""
        while self.position < len(self.source) and self._current_char() != '\n':
            self._advance()
    
    def _skip_block_comment(self):
        """Skip a block comment."""
        self._advance()  # Skip '/'
        self._advance()  # Skip '*'
        
        while self.position < len(self.source):
            if self._current_char() == '*' and self._peek(1) == '/':
                self._advance()
                self._advance()
                break
            self._advance()
    
    def _add_token(self, type: TokenType, value: str):
        """Add a token with the current position."""
        self.tokens.append(Token(type, value, self.line, self.column))
    
    def _current_char(self) -> str:
        """Get the current character."""
        if self.position >= len(self.source):
            return ''
        return self.source[self.position]
    
    def _peek(self, offset: int = 1) -> str:
        """Peek ahead."""
        pos = self.position + offset
        if pos >= len(self.source):
            return ''
        return self.source[pos]
    
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

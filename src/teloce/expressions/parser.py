"""
Expression parser - builds AST from tokens.

Parses JavaScript expressions into an Abstract Syntax Tree.
"""

from typing import List, Optional, Any, Dict, Tuple
from teloce.expressions.lexer import Token, TokenType
from teloce.expressions.ast import (
    ExpressionNode, IdentifierNode, LiteralNode, BinaryNode,
    UnaryNode, CallNode, MemberNode, ArrayNode, ObjectNode,
    TernaryNode, AssignmentNode
)


class ExpressionParser:
    """
    Parser for JavaScript expressions.
    
    Builds an AST from tokens.
    """
    
    def __init__(self):
        self.tokens: List[Token] = []
        self.position = 0
        self.errors: List[str] = []
    
    def parse(self, tokens: List[Token]) -> Optional[ExpressionNode]:
        """Parse tokens into an expression AST."""
        self.tokens = tokens
        self.position = 0
        self.errors = []
        
        if not self.tokens:
            return None
        
        # Skip leading whitespace tokens (none exist in lexer output)
        result = self._parse_expression()
        
        # Check for trailing tokens
        if not self._is_at_end():
            token = self._peek()
            if token.type != TokenType.EOF:
                self.errors.append(f"Unexpected token: {token.value} at {token.line}:{token.column}")
        
        return result
    
    def _parse_expression(self) -> Optional[ExpressionNode]:
        """Parse an expression."""
        return self._parse_assignment()
    
    def _parse_assignment(self) -> Optional[ExpressionNode]:
        """Parse an assignment expression."""
        left = self._parse_logical_or()
        
        assignment_operators = {
            TokenType.EQUAL: '=',
            TokenType.PLUS_EQUAL: '+=',
            TokenType.MINUS_EQUAL: '-=',
            TokenType.STAR_EQUAL: '*=',
            TokenType.SLASH_EQUAL: '/=',
            TokenType.PERCENT_EQUAL: '%=',
            TokenType.EXPONENT_EQUAL: '**=',
        }
        operator = next((value for token_type, value in assignment_operators.items() if self._match(token_type)), None)
        if operator:
            right = self._parse_assignment()
            if right and left:
                return AssignmentNode(left, right, operator)
        
        return left
    
    def _parse_logical_or(self) -> Optional[ExpressionNode]:
        """Parse a logical OR expression."""
        left = self._parse_nullish()
        
        while self._match(TokenType.OR):
            right = self._parse_nullish()
            if right:
                left = BinaryNode(left, '||', right)
        
        return left

    def _parse_nullish(self) -> Optional[ExpressionNode]:
        """Parse JavaScript's nullish-coalescing operator."""
        left = self._parse_logical_and()
        while self._match(TokenType.NULLISH):
            right = self._parse_logical_and()
            if right:
                left = BinaryNode(left, '??', right)
        return left
    
    def _parse_logical_and(self) -> Optional[ExpressionNode]:
        """Parse a logical AND expression."""
        left = self._parse_bitwise_or()
        
        while self._match(TokenType.AND):
            right = self._parse_bitwise_or()
            if right:
                left = BinaryNode(left, '&&', right)
        
        return left
    
    def _parse_bitwise_or(self) -> Optional[ExpressionNode]:
        """Parse a bitwise OR expression."""
        left = self._parse_bitwise_xor()
        
        while self._match(TokenType.BITWISE_OR):
            right = self._parse_bitwise_xor()
            if right:
                left = BinaryNode(left, '|', right)
        
        return left
    
    def _parse_bitwise_xor(self) -> Optional[ExpressionNode]:
        """Parse a bitwise XOR expression."""
        left = self._parse_bitwise_and()
        
        while self._match(TokenType.BITWISE_XOR):
            right = self._parse_bitwise_and()
            if right:
                left = BinaryNode(left, '^', right)
        
        return left
    
    def _parse_bitwise_and(self) -> Optional[ExpressionNode]:
        """Parse a bitwise AND expression."""
        left = self._parse_equality()
        
        while self._match(TokenType.BITWISE_AND):
            right = self._parse_equality()
            if right:
                left = BinaryNode(left, '&', right)
        
        return left
    
    def _parse_equality(self) -> Optional[ExpressionNode]:
        """Parse an equality expression."""
        left = self._parse_comparison()
        
        while True:
            if self._match(TokenType.STRICT_EQUAL):
                right = self._parse_comparison()
                if right:
                    left = BinaryNode(left, '===', right)
            elif self._match(TokenType.STRICT_NOT_EQUAL):
                right = self._parse_comparison()
                if right:
                    left = BinaryNode(left, '!==', right)
            elif self._match(TokenType.EQUAL_EQUAL):
                right = self._parse_comparison()
                if right:
                    left = BinaryNode(left, '==', right)
            elif self._match(TokenType.NOT_EQUAL):
                right = self._parse_comparison()
                if right:
                    left = BinaryNode(left, '!=', right)
            else:
                break
        
        return left
    
    def _parse_comparison(self) -> Optional[ExpressionNode]:
        """Parse a comparison expression."""
        left = self._parse_shift()
        
        while True:
            if self._match(TokenType.GREATER):
                right = self._parse_shift()
                if right:
                    left = BinaryNode(left, '>', right)
            elif self._match(TokenType.GREATER_EQUAL):
                right = self._parse_shift()
                if right:
                    left = BinaryNode(left, '>=', right)
            elif self._match(TokenType.LESS):
                right = self._parse_shift()
                if right:
                    left = BinaryNode(left, '<', right)
            elif self._match(TokenType.LESS_EQUAL):
                right = self._parse_shift()
                if right:
                    left = BinaryNode(left, '<=', right)
            else:
                break
        
        return left
    
    def _parse_shift(self) -> Optional[ExpressionNode]:
        """Parse a shift expression."""
        left = self._parse_additive()
        
        while True:
            if self._match(TokenType.LEFT_SHIFT):
                right = self._parse_additive()
                if right:
                    left = BinaryNode(left, '<<', right)
            elif self._match(TokenType.RIGHT_SHIFT):
                right = self._parse_additive()
                if right:
                    left = BinaryNode(left, '>>', right)
            elif self._match(TokenType.UNSIGNED_RIGHT_SHIFT):
                right = self._parse_additive()
                if right:
                    left = BinaryNode(left, '>>>', right)
            else:
                break
        
        return left
    
    def _parse_additive(self) -> Optional[ExpressionNode]:
        """Parse an additive expression."""
        left = self._parse_multiplicative()
        
        while True:
            if self._match(TokenType.PLUS):
                right = self._parse_multiplicative()
                if right:
                    left = BinaryNode(left, '+', right)
            elif self._match(TokenType.MINUS):
                right = self._parse_multiplicative()
                if right:
                    left = BinaryNode(left, '-', right)
            else:
                break
        
        return left
    
    def _parse_multiplicative(self) -> Optional[ExpressionNode]:
        """Parse a multiplicative expression."""
        left = self._parse_exponent()
        
        while True:
            if self._match(TokenType.STAR):
                right = self._parse_exponent()
                if right:
                    left = BinaryNode(left, '*', right)
            elif self._match(TokenType.SLASH):
                right = self._parse_exponent()
                if right:
                    left = BinaryNode(left, '/', right)
            elif self._match(TokenType.PERCENT):
                right = self._parse_exponent()
                if right:
                    left = BinaryNode(left, '%', right)
            else:
                break
        
        return left

    def _parse_exponent(self) -> Optional[ExpressionNode]:
        """Parse right-associative exponentiation."""
        left = self._parse_unary()
        if self._match(TokenType.EXPONENT):
            right = self._parse_exponent()
            if left and right:
                return BinaryNode(left, '**', right)
        return left
    
    def _parse_unary(self) -> Optional[ExpressionNode]:
        """Parse a unary expression."""
        if self._match(TokenType.TYPEOF):
            operand = self._parse_unary()
            if operand:
                return UnaryNode("typeof", operand)

        if self._match(TokenType.NOT):
            operand = self._parse_unary()
            if operand:
                return UnaryNode('!', operand)
        
        if self._match(TokenType.MINUS):
            operand = self._parse_unary()
            if operand:
                return UnaryNode('-', operand)
        
        if self._match(TokenType.PLUS):
            operand = self._parse_unary()
            if operand:
                return UnaryNode('+', operand)
        
        if self._match(TokenType.BITWISE_NOT):
            operand = self._parse_unary()
            if operand:
                return UnaryNode('~', operand)
        
        return self._parse_primary()
    
    def _parse_primary(self) -> Optional[ExpressionNode]:
        """Parse a primary expression."""
        token = self._peek()
        
        # Parenthesized expression
        if token.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            if self._match(TokenType.RPAREN):
                return expr
            self.errors.append("Expected ')'")
            return None
        
        # Literals
        if token.type == TokenType.BOOLEAN:
            self._advance()
            return LiteralNode(token.value.lower() == 'true')
        
        if token.type == TokenType.NULL:
            self._advance()
            return LiteralNode(None)
        
        if token.type == TokenType.UNDEFINED:
            self._advance()
            return IdentifierNode("undefined")
        
        if token.type == TokenType.NUMBER:
            self._advance()
            try:
                if '.' in token.value or 'e' in token.value.lower():
                    return LiteralNode(float(token.value))
                return LiteralNode(int(token.value))
            except ValueError:
                self.errors.append(f"Invalid number: {token.value}")
                return None
        
        if token.type == TokenType.STRING:
            self._advance()
            return LiteralNode(token.value)
        
        if token.type == TokenType.IDENTIFIER:
            self._advance()
            return self._parse_postfix(IdentifierNode(token.value))
        
        # Array literal
        if token.type == TokenType.LBRACKET:
            return self._parse_array()
        
        # Object literal
        if token.type == TokenType.LBRACE:
            return self._parse_object()
        
        self.errors.append(f"Unexpected token: {token.value}")
        return None
    
    def _parse_postfix(self, node: ExpressionNode) -> ExpressionNode:
        """Parse postfix expressions (member access, calls, etc.)."""
        while True:
            # Optional member access: object?.property
            if self._match(TokenType.OPTIONAL_DOT):
                prop_token = self._peek()
                if prop_token.type == TokenType.IDENTIFIER:
                    self._advance()
                    node = MemberNode(node, prop_token.value, optional=True)
                else:
                    self.errors.append("Expected identifier after '?.'")
                    return node
            # Member access: .property
            elif self._match(TokenType.DOT):
                prop_token = self._peek()
                if prop_token.type == TokenType.IDENTIFIER:
                    self._advance()
                    node = MemberNode(node, prop_token.value)
                else:
                    self.errors.append(f"Expected identifier after '.'")
                    return node
            
            # Computed member access: [expression]
            elif self._match(TokenType.LBRACKET):
                index = self._parse_expression()
                if self._match(TokenType.RBRACKET):
                    if index:
                        # Keep the expression AST; repr() is not JavaScript.
                        node = MemberNode(node, index, computed=True)
                else:
                    self.errors.append("Expected ']'")
                    return node
            
            # Function call: (arguments)
            elif self._match(TokenType.LPAREN):
                args = []
                while not self._match(TokenType.RPAREN):
                    if self._match(TokenType.COMMA):
                        continue
                    arg = self._parse_expression()
                    if arg:
                        args.append(arg)
                    if self._peek().type == TokenType.RPAREN:
                        self._advance()
                        break
                node = CallNode(node, args)
            
            # Ternary operator: ? :
            elif self._match(TokenType.QUESTION):
                then_expr = self._parse_expression()
                if self._match(TokenType.COLON):
                    else_expr = self._parse_expression()
                    if then_expr and else_expr:
                        node = TernaryNode(node, then_expr, else_expr)
                else:
                    self.errors.append("Expected ':'")
                    return node
            
            else:
                break
        
        return node
    
    def _parse_array(self) -> Optional[ArrayNode]:
        """Parse an array literal."""
        self._advance()  # Skip '['
        
        elements = []
        while not self._match(TokenType.RBRACKET):
            if self._match(TokenType.COMMA):
                continue
            element = self._parse_expression()
            if element:
                elements.append(element)
            if self._peek().type == TokenType.RBRACKET:
                self._advance()
                break
        
        return ArrayNode(elements)
    
    def _parse_object(self) -> Optional[ObjectNode]:
        """Parse an object literal."""
        self._advance()  # Skip '{'
        
        properties = []
        while not self._match(TokenType.RBRACE):
            # Get key
            key_token = self._peek()
            key = None
            
            if key_token.type == TokenType.IDENTIFIER:
                self._advance()
                key = key_token.value
            elif key_token.type == TokenType.STRING:
                self._advance()
                key = key_token.value
            elif key_token.type == TokenType.NUMBER:
                self._advance()
                key = key_token.value
            else:
                self.errors.append(f"Unexpected key token: {key_token.value}")
                break
            
            if not self._match(TokenType.COLON):
                self.errors.append("Expected ':'")
                break
            
            value = self._parse_expression()
            if value:
                properties.append((key, value))
            
            if self._match(TokenType.COMMA):
                continue
        
        return ObjectNode(properties)
    
    def _match(self, *types: TokenType) -> bool:
        """Check if the current token matches any of the given types."""
        if self._is_at_end():
            return False
        
        token = self._peek()
        if token.type in types:
            self._advance()
            return True
        
        return False
    
    def _peek(self) -> Token:
        """Peek at the next token."""
        if self._is_at_end():
            return Token(TokenType.EOF, "", 0, 0)
        return self.tokens[self.position]
    
    def _advance(self) -> Token:
        """Advance to the next token."""
        token = self._peek()
        self.position += 1
        return token
    
    def _is_at_end(self) -> bool:
        """Check if we've reached the end of tokens."""
        return self.position >= len(self.tokens) or self.tokens[self.position].type == TokenType.EOF
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

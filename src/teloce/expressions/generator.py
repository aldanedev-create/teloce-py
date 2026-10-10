"""
Expression generator - generates JavaScript code from expression AST.

Converts expression AST nodes back to JavaScript source code.
"""

from typing import List, Optional, Any, Dict
from teloce.expressions.ast import (
    ExpressionNode, IdentifierNode, LiteralNode, BinaryNode,
    UnaryNode, CallNode, MemberNode, ArrayNode, ObjectNode,
    TernaryNode, AssignmentNode
)


class ExpressionGenerator:
    """
    Generates JavaScript code from expression AST.
    
    Converts AST nodes back to source code.
    """
    
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        self.options = options or {}
        self.minify = self.options.get('minify', False)
    
    def generate(self, node: ExpressionNode) -> str:
        """Generate JavaScript code from an expression node."""
        if isinstance(node, IdentifierNode):
            return self._generate_identifier(node)
        elif isinstance(node, LiteralNode):
            return self._generate_literal(node)
        elif isinstance(node, BinaryNode):
            return self._generate_binary(node)
        elif isinstance(node, UnaryNode):
            return self._generate_unary(node)
        elif isinstance(node, CallNode):
            return self._generate_call(node)
        elif isinstance(node, MemberNode):
            return self._generate_member(node)
        elif isinstance(node, ArrayNode):
            return self._generate_array(node)
        elif isinstance(node, ObjectNode):
            return self._generate_object(node)
        elif isinstance(node, TernaryNode):
            return self._generate_ternary(node)
        elif isinstance(node, AssignmentNode):
            return self._generate_assignment(node)
        else:
            return str(node)
    
    def _generate_identifier(self, node: IdentifierNode) -> str:
        """Generate code for an identifier."""
        return node.name
    
    def _generate_literal(self, node: LiteralNode) -> str:
        """Generate code for a literal."""
        if node.value is None:
            return 'null'
        if isinstance(node.value, bool):
            return 'true' if node.value else 'false'
        if isinstance(node.value, str):
            return f"'{node.value}'"
        return str(node.value)
    
    def _generate_binary(self, node: BinaryNode) -> str:
        """Generate code for a binary expression."""
        left = self.generate(node.left)
        right = self.generate(node.right)
        
        if self.minify:
            return f"({left}{node.operator}{right})"
        return f"({left} {node.operator} {right})"
    
    def _generate_unary(self, node: UnaryNode) -> str:
        """Generate code for a unary expression."""
        operand = self.generate(node.operand)
        
        separator = " " if node.operator == "typeof" else ""
        return f"{node.operator}{separator}{operand}"
    
    def _generate_call(self, node: CallNode) -> str:
        """Generate code for a function call."""
        callee = self.generate(node.callee)
        args = ', '.join(self.generate(arg) for arg in node.arguments)
        return f"{callee}({args})"
    
    def _generate_member(self, node: MemberNode) -> str:
        """Generate code for a member access."""
        obj = self.generate(node.object)
        
        if node.computed:
            property_code = self.generate(node.property) if isinstance(node.property, ExpressionNode) else node.property
            return f"{obj}[{property_code}]"
        return f"{obj}{'?.' if node.optional else '.'}{node.property}"
    
    def _generate_array(self, node: ArrayNode) -> str:
        """Generate code for an array literal."""
        if not node.elements:
            return '[]'
        
        elements = ', '.join(self.generate(el) for el in node.elements)
        return f"[{elements}]"
    
    def _generate_object(self, node: ObjectNode) -> str:
        """Generate code for an object literal."""
        if not node.properties:
            return '{}'
        
        props = []
        for key, value in node.properties:
            props.append(f"{key}: {self.generate(value)}")
        
        return f"{{{', '.join(props)}}}"
    
    def _generate_ternary(self, node: TernaryNode) -> str:
        """Generate code for a ternary expression."""
        condition = self.generate(node.condition)
        then_expr = self.generate(node.then_expr)
        else_expr = self.generate(node.else_expr)
        
        if self.minify:
            return f"({condition}?{then_expr}:{else_expr})"
        return f"({condition} ? {then_expr} : {else_expr})"
    
    def _generate_assignment(self, node: AssignmentNode) -> str:
        """Generate code for an assignment expression."""
        left = self.generate(node.left)
        right = self.generate(node.right)
        
        if self.minify:
            return f"{left}{node.operator}{right}"
        return f"{left} {node.operator} {right}"

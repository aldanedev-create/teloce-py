"""
Expression AST nodes.

Defines the Abstract Syntax Tree for JavaScript expressions.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Union, Dict


@dataclass
class ExpressionNode:
    """Base class for expression nodes."""
    line: int = field(default=0, kw_only=True)
    column: int = field(default=0, kw_only=True)


@dataclass
class IdentifierNode(ExpressionNode):
    """Identifier expression."""
    name: str
    
    def __repr__(self) -> str:
        return f"Identifier({self.name})"


@dataclass
class LiteralNode(ExpressionNode):
    """Literal value expression."""
    value: Any
    
    def __repr__(self) -> str:
        return f"Literal({repr(self.value)})"


@dataclass
class BinaryNode(ExpressionNode):
    """Binary operation expression."""
    left: ExpressionNode
    operator: str
    right: ExpressionNode
    
    def __repr__(self) -> str:
        return f"Binary({self.left} {self.operator} {self.right})"


@dataclass
class UnaryNode(ExpressionNode):
    """Unary operation expression."""
    operator: str
    operand: ExpressionNode
    
    def __repr__(self) -> str:
        return f"Unary({self.operator}{self.operand})"


@dataclass
class CallNode(ExpressionNode):
    """Function call expression."""
    callee: ExpressionNode
    arguments: List[ExpressionNode] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Call({self.callee}, {self.arguments})"


@dataclass
class MemberNode(ExpressionNode):
    """Member access expression."""
    object: ExpressionNode
    property: Union[str, ExpressionNode]
    computed: bool = False
    optional: bool = False
    
    def __repr__(self) -> str:
        if self.computed:
            return f"Member({self.object}[{self.property}])"
        return f"Member({self.object}{'?.' if self.optional else '.'}{self.property})"


@dataclass
class ArrayNode(ExpressionNode):
    """Array literal expression."""
    elements: List[ExpressionNode] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Array({self.elements})"


@dataclass
class ObjectNode(ExpressionNode):
    """Object literal expression."""
    properties: List[tuple] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Object({self.properties})"


@dataclass
class TernaryNode(ExpressionNode):
    """Ternary (conditional) expression."""
    condition: ExpressionNode
    then_expr: ExpressionNode
    else_expr: ExpressionNode
    
    def __repr__(self) -> str:
        return f"Ternary({self.condition} ? {self.then_expr} : {self.else_expr})"


@dataclass
class AssignmentNode(ExpressionNode):
    """Assignment expression."""
    left: ExpressionNode
    right: ExpressionNode
    operator: str = '='
    
    def __repr__(self) -> str:
        return f"Assignment({self.left} = {self.right})"

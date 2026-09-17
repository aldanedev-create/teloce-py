"""
AST node definitions for Teloce templates.

Defines all node types used in the Abstract Syntax Tree.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


class NodeType(Enum):
    """Types of AST nodes."""
    ELEMENT = auto()
    TEXT = auto()
    INTERPOLATION = auto()
    FOR = auto()
    IF = auto()
    ELSE = auto()
    EVENT = auto()
    BINDING = auto()
    COMPONENT = auto()
    SLOT = auto()
    FRAGMENT = auto()
    ATTRIBUTE = auto()
    COMMENT = auto()
    DOCTYPE = auto()


@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    type: NodeType
    line: int = 0
    column: int = 0
    
    def accept(self, visitor):
        """Accept a visitor."""
        method_name = f"visit_{self.type.name.lower()}"
        method = getattr(visitor, method_name, None)
        if method:
            return method(self)
        return visitor.visit_default(self)


@dataclass(init=False)
class ElementNode(ASTNode):
    """HTML element node."""
    tag: str
    attributes: Dict[str, str] = field(default_factory=dict)
    events: List['EventNode'] = field(default_factory=list)
    bindings: List['BindingNode'] = field(default_factory=list)
    transitions: List['TransitionDirectiveNode'] = field(default_factory=list)
    children: List[ASTNode] = field(default_factory=list)
    
    def __init__(self, tag: str, attributes: Dict[str, str] = None,
                 events: List['EventNode'] = None,
                 bindings: List['BindingNode'] = None,
                 children: List[ASTNode] = None,
                 line: int = 0, column: int = 0,
                 transitions: List['TransitionDirectiveNode'] = None):
        super().__init__(NodeType.ELEMENT, line, column)
        self.tag = tag
        self.attributes = attributes or {}
        self.events = events or []
        self.bindings = bindings or []
        self.transitions = transitions or []
        self.children = children or []
    
    def accept(self, visitor):
        return visitor.visit_element(self)


@dataclass(init=False)
class TextNode(ASTNode):
    """Plain text node."""
    value: str
    
    def __init__(self, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.TEXT, line, column)
        self.value = value
    
    def accept(self, visitor):
        return visitor.visit_text(self)


@dataclass(init=False)
class InterpolationNode(ASTNode):
    """{{ expression }} interpolation node."""
    expression: str
    
    def __init__(self, expression: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.INTERPOLATION, line, column)
        self.expression = expression
    
    def accept(self, visitor):
        return visitor.visit_interpolation(self)


@dataclass(init=False)
class ForNode(ASTNode):
    """For loop directive node."""
    item: str
    collection: str
    key: str = ""
    children: List[ASTNode] = field(default_factory=list)
    virtual: bool = False
    virtual_options: Dict[str, str] = field(default_factory=dict)
    
    def __init__(self, item: str, collection: str, key: str = "",
                 children: List[ASTNode] = None,
                 line: int = 0, column: int = 0,
                 virtual: bool = False,
                 virtual_options: Dict[str, str] = None):
        super().__init__(NodeType.FOR, line, column)
        self.item = item
        self.collection = collection
        self.key = key
        self.children = children or []
        self.virtual = virtual
        self.virtual_options = virtual_options or {}
    
    def accept(self, visitor):
        return visitor.visit_for(self)


@dataclass(init=False)
class IfNode(ASTNode):
    """If directive node."""
    condition: str
    children: List[ASTNode] = field(default_factory=list)
    else_children: List[ASTNode] = field(default_factory=list)
    
    def __init__(self, condition: str, children: List[ASTNode] = None,
                 else_children: List[ASTNode] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.IF, line, column)
        self.condition = condition
        self.children = children or []
        self.else_children = else_children or []
    
    def accept(self, visitor):
        return visitor.visit_if(self)


@dataclass(init=False)
class ElseNode(ASTNode):
    """Else directive node."""
    children: List[ASTNode] = field(default_factory=list)
    
    def __init__(self, children: List[ASTNode] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.ELSE, line, column)
        self.children = children or []
    
    def accept(self, visitor):
        return visitor.visit_else(self)


@dataclass(init=False)
class EventNode(ASTNode):
    """@click event binding node."""
    name: str
    handler: str
    
    def __init__(self, name: str, handler: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.EVENT, line, column)
        self.name = name
        self.handler = handler
    
    def accept(self, visitor):
        return visitor.visit_event(self)


@dataclass(init=False)
class TransitionDirectiveNode(ASTNode):
    """transition:/in:/out:/animate: directive node.

    kind is one of "transition", "in", "out", "animate".
    name is the helper name, e.g. "fade", "slide", "flip".
    params is the raw `{ ... }` JS object literal, or "" if none given.
    """
    kind: str
    name: str
    params: str

    def __init__(self, kind: str, name: str, params: str = "", line: int = 0, column: int = 0):
        super().__init__(NodeType.BINDING, line, column)
        self.kind = kind
        self.name = name
        self.params = params

    def accept(self, visitor):
        method = getattr(visitor, "visit_transition_directive", None)
        return method(self) if method else visitor.visit_default(self)


@dataclass(init=False)
class BindingNode(ASTNode):
    """:model binding node."""
    name: str
    value: str
    
    def __init__(self, name: str, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.BINDING, line, column)
        self.name = name
        self.value = value
    
    def accept(self, visitor):
        return visitor.visit_binding(self)


@dataclass(init=False)
class ComponentNode(ASTNode):
    """Custom component node."""
    name: str
    props: Dict[str, str] = field(default_factory=dict)
    children: List[ASTNode] = field(default_factory=list)
    slots: Dict[str, List[ASTNode]] = field(default_factory=dict)
    
    def __init__(self, name: str, props: Dict[str, str] = None,
                 children: List[ASTNode] = None,
                 slots: Dict[str, List[ASTNode]] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.COMPONENT, line, column)
        self.name = name
        self.props = props or {}
        self.children = children or []
        self.slots = slots or {}
    
    def accept(self, visitor):
        return visitor.visit_component(self)


@dataclass(init=False)
class SlotNode(ASTNode):
    """Slot node."""
    name: str = "default"
    children: List[ASTNode] = field(default_factory=list)
    
    def __init__(self, name: str = "default", children: List[ASTNode] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.SLOT, line, column)
        self.name = name
        self.children = children or []
    
    def accept(self, visitor):
        return visitor.visit_slot(self)


@dataclass(init=False)
class FragmentNode(ASTNode):
    """Fragment node (multiple root elements)."""
    children: List[ASTNode] = field(default_factory=list)
    
    def __init__(self, children: List[ASTNode] = None,
                 line: int = 0, column: int = 0):
        super().__init__(NodeType.FRAGMENT, line, column)
        self.children = children or []
    
    def accept(self, visitor):
        return visitor.visit_fragment(self)


@dataclass(init=False)
class AttributeNode(ASTNode):
    """HTML attribute node."""
    name: str
    value: str
    
    def __init__(self, name: str, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.ATTRIBUTE, line, column)
        self.name = name
        self.value = value
    
    def accept(self, visitor):
        return visitor.visit_attribute(self)


@dataclass(init=False)
class CommentNode(ASTNode):
    """HTML comment node."""
    value: str
    
    def __init__(self, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.COMMENT, line, column)
        self.value = value
    
    def accept(self, visitor):
        return visitor.visit_comment(self)


@dataclass(init=False)
class DoctypeNode(ASTNode):
    """DOCTYPE node."""
    value: str
    
    def __init__(self, value: str, line: int = 0, column: int = 0):
        super().__init__(NodeType.DOCTYPE, line, column)
        self.value = value
    
    def accept(self, visitor):
        return visitor.visit_doctype(self)

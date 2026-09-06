"""
Parser for Teloce templates.

Converts tokens into an Abstract Syntax Tree (AST).
"""

from typing import List, Optional, Any
import re

from teloce.compiler.lexer import Token, TokenType
from teloce.ast.nodes import (
    ASTNode, ElementNode, TextNode, InterpolationNode,
    ForNode, IfNode, ElseNode, EventNode, BindingNode,
    ComponentNode, SlotNode, FragmentNode, TransitionDirectiveNode
)


class Parser:
    """
    Parses tokens into an Abstract Syntax Tree.
    """
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.position = 0
        self.errors: List[str] = []
    
    def parse(self) -> List[ASTNode]:
        """Parse tokens into an AST."""
        self.errors = []
        return self._parse_nodes()
    
    def _parse_nodes(self, stop_types=None) -> List[ASTNode]:
        """Parse a list of nodes."""
        nodes = []
        stop_types = set(stop_types or ())
        
        while not self._is_at_end() and self._peek().type not in stop_types:
            node = self._parse_node()
            if node:
                # Long-form v-else/v-else-if branches are represented as
                # adjacent elements by the HTML lexer. Fold them into the
                # preceding IfNode before they reach code generation.
                if isinstance(node, ElementNode) and ('v-else-if' in node.attributes or 'v-else' in node.attributes):
                    anchor_index = len(nodes) - 1
                    while anchor_index >= 0 and isinstance(nodes[anchor_index], TextNode) and not nodes[anchor_index].value.strip():
                        anchor_index -= 1
                    if anchor_index >= 0 and isinstance(nodes[anchor_index], IfNode):
                        del nodes[anchor_index + 1:]
                        chain_end = nodes[anchor_index]
                        while (
                            chain_end.else_children
                            and len(chain_end.else_children) == 1
                            and isinstance(chain_end.else_children[0], IfNode)
                        ):
                            chain_end = chain_end.else_children[0]
                        if 'v-else-if' in node.attributes:
                            condition = node.attributes.pop('v-else-if')
                            branch = IfNode(condition, [node], [], node.line, node.column)
                            chain_end.else_children = [branch]
                        else:
                            node.attributes.pop('v-else')
                            chain_end.else_children = [node]
                        continue
                nodes.append(node)
            else:
                token = self._advance()
                if token.type not in (TokenType.COMMENT, TokenType.ATTRIBUTE_VALUE):
                    self.errors.append(f"Unexpected token {token.type.name} at {token.line}:{token.column}")
        
        return nodes
    
    def _parse_node(self) -> Optional[ASTNode]:
        """Parse a single node."""
        token = self._peek()
        
        if token.type == TokenType.OPEN_TAG:
            return self._parse_element()
        elif token.type == TokenType.INTERPOLATION_START:
            return self._parse_interpolation()
        elif token.type == TokenType.FOR_START:
            return self._parse_for()
        elif token.type == TokenType.IF_START:
            return self._parse_if()
        elif token.type == TokenType.TEXT:
            self._advance()
            return TextNode(token.value, token.line, token.column)
        else:
            return None
    
    def _parse_element(self) -> Optional[ElementNode]:
        """Parse an HTML element."""
        tag_token = self._advance()
        tag_name = tag_token.value
        
        # Parse attributes
        attributes = {}
        events = []
        bindings = []
        transitions = []
        
        while not self._is_at_end():
            token = self._peek()

            if token.type == TokenType.TRANSITION_DIRECTIVE:
                self._advance()
                kind, _, modifier_name = token.value.partition(':')

                if self._peek().type == TokenType.ATTRIBUTE_VALUE:
                    value_token = self._advance()
                    transitions.append(TransitionDirectiveNode(
                        kind, modifier_name, value_token.value, token.line, token.column
                    ))
                else:
                    transitions.append(TransitionDirectiveNode(
                        kind, modifier_name, "", token.line, token.column
                    ))

            elif token.type == TokenType.ATTRIBUTE_NAME:
                self._advance()
                attr_name = token.value
                
                # Check for value
                if self._peek().type == TokenType.ATTRIBUTE_VALUE:
                    value_token = self._advance()
                    attributes[attr_name] = value_token.value
                else:
                    attributes[attr_name] = ""
            
            elif token.type == TokenType.EVENT:
                self._advance()
                event_name = token.value
                
                # Get event handler
                if self._peek().type == TokenType.ATTRIBUTE_VALUE:
                    handler_token = self._advance()
                    events.append(EventNode(event_name.lstrip('@'), handler_token.value, token.line, token.column))
                else:
                    events.append(EventNode(event_name.lstrip('@'), "", token.line, token.column))
            
            elif token.type in (TokenType.MODEL, TokenType.CLASS_BIND, TokenType.STYLE_BIND,
                               TokenType.SHOW_BIND, TokenType.HIDE_BIND,
                               TokenType.DISABLED_BIND, TokenType.CHECKED_BIND,
                               TokenType.VALUE_BIND, TokenType.HREF_BIND,
                               TokenType.SRC_BIND, TokenType.BIND):
                self._advance()
                bind_name = token.value.lstrip(':')
                
                # Get binding value
                if self._peek().type == TokenType.ATTRIBUTE_VALUE:
                    value_token = self._advance()
                    bindings.append(BindingNode(bind_name, value_token.value, token.line, token.column))
                else:
                    bindings.append(BindingNode(bind_name, "", token.line, token.column))
            
            elif token.type == TokenType.ATTRIBUTE_VALUE:
                # Skip standalone attribute values
                self._advance()
            
            elif token.type == TokenType.SELF_CLOSE_TAG:
                self._advance()
                return self._lower_long_form_directives(
                    self._create_element(tag_name, attributes, events, bindings, [], transitions)
                )
            
            else:
                break

        # The lexer does not emit a token for the opening `>`; after the
        # attributes, the next token begins the element body.
        children = self._parse_nodes({TokenType.CLOSE_TAG, TokenType.EOF})
        if self._peek().type == TokenType.CLOSE_TAG:
            close_token = self._advance()
            if close_token.value != f"</{tag_name}>":
                self.errors.append(
                    f"Mismatched closing tag {close_token.value}; expected </{tag_name}>"
                )
        else:
            self.errors.append(f"Missing closing tag </{tag_name}>")
        element = self._create_element(tag_name, attributes, events, bindings, children, transitions)
        return self._lower_long_form_directives(element)

    def _lower_long_form_directives(self, element: ElementNode) -> ASTNode:
        """Lower npm/Vue-compatible structural attributes into AST nodes."""
        for source_name, binding_name in (
            ('v-show', 'show'),
            ('v-hide', 'hide'),
            ('v-text', 'text'),
            ('v-html', 'html'),
        ):
            if source_name in element.attributes:
                element.bindings.append(
                    BindingNode(binding_name, element.attributes.pop(source_name), element.line, element.column)
                )
        if 'v-for' in element.attributes:
            expression = element.attributes.pop('v-for').strip()
            match = re.match(
                r'^\s*(?:\(([^)]+)\)|([^\s]+))\s+(?:in|of)\s+(.+?)\s*$',
                expression,
            )
            if match:
                variables = [part.strip() for part in (match.group(1) or match.group(2)).split(',')]
                item = variables[0] or 'item'
                collection = match.group(3)
                key = ''
                for binding in list(element.bindings):
                    if binding.name == 'key':
                        key = binding.value
                        element.bindings.remove(binding)
                        break
                if not key and 'key' in element.attributes:
                    key = element.attributes.pop('key')
                child: ASTNode = element
                if 'v-if' in element.attributes:
                    condition = element.attributes.pop('v-if').strip()
                    child = IfNode(condition, [element], [], element.line, element.column)
                return ForNode(item, collection, key, [child], element.line, element.column)
        if 'v-if' in element.attributes:
            condition = element.attributes.pop('v-if').strip()
            return IfNode(condition, [element], [], element.line, element.column)
        return element
    
    def _parse_interpolation(self) -> Optional[InterpolationNode]:
        """Parse an interpolation {{ expression }}."""
        start_token = self._advance()  # Skip {{
        expression_token = self._advance()  # Expression
        end_token = self._advance()  # Skip }}
        
        if expression_token.type in (TokenType.IDENTIFIER, TokenType.INTERPOLATION_EXPR):
            return InterpolationNode(expression_token.value, start_token.line, start_token.column)
        elif expression_token.type == TokenType.TEXT:
            return InterpolationNode(expression_token.value.strip(), start_token.line, start_token.column)
        
        return InterpolationNode("", start_token.line, start_token.column)
    
    def _parse_for(self) -> Optional[ForNode]:
        """Parse a for loop directive."""
        start_token = self._advance()
        
        # Parse attributes
        item = ""
        collection = ""
        key = ""
        
        header = []
        while not self._is_at_end():
            token = self._peek()
            
            if token.type == TokenType.ATTRIBUTE_NAME:
                self._advance()
                header.append(token.value)
            
            elif token.type == TokenType.ATTRIBUTE_VALUE:
                header.append(self._advance().value)
            
            else:
                break

        # Support both `<for item in items>` and HTML-style named
        # attributes such as `<for key="id" item="item" in="items">`.
        if len(header) >= 2 and len(header) % 2 == 0 and all(
            header[index] in ("item", "collection", "in", "key")
            for index in range(0, len(header), 2)
        ):
            for index in range(0, len(header), 2):
                name, value = header[index], header[index + 1]
                if name == "item":
                    item = value
                elif name in ("collection", "in"):
                    collection = value
                elif name == "key":
                    key = value
        elif len(header) >= 3 and header[1] == "in":
            item, collection = header[0], header[2]
            if len(header) >= 5 and header[3] == "key":
                key = header[4]
        else:
            for index, value in enumerate(header):
                if value in ("item", "collection", "in", "key") and index + 1 < len(header):
                    if value == "item":
                        item = header[index + 1]
                    elif value in ("collection", "in"):
                        collection = header[index + 1]
                    elif value == "key":
                        key = header[index + 1]

        children = self._parse_nodes({TokenType.FOR_END, TokenType.EOF})
        if self._peek().type == TokenType.FOR_END:
            self._advance()
        else:
            self.errors.append("Missing closing </for>")
        return ForNode(item, collection, key, children, start_token.line, start_token.column)
    
    def _parse_if(self) -> Optional[IfNode]:
        """Parse an if directive."""
        start_token = self._advance()
        condition = ""
        
        # Parse condition
        while not self._is_at_end():
            token = self._peek()
            
            if token.type == TokenType.ATTRIBUTE_NAME:
                self._advance()
                attr_name = token.value
                if not condition and attr_name not in ("condition", "test"):
                    condition = attr_name
                if attr_name == "condition" or attr_name == "test":
                    if self._peek().type == TokenType.ATTRIBUTE_VALUE:
                        value_token = self._advance()
                        condition = value_token.value
            
            elif token.type == TokenType.ATTRIBUTE_VALUE:
                self._advance()
                condition = token.value
            else:
                break

        children = self._parse_nodes({TokenType.ELSE, TokenType.IF_END, TokenType.EOF})
        else_children = []

        if self._peek().type == TokenType.ELSE:
            self._advance()
            else_children = self._parse_nodes({TokenType.IF_END, TokenType.EOF})
                
        if self._peek().type == TokenType.IF_END:
            self._advance()
        else:
            self.errors.append("Missing closing </if>")
        return IfNode(condition, children, else_children, start_token.line, start_token.column)
    
    def _create_element(self, tag: str, attributes: dict, events: List[EventNode],
                        bindings: List[BindingNode], children: List[ASTNode],
                        transitions: List['TransitionDirectiveNode'] = None) -> ElementNode:
        """Create an element node with all attributes."""
        element = ElementNode(tag, attributes, events, bindings, children)
        element.transitions = transitions or []
        return element
    
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
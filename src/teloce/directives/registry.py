"""
Directive registry for managing and resolving directives.
"""

from typing import Optional, Dict, List, Any
from teloce.directives.base import Directive, DirectiveType, DirectiveContext, DirectiveHandler


class DirectiveRegistry:
    """
    Registry for all directives.
    """
    
    def __init__(self):
        self._directives: Dict[str, Directive] = {}
        self._by_type: Dict[DirectiveType, List[Directive]] = {
            DirectiveType.EVENT: [],
            DirectiveType.BIND: [],
            DirectiveType.CONDITIONAL: [],
            DirectiveType.LOOP: [],
            DirectiveType.SLOT: [],
            DirectiveType.COMPONENT: [],
            DirectiveType.CUSTOM: [],
        }
        self._handler = DirectiveHandler()
    
    def register(self, directive: Directive):
        """Register a directive."""
        self._directives[directive.name] = directive
        self._by_type[directive.type].append(directive)
        self._handler.register(directive)
    
    def get(self, name: str) -> Optional[Directive]:
        """Get a directive by name."""
        return self._directives.get(name)
    
    def get_by_type(self, type: DirectiveType) -> List[Directive]:
        """Get directives by type."""
        return self._by_type.get(type, [])
    
    def has(self, name: str) -> bool:
        """Check if a directive exists."""
        return name in self._directives
    
    def process(self, name: str, value: str, context: DirectiveContext) -> Optional[str]:
        """Process a directive."""
        return self._handler.process(name, value, context)
    
    def register_builtin(self):
        """Register all built-in directives."""
        from teloce.directives.events import EventDirective
        from teloce.directives.model import ModelDirective
        from teloce.directives.bind import BindDirective
        from teloce.directives.show import ShowDirective
        from teloce.directives.if_ import IfDirective
        from teloce.directives.for_ import ForDirective
        from teloce.directives.advanced import (
            VirtualForDirective, MemoDirective, ScrollyDirective, StepDirective,
            AnnotationDirective, PollDirective, LiveDirective, UseDirective,
        )
        
        self.register(EventDirective())
        self.register(ModelDirective())
        self.register(BindDirective())
        self.register(ShowDirective())
        self.register(IfDirective())
        self.register(ForDirective())
        for directive in (
            VirtualForDirective(), MemoDirective(), ScrollyDirective(),
            StepDirective(), AnnotationDirective(), PollDirective(),
            LiveDirective(), UseDirective(),
        ):
            self.register(directive)
    
    def clear(self):
        """Clear all directives."""
        self._directives.clear()
        for list in self._by_type.values():
            list.clear()

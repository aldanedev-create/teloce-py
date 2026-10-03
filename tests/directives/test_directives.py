"""
Tests for the directives module.
"""

import pytest

from teloce.directives.base import Directive, DirectiveType, DirectiveContext
from teloce.directives.registry import DirectiveRegistry
from teloce.directives.events import EventDirective
from teloce.directives.model import ModelDirective
from teloce.directives.bind import BindDirective
from teloce.directives.show import ShowDirective
from teloce.directives.if_ import IfDirective, ElseDirective
from teloce.directives.for_ import ForDirective


class TestDirectives:
    """Tests for directives."""

    def test_event_directive(self):
        """Test event directive."""
        directive = EventDirective()
        context = DirectiveContext()
        
        # Valid event
        result = directive.validate("handleClick", context)
        assert len(result) == 0
        
        # Empty event
        result = directive.validate("", context)
        assert len(result) > 0

    def test_model_directive(self):
        """Test model directive."""
        directive = ModelDirective()
        context = DirectiveContext()
        
        # Valid model
        result = directive.validate("username", context)
        assert len(result) == 0
        
        # Empty model
        result = directive.validate("", context)
        assert len(result) > 0

    def test_bind_directive(self):
        """Test bind directive."""
        directive = BindDirective()
        context = DirectiveContext()
        
        # Valid bind
        result = directive.validate("className", context)
        assert len(result) == 0
        
        # Empty bind
        result = directive.validate("", context)
        assert len(result) > 0

    def test_show_directive(self):
        """Test show directive."""
        directive = ShowDirective()
        context = DirectiveContext()
        
        # Valid show
        result = directive.validate("isVisible", context)
        assert len(result) == 0
        
        # Empty show
        result = directive.validate("", context)
        assert len(result) > 0

    def test_if_directive(self):
        """Test if directive."""
        directive = IfDirective()
        context = DirectiveContext()
        
        # Valid if
        result = directive.validate("isLoggedIn", context)
        assert len(result) == 0
        
        # Empty if
        result = directive.validate("", context)
        assert len(result) > 0

    def test_else_directive(self):
        """Test else directive."""
        directive = ElseDirective()
        context = DirectiveContext()
        
        # Valid else (no condition)
        result = directive.validate("", context)
        assert len(result) == 0
        
        # Invalid else (with condition)
        result = directive.validate("something", context)
        assert len(result) > 0

    def test_for_directive(self):
        """Test for directive."""
        directive = ForDirective()
        context = DirectiveContext()
        
        # Valid for
        result = directive.validate("item in items key id", context)
        assert len(result) == 0
        
        # Invalid for
        result = directive.validate("", context)
        assert len(result) > 0

    def test_registry(self):
        """Test directive registry."""
        registry = DirectiveRegistry()
        
        # Register a directive
        directive = EventDirective()
        registry.register(directive)
        
        assert registry.has('event')
        assert registry.get('event') is not None

    def test_register_builtin_is_idempotent(self):
        registry = DirectiveRegistry()

        registry.register_builtin()
        registry.register_builtin()

        names = [item.name for item in registry.get_by_type(DirectiveType.CUSTOM)]
        assert len(names) == len(set(names))

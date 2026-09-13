"""
Tests for the components module.
"""

import pytest

from teloce.components.registry import ComponentRegistry
from teloce.components.resolver import ComponentResolver
from teloce.components.imports import ComponentImporter
from teloce.components.dependency_graph import DependencyGraph


class TestComponents:
    """Tests for the components module."""

    def test_registry(self):
        """Test component registry."""
        registry = ComponentRegistry()
        registry.register("MyComponent", {"name": "MyComponent"})
        
        assert registry.has("MyComponent")
        assert registry.get("MyComponent") == {"name": "MyComponent"}

    def test_registry_alias(self):
        """Test component registry alias."""
        registry = ComponentRegistry()
        registry.register("MyComponent", {"name": "MyComponent"})
        registry.register_alias("MC", "MyComponent")
        
        assert registry.has("MC")
        assert registry.get("MC") == {"name": "MyComponent"}

    def test_resolver(self):
        """Test component resolver."""
        resolver = ComponentResolver()
        resolver.register("MyComponent", {"name": "MyComponent"})
        
        assert resolver.has("MyComponent")
        assert resolver.resolve("MyComponent") == {"name": "MyComponent"}

    def test_importer(self):
        """Test component importer."""
        importer = ComponentImporter()
        importer.add_import("MyComponent", "./components/MyComponent.vel")
        
        assert importer.get_import("MyComponent") == "./components/MyComponent.vel"

    def test_importer_parses_aliases_and_namespace_imports(self):
        """Import metadata uses the local binding developers actually use."""
        importer = ComponentImporter()

        assert importer.parse_import(
            'import { Button as PrimaryButton, Card } from "./ui.vel";'
        ) is None
        assert importer.get_import("PrimaryButton") == "./ui.vel"
        assert importer.get_import("Card") == "./ui.vel"
        assert importer.parse_import(
            'import * as Icons from "./icons.vel";'
        ) == ("Icons", "./icons.vel")
        assert importer.get_component("Icons") == "./icons.vel"

    def test_dependency_graph(self):
        """Test dependency graph."""
        graph = DependencyGraph()
        graph.add_component("A")
        graph.add_component("B")
        graph.add_dependency("A", "B")
        
        assert "B" in graph.get_dependencies("A")
        assert "A" in graph.get_dependents("B")

    def test_dependency_graph_cycle(self):
        """Test dependency graph cycle detection."""
        graph = DependencyGraph()
        graph.add_dependency("A", "B")
        graph.add_dependency("B", "A")
        
        has_cycle, cycle = graph.has_cycle()
        assert has_cycle is True

    def test_dependency_graph_topological(self):
        """Test dependency graph topological order."""
        graph = DependencyGraph()
        graph.add_dependency("A", "B")
        graph.add_dependency("A", "C")
        graph.add_dependency("B", "D")
        
        order = graph.get_topological_order()
        # D should come before B, B and C before A
        assert order.index("D") < order.index("B")
        assert order.index("B") < order.index("A")
        assert order.index("C") < order.index("A")

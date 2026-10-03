"""
Component resolver - resolves component references.

Handles component resolution from imports and registry.
"""

from typing import Optional, Dict, Any, List, Set
from pathlib import Path
import importlib


class ComponentResolver:
    """
    Resolves component references to their implementations.
    """
    
    def __init__(self):
        self.registry: Dict[str, Any] = {}
        self.aliases: Dict[str, str] = {}
        self.paths: List[str] = []
    
    def register(self, name: str, component: Any, alias: Optional[str] = None):
        """
        Register a component.
        
        Args:
            name: The component name
            component: The component implementation
            alias: Optional alias for the component
        """
        self.registry[name] = component
        if alias:
            self.aliases[alias] = name
    
    def resolve(self, name: str) -> Optional[Any]:
        """
        Resolve a component by name.
        
        Args:
            name: The component name
            
        Returns:
            The component implementation or None if not found.
        """
        # Check aliases
        if name in self.aliases:
            name = self.aliases[name]
        
        return self.registry.get(name)
    
    def resolve_import(self, import_path: str, component_name: str) -> Optional[Any]:
        """
        Resolve a component from an import path.
        
        Args:
            import_path: The import path
            component_name: The component name
            
        Returns:
            The component implementation or None if not found.
        """
        # Check if it's a relative import
        if import_path.startswith('.'):
            # Relative import - resolve from file system
            return self._resolve_relative_import(import_path, component_name)
        
        # Check if it's a package import
        return self._resolve_package_import(import_path, component_name)
    
    def _resolve_relative_import(self, import_path: str, component_name: str) -> Optional[Any]:
        """Resolve a relative import."""
        relative = import_path.lstrip('.').replace('/', '.')
        for base in self.paths:
            candidate = Path(base) / import_path.lstrip('./')
            candidates = [
                candidate,
                candidate.with_suffix('.py'),
                candidate.with_suffix('.vel'),
                candidate.with_suffix('.html'),
            ]
            for path in candidates:
                if path.exists() and path.suffix == '.py':
                    module_name = '.'.join(path.with_suffix('').parts)
                    try:
                        module = importlib.import_module(module_name)
                        return getattr(module, component_name, None)
                    except (ImportError, AttributeError):
                        continue
                if path.exists() and path.suffix in {'.vel', '.html'}:
                    return path
        return None
    
    def _resolve_package_import(self, import_path: str, component_name: str) -> Optional[Any]:
        """Resolve a package import."""
        module_name = import_path.replace('/', '.')
        try:
            module = importlib.import_module(module_name)
            return getattr(module, component_name, None)
        except (ImportError, AttributeError):
            return None
    
    def add_path(self, path: str):
        """Add a path to the resolver search paths."""
        self.paths.append(path)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all registered components."""
        return self.registry.copy()
    
    def has(self, name: str) -> bool:
        """Check if a component is registered."""
        return name in self.registry or name in self.aliases

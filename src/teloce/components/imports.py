"""
Component importer - handles component imports.

Manages import statements and component resolution.
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


class ComponentImporter:
    """
    Handles component imports and resolution.
    """
    
    def __init__(self):
        self.imports: Dict[str, str] = {}  # alias -> source
        self.components: Dict[str, str] = {}  # name -> source
        self.import_lines: List[str] = []
    
    def parse_import(self, line: str) -> Optional[Tuple[str, str]]:
        """
        Parse an import statement.
        
        Args:
            line: The import line
            
        Returns:
            A tuple of (name, source) or None.
        """
        line = line.strip().rstrip(';').strip()

        # Namespace import: import * as X from 'source'
        namespace_match = re.match(
            r'import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\s+[\'"]([^\'"]+)[\'"]$',
            line,
        )
        if namespace_match:
            name, source = namespace_match.groups()
            self.imports[name] = source
            self.components[name] = source
            return (name, source)

        # Default imports may be combined with named imports.  Keep the local
        # alias as the key so ``import Widget as``-style named bindings resolve
        # to the identifier developers actually use in templates/scripts.
        default_match = re.match(
            r'import\s+([A-Za-z_$][\w$]*)(?:\s*,\s*\{([^}]*)\})?\s+from\s+[\'"]([^\'"]+)[\'"]$',
            line,
        )
        if default_match:
            name, named, source = default_match.groups()
            self.imports[name] = source
            self.components[name] = source
            if named:
                self._record_named_imports(named, source)
            return (name, source)
        
        # Named import: import { X, Y } from 'source'
        named_match = re.match(
            r'import\s*\{([^}]+)\}\s*from\s+[\'"]([^\'"]+)[\'"]$',
            line,
        )
        if named_match:
            names_str = named_match.group(1)
            source = named_match.group(2)
            self._record_named_imports(names_str, source)
            return None
        return None

    def _record_named_imports(self, names: str, source: str) -> None:
        """Record named imports using their local aliases when present."""
        for name_part in names.split(','):
            pieces = re.split(r'\s+as\s+', name_part.strip(), maxsplit=1)
            imported = pieces[0].strip()
            local = pieces[-1].strip()
            if imported and re.fullmatch(r'[A-Za-z_$][\w$]*', local):
                self.imports[local] = source
                self.components[local] = source
    
    def add_import(self, name: str, source: str):
        """Add an import."""
        self.imports[name] = source
        self.components[name] = source
    
    def get_import(self, name: str) -> Optional[str]:
        """Get the import source for a name."""
        return self.imports.get(name)
    
    def get_component(self, name: str) -> Optional[str]:
        """Get the component source for a name."""
        return self.components.get(name)
    
    def generate_imports(self) -> str:
        """Generate import statements."""
        return '\n'.join(self.import_lines)
    
    def clear(self):
        """Clear all imports."""
        self.imports.clear()
        self.components.clear()
        self.import_lines.clear()
    
    def from_script(self, script: str) -> List[Tuple[str, str]]:
        """
        Extract imports from a script.
        
        Args:
            script: The script source code
            
        Returns:
            A list of (name, source) tuples.
        """
        imports = []
        
        # Keep this helper source-preserving and intentionally small: it is a
        # public import registry, not the compiler's JavaScript parser.  Parse
        # one import declaration per line and report every local binding.
        pattern = re.compile(r'(?m)^\s*import\b[^\n;]*(?:;|$)')
        for match in pattern.finditer(script):
            statement = match.group(0).strip()
            before = set(self.imports)
            parsed = self.parse_import(statement)
            if parsed:
                imports.append(parsed)
                before.add(parsed[0])
            for name in sorted(set(self.imports) - before):
                imports.append((name, self.imports[name]))

        return imports

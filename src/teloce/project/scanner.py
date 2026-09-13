"""
Project scanner - scans for .vel files in a project.

Discovers all .vel files and their locations.
"""

from pathlib import Path
from typing import List, Optional, Set, Dict, Any
import os
import fnmatch


class ProjectScanner:
    """
    Scans a project for .vel files.
    
    Discovers all .vel files in a project directory.
    """
    
    def __init__(self):
        self.vel_files: List[Path] = []
        self.ignored_patterns: Set[str] = {
            'node_modules',
            '.git',
            '__pycache__',
            'dist',
            'build',
            '.venv',
            'venv',
            'env',
            '.idea',
            '.vscode',
        }
    
    def scan(self, root_dir: str | Path, exclude_paths: Optional[List[str | Path]] = None) -> List[Path]:
        """
        Scan a directory for .vel files.
        
        Args:
            root_dir: The root directory to scan.
            
        Returns:
            A list of paths to .vel files.
        """
        root = Path(root_dir)
        self.vel_files = []
        
        if not root.exists():
            return []
        
        excluded = [Path(item).resolve() for item in (exclude_paths or [])]
        for path in sorted(root.rglob('*.vel'), key=lambda item: item.as_posix().lower()):
            resolved = path.resolve()
            if any(resolved == item or item in resolved.parents for item in excluded):
                continue
            if self._should_ignore(path):
                continue
            self.vel_files.append(path)
        
        return self.vel_files
    
    def scan_with_patterns(self, root_dir: str | Path, 
                           include: List[str] = None,
                           exclude: List[str] = None) -> List[Path]:
        """
        Scan a directory with custom include/exclude patterns.
        
        Args:
            root_dir: The root directory to scan.
            include: List of glob patterns to include.
            exclude: List of glob patterns to exclude.
            
        Returns:
            A list of paths to .vel files.
        """
        root = Path(root_dir)
        self.vel_files = []
        
        if not root.exists():
            return []
        
        include_patterns = include or ['**/*.vel']
        exclude_patterns = exclude or []
        
        seen: Set[Path] = set()
        for pattern in include_patterns:
            for path in sorted(root.glob(pattern), key=lambda item: item.as_posix().lower()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                if self._should_ignore(path, exclude_patterns):
                    continue
                seen.add(resolved)
                self.vel_files.append(path)

        self.vel_files.sort(key=lambda item: item.as_posix().lower())
        
        return self.vel_files
    
    def _should_ignore(self, path: Path, custom_exclude: List[str] = None) -> bool:
        """Check if a path should be ignored."""
        # Check default ignored patterns
        for pattern in self.ignored_patterns:
            if pattern in path.parts or fnmatch.fnmatch(path.name, pattern):
                return True
        
        # Check custom exclude patterns
        if custom_exclude:
            for pattern in custom_exclude:
                if fnmatch.fnmatch(str(path), pattern) or fnmatch.fnmatch(path.name, pattern):
                    return True
        
        return False
    
    def get_relative_paths(self, root_dir: str | Path) -> List[str]:
        """Get relative paths of .vel files."""
        root = Path(root_dir)
        return [p.relative_to(root).as_posix() for p in self.vel_files]
    
    def get_components(self) -> List[str]:
        """Get component names from .vel files."""
        components = []
        for path in self.vel_files:
            name = path.stem
            if name and name not in components:
                components.append(name)
        return components
    
    def group_by_directory(self) -> Dict[str, List[Path]]:
        """Group .vel files by directory."""
        groups = {}
        for path in self.vel_files:
            parent = str(path.parent)
            if parent not in groups:
                groups[parent] = []
            groups[parent].append(path)
        return groups

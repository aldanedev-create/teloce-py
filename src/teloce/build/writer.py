"""
File writer - writes compiled files to disk.

Handles writing JavaScript, CSS, and other files.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import os


class FileWriter:
    """
    Writes compiled files to disk.
    """
    
    def __init__(self):
        self.written_files: Dict[str, int] = {}
    
    def write_js(self, filepath: Path, content: str) -> None:
        """
        Write a JavaScript file.
        
        Args:
            filepath: The file path.
            content: The file content.
        """
        self._write_file(filepath, content)
    
    def write_css(self, filepath: Path, content: str) -> None:
        """
        Write a CSS file.
        
        Args:
            filepath: The file path.
            content: The file content.
        """
        self._write_file(filepath, content)
    
    def write_html(self, filepath: Path, content: str) -> None:
        """
        Write an HTML file.
        
        Args:
            filepath: The file path.
            content: The file content.
        """
        self._write_file(filepath, content)
    
    def write_json(self, filepath: Path, data: Dict[str, Any]) -> None:
        """
        Write a JSON file.
        
        Args:
            filepath: The file path.
            data: The JSON data.
        """
        import json
        self._write_file(filepath, json.dumps(data, indent=2))
    
    def _write_file(self, filepath: Path, content: str) -> None:
        """Write a file to disk."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode('utf-8')
        if not filepath.is_file() or filepath.read_bytes() != encoded:
            filepath.write_bytes(encoded)
        self.written_files[str(filepath)] = len(content)
    
    def copy_file(self, source: Path, dest: Path) -> None:
        """
        Copy a file.
        
        Args:
            source: The source file path.
            dest: The destination file path.
        """
        import shutil
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        self.written_files[str(dest)] = source.stat().st_size
    
    def get_written_files(self) -> Dict[str, int]:
        """Get all written files with their sizes."""
        return self.written_files.copy()
    
    def clear(self) -> None:
        """Clear the written files list."""
        self.written_files.clear()

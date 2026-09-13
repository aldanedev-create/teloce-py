"""
Manifest generator - generates build manifest.

Creates a manifest file describing the build output.
"""

from typing import Dict, Any, List
from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone


class ManifestGenerator:
    """
    Generates build manifest.
    """
    
    def __init__(self):
        self.manifest: Dict[str, Any] = {}
    
    def generate(self, build_result: Dict[str, Any], base_dir: str | Path | None = None) -> Dict[str, Any]:
        """
        Generate a build manifest.
        
        Args:
            build_result: The build result dictionary.
            
        Returns:
            The generated manifest.
        """
        manifest = {
            'version': '1.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_files': build_result.get('total', 0),
            'compiled': build_result.get('compiled', 0),
            'failed': build_result.get('failed', 0),
            'assets_copied': build_result.get('assets_copied', 0),
            'asset_map': build_result.get('asset_map', {}),
            'files': [],
            'dependencies': build_result.get('dependencies', {}),
            'dependency_cycle': build_result.get('dependency_cycle'),
            'errors': build_result.get('errors', []),
            'mode': build_result.get('mode', 'production'),
            'total_bytes': build_result.get('total_bytes', 0),
            'asset_bytes': build_result.get('asset_bytes', 0),
            'asset_files': build_result.get('asset_files', []),
            'asset_aliases': build_result.get('asset_aliases', []),
            'size_warnings': build_result.get('size_warnings', []),
            'build_signature': build_result.get('build_signature'),
        }
        
        for file_info in build_result.get('files', []):
            file_manifest = {
                'input': file_info.get('input'),
                'output': file_info.get('output'),
                'size': file_info.get('size'),
                'source_hash': file_info.get('source_hash'),
            }
            
            # Add hash if file exists
            output = Path(file_info['output']) if file_info.get('output') else None
            if output and base_dir and not output.is_absolute():
                output = Path(base_dir) / output
            if output and output.exists():
                file_manifest['hash'] = self._get_file_hash(str(output))
            
            manifest['files'].append(file_manifest)
        
        self.manifest = manifest
        return manifest
    
    def _get_file_hash(self, filepath: str) -> str:
        """Get the SHA-256 hash of a file."""
        if not Path(filepath).exists():
            return ''
        
        with open(filepath, 'rb') as f:
            content = f.read()
            return hashlib.sha256(content).hexdigest()[:8]
    
    def get_manifest(self) -> Dict[str, Any]:
        """Get the current manifest."""
        return self.manifest
    
    def save(self, filepath: Path) -> None:
        """
        Save the manifest to a file.
        
        Args:
            filepath: The file path.
        """
        if not self.manifest:
            return
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2)

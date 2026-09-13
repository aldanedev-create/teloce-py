"""
Project configuration - manages project configuration.

Loads and manages configuration settings for the project.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import json
from copy import deepcopy


class ProjectConfiguration:
    """
    Manages project configuration.
    """
    
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.config_file: Optional[Path] = None
        self._defaults = {
            'compiler': {
                'source_maps': True,
                'minify': False,
                'dev': True,
                'target': 'es2020',
            },
            'build': {
                'out_dir': 'dist',
                'static_dir': 'static',
                'clean': True,
                'minify': True,
                'hash_assets': True,
                'extract_css': True,
                'shared_runtime': True,
                # Discover static/js/pages automatically. Set false for a
                # deliberately multi-page build or true to require a router.
                'spa': 'auto',
                'spa_mode': 'hash',
                'spa_base': '/',
                'spa_pages': None,
                'spa_router': None,
                'spa_routes': {},
                'lazy_components': [],
                'tree_shake': True,
                'bundler': 'teloce',
                'ssr': False,
                'static': False,
                'report': 'build-report.json',
            },
            'server': {
                'port': 5173,
                'host': 'localhost',
                'hmr': True,
            },
            'watch': {
                'enabled': True,
                'debounce': 300,
            },
        }
    
    def load(self, config_file: str | Path = None) -> Dict[str, Any]:
        """
        Load configuration from a file.
        
        Args:
            config_file: Path to the configuration file.
            
        Returns:
            The loaded configuration.
        """
        if config_file:
            self.config_file = Path(config_file)
        
        if not self.config_file:
            self.config = deepcopy(self._defaults)
            return self.config
        
        try:
            with open(self.config_file) as f:
                loaded_config = json.load(f)
            
            # Merge with defaults
            self.config = self._merge_configs(self._defaults, loaded_config)
            return self.config
        except Exception:
            self.config = deepcopy(self._defaults)
            return self.config
    
    def save(self, config_file: str | Path = None) -> bool:
        """
        Save configuration to a file.
        
        Args:
            config_file: Path to the configuration file.
            
        Returns:
            True if saved successfully, False otherwise.
        """
        if config_file:
            self.config_file = Path(config_file)
        
        if not self.config_file:
            return False
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception:
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        keys = key.split('.')
        target = self.config
        
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
    
    def _merge_configs(self, defaults: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two configurations."""
        result = deepcopy(defaults)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get_compiler_config(self) -> Dict[str, Any]:
        """Get compiler configuration."""
        return self.get('compiler', {})
    
    def get_build_config(self) -> Dict[str, Any]:
        """Get build configuration."""
        return self.get('build', {})
    
    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration."""
        return self.get('server', {})

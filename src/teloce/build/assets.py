"""
Asset manager - manages static assets.

Copies and manages assets for the build.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil
import os
import hashlib


class AssetManager:
    """
    Manages static assets.
    """
    
    def __init__(self, hash_assets: bool = False):
        self.copied_assets: List[str] = []
        self.hash_assets = hash_assets
        self.asset_map: Dict[str, str] = {}
        self.asset_extensions = {
            '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.ico', '.webp', '.woff', '.woff2', '.ttf', '.eot',
            '.mp3', '.mp4', '.webm', '.ogg', '.pdf', '.json',
            '.xml', '.txt', '.md',
        }
    
    def copy_assets(self, source_dir: str | Path, dest_dir: str | Path,
                    asset_directories: list[str | Path] | None = None) -> int:
        """
        Copy static assets to the build directory.
        
        Args:
            source_dir: The source directory.
            dest_dir: The destination directory.
            
        Returns:
            The number of assets copied.
        """
        source = Path(source_dir)
        dest = Path(dest_dir)
        self.copied_assets = []
        self.asset_map = {}
        
        if not source.exists():
            return 0
        
        # Create destination directory
        dest.mkdir(parents=True, exist_ok=True)
        
        # Copy assets from common asset directories, plus an explicitly
        # configured source directory such as ``client``. The latter matters
        # for projects whose authored static tree is not named ``static``.
        asset_dirs = [
            source / 'static',
            source / 'assets',
            source / 'public',
            source / 'media',
        ]
        for configured in asset_directories or []:
            candidate = source / Path(configured)
            try:
                candidate.resolve().relative_to(source.resolve())
            except (OSError, ValueError):
                continue
            if candidate not in asset_dirs:
                asset_dirs.append(candidate)
        
        for asset_dir in asset_dirs:
            if asset_dir.exists():
                # A common deployment layout uses ``public`` as both source
                # asset directory and build output.  Recursing into the same
                # directory would copy files onto themselves forever.
                try:
                    asset_path = asset_dir.resolve()
                    dest_path = dest.resolve()
                    if asset_path == dest_path or asset_path in dest_path.parents:
                        continue
                except OSError:
                    continue
                self._copy_directory(asset_dir, dest / asset_dir.name, source, dest)
        
        return len(self.copied_assets)
    
    def _copy_directory(self, source_dir: Path, dest_dir: Path, source_root: Path, dest_root: Path) -> None:
        """Copy a directory of assets."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        for item in source_dir.iterdir():
            if item.is_dir():
                self._copy_directory(item, dest_dir / item.name, source_root, dest_root)
            elif item.is_file():
                # Check if it's an asset file
                if self._is_asset(item):
                    dest_name = item.name
                    if self.hash_assets:
                        digest = hashlib.sha256(item.read_bytes()).hexdigest()[:8]
                        dest_name = f"{item.stem}.{digest}{item.suffix}"
                    dest_path = dest_dir / dest_name
                    shutil.copy2(item, dest_path)
                    self.copied_assets.append(str(dest_path))
                    self.asset_map[item.relative_to(source_root).as_posix()] = dest_path.relative_to(dest_root).as_posix()
    
    def _is_asset(self, file_path: Path) -> bool:
        """Check if a file is an asset."""
        # Check extension
        if file_path.suffix.lower() in self.asset_extensions:
            return True
        
        # Check common asset patterns
        if file_path.suffix.lower() == '.map':
            return True
        
        return False
    
    def copy_file(self, source: Path, dest: Path) -> bool:
        """
        Copy a single asset file.
        
        Args:
            source: The source file path.
            dest: The destination file path.
            
        Returns:
            True if copied, False otherwise.
        """
        if not source.exists():
            return False
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = dest
        if self.hash_assets:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
            target = dest.with_name(f"{dest.stem}.{digest}{dest.suffix}")
        shutil.copy2(source, target)
        self.copied_assets.append(str(target))
        self.asset_map[source.name] = target.name
        return True
    
    def get_copied_assets(self) -> List[str]:
        """Get the list of copied assets."""
        return self.copied_assets.copy()
    
    def clear(self) -> None:
        """Clear the copied assets list."""
        self.copied_assets = []
        self.asset_map = {}

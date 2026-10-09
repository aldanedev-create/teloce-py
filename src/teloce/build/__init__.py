"""
Build package for Teloce.

Provides build system for compiling .vel files.
"""

from teloce.build.builder import Builder
from teloce.build.writer import FileWriter
from teloce.build.manifest import ManifestGenerator
from teloce.build.assets import AssetManager
from teloce.build.bundler import ModuleBundler, BundleError
from teloce.build.minifyjs import MinifyJSBundler, TeloceMinifyJSAdapter
from teloce.build.esbuild import EsbuildBundler, EsbuildUnavailable


def build_project(root_dir, out_dir=None, options=None):
    """Compile a project's `.vel` files for a Python web-server startup.

    Raises ``RuntimeError`` when any component fails, preventing a server
    from starting with stale or incomplete frontend assets.
    """
    with Builder(options or {}) as builder:
        result = builder.build(root_dir, out_dir)
    if result.get("failed"):
        details = "\n".join(
            f"{item.get('file')}: {item.get('error')}"
            for item in result.get("errors", [])
        )
        raise RuntimeError(f"Teloce build failed:\n{details}")
    return result

__all__ = [
    "Builder",
    "FileWriter",
    "ManifestGenerator",
    "AssetManager",
    "ModuleBundler",
    "BundleError",
    "MinifyJSBundler",
    "TeloceMinifyJSAdapter",
    "EsbuildBundler",
    "EsbuildUnavailable",
    "build_project",
]

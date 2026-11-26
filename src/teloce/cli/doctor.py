"""
Doctor command - checks environment and configuration.

Checks the environment and project configuration for issues.
"""

import sys
import os
from typing import Any

from teloce.project.discovery import ProjectDiscovery
from teloce.project.configuration import ProjectConfiguration
from teloce.version import __version__


def doctor_command(args: Any) -> int:
    """
    Check environment and configuration.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    print("🔍 Teloce Doctor")
    print("=" * 40)
    
    verbose = args.verbose
    
    # Check Python version
    import sys
    python_version = sys.version_info
    print(f"🐍 Python Version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 9):
        print("   ❌ Python 3.9 or higher required")
    
    # Check Teloce version
    print(f"📦 Teloce Version: {__version__}")

    # Type checker (optional): tsgo, bundled with pytscheck
    from teloce.typecheck import checker_info

    checker = checker_info()
    if checker:
        print(f"🔎 Type checker: tsgo {checker['tsgo']} via pytscheck {checker['pytscheck']}")
    else:
        print("🔎 Type checker: not installed (pip install \"teloce-py[typecheck]\" on Python 3.11+)")
    
    # Discover project
    discovery = ProjectDiscovery()
    project_info = discovery.discover()
    
    print(f"📁 Project Root: {discovery.root_dir}")
    print(f"📄 Config File: {discovery.config_file or 'Not found'}")
    
    # Check directories
    static_dir = discovery.get_static_dir()
    templates_dir = discovery.get_templates_dir()
    js_dir = discovery.get_js_dir()
    
    print(f"📂 Static Dir: {static_dir or 'Not found'}")
    print(f"📂 Templates Dir: {templates_dir or 'Not found'}")
    print(f"📂 JS Dir: {js_dir or 'Not found'}")
    
    # Check configuration
    config = ProjectConfiguration()
    config.load()
    
    if discovery.config_file:
        print("✅ Configuration loaded")
        if verbose:
            import json
            print(json.dumps(config.config, indent=2))
    else:
        print("⚠️  No configuration file found (using defaults)")
    
    # Check .vel files
    if js_dir:
        import glob
        vel_files = list(js_dir.rglob('*.vel'))
        print(f"📄 .vel Files: {len(vel_files)}")
        if verbose and vel_files:
            for f in vel_files[:10]:
                print(f"   - {f.relative_to(discovery.root_dir)}")
            if len(vel_files) > 10:
                print(f"   ... and {len(vel_files) - 10} more")
    
    print()
    
    # Summary
    issues = []
    
    if not static_dir:
        issues.append("No static directory found")
    if not templates_dir:
        issues.append("No templates directory found")
    if not js_dir:
        issues.append("No JavaScript directory found")
    
    if issues:
        print("⚠️  Issues found:")
        for issue in issues:
            print(f"   - {issue}")
        return 1
    else:
        print("✅ All checks passed!")
        return 0
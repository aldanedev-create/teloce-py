"""
Dev command - starts the development server.

Starts a development server with hot reload and HMR.
"""

import sys
from pathlib import Path
from typing import Any, Dict

from teloce.project.discovery import ProjectDiscovery
from teloce.project.configuration import ProjectConfiguration
from teloce.watcher.watcher import FileWatcher, WatchEventType
from teloce.build.builder import Builder
from teloce.cli.server import start_dev_server


def dev_command(args: Any) -> int:
    """
    Start the development server.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    print("🐛 Teloce Development Server")
    print("=" * 40)
    
    # Discover project
    discovery = ProjectDiscovery()
    project_info = discovery.discover()
    
    print(f"📁 Project: {discovery.get_project_name()}")
    print(f"📂 Root: {discovery.root_dir}")
    
    # Load configuration
    config = ProjectConfiguration()
    config.load(discovery.config_file)
    
    # Get dev server config
    server_config = config.get_server_config()
    port = args.port if args.port is not None else server_config.get('port', 5173)
    host = args.host if args.host is not None else server_config.get('host', 'localhost')
    build_config = config.get_build_config()
    out_dir = build_config.get('out_dir', 'dist')
    output_dir = Path(out_dir) if Path(out_dir).is_absolute() else discovery.root_dir / out_dir
    hmr = not args.no_hmr and server_config.get('hmr', True)
    
    print(f"🌐 Server: http://{host}:{port}")
    print(f"🔄 HMR: {'Enabled' if hmr else 'Disabled'}")
    print()
    
    # Build initially
    print("📦 Building project...")
    builder = Builder({
        'dev': True,
        'source_maps': True,
        'clean': True,
        'static_dir': build_config.get('static_dir', 'static'),
        'spa': build_config.get('spa', 'auto'),
        'spa_mode': build_config.get('spa_mode', 'hash'),
        'spa_base': build_config.get('spa_base', '/'),
        'spa_pages': build_config.get('spa_pages'),
        'spa_router': build_config.get('spa_router'),
        'spa_routes': build_config.get('spa_routes', {}),
    })
    result = builder.build(discovery.root_dir, output_dir)
    if result['errors']:
        print(f"❌ Initial build failed: {len(result['errors'])} errors")
        return 1
    server = start_dev_server(host, port, output_dir, proxy_target=getattr(args, 'proxy', None), hmr=hmr)
    
    # Set up watcher
    if hmr:
        print("👀 Watching for changes...")
        watcher = FileWatcher()
        
        # Watch .vel files
        js_dir = discovery.get_js_dir()
        if js_dir:
            watcher.add_path(js_dir)
        
        # Watch templates
        templates_dir = discovery.get_templates_dir()
        if templates_dir:
            watcher.add_path(templates_dir)
        
        def on_change(event):
            print(f"📝 File changed: {event.path}")
            result = builder.build(discovery.root_dir, output_dir)
            if result['errors']:
                print(f"❌ Rebuild failed: {len(result['errors'])} errors")
                return
            server.notify_reload()
            print("✅ Rebuild complete")
        
        watcher.on_change(on_change)
    
    print()
    print("✅ Development server started!")
    print(f"📍 http://{host}:{port}")
    print()
    print("Press Ctrl+C to stop")
    
    try:
        # Start watcher
        if hmr:
            watcher.start()
        else:
            # Keep running
            import time
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
        print("\n🛑 Server stopped")
    
    return 0

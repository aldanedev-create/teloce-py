"""
Watch command - watches for changes and rebuilds.

Watches for file changes and rebuilds automatically.
"""

import sys
from pathlib import Path
from typing import Any

from teloce.project.discovery import ProjectDiscovery
from teloce.project.configuration import ProjectConfiguration
from teloce.watcher.watcher import FileWatcher, WatchEventType
from teloce.build.builder import Builder
from teloce.cli.server import start_dev_server


def watch_command(args: Any) -> int:
    """
    Watch for changes and rebuild.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    print("👀 Teloce Watch")
    print("=" * 40)
    
    # Discover project
    discovery = ProjectDiscovery()
    project_info = discovery.discover()
    
    print(f"📁 Project: {discovery.get_project_name()}")
    
    # Load configuration
    config = ProjectConfiguration()
    config.load(discovery.config_file)
    
    # Get watch config
    watch_config = config.get('watch', {})
    out_dir = args.out_dir if args.out_dir is not None else config.get_build_config().get('out_dir', 'dist')
    hmr = not args.no_hmr and watch_config.get('enabled', True)
    host = args.host if getattr(args, 'host', None) is not None else config.get_server_config().get('host', '127.0.0.1')
    port = args.port if getattr(args, 'port', None) is not None else config.get_server_config().get('port', 5173)
    output_dir = Path(out_dir) if Path(out_dir).is_absolute() else discovery.root_dir / out_dir
    
    print(f"📂 Output: {out_dir}")
    print(f"🔄 HMR: {'Enabled' if hmr else 'Disabled'}")
    print()
    
    # Build initially
    print("📦 Building project...")
    build_config = config.get_build_config()
    builder = Builder({
        'dev': True,
        'source_maps': True,
        'incremental': True,
        'clean': False,
        'static_dir': build_config.get('static_dir', 'static'),
        'spa': build_config.get('spa', 'auto'),
        'spa_mode': build_config.get('spa_mode', 'hash'),
        'spa_base': build_config.get('spa_base', '/'),
        'spa_pages': build_config.get('spa_pages'),
        'spa_router': build_config.get('spa_router'),
        'spa_routes': build_config.get('spa_routes', {}),
    })
    builder.build(discovery.root_dir, output_dir)
    server = start_dev_server(host, port, output_dir, proxy_target=getattr(args, 'proxy', None), hmr=hmr)
    print("✅ Initial build complete")
    print()
    
    # Set up watcher
    print("👀 Watching for changes...")
    watcher = FileWatcher({'debounce': watch_config.get('debounce', 300)})
    
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
        if not result['errors'] and hmr:
            server.notify_reload()
        if result['errors']:
            print(f"❌ Build failed: {len(result['errors'])} errors")
        else:
            print(f"✅ Rebuild complete ({result['compiled']} files)")
    
    watcher.on_change(on_change)
    
    print()
    print("Press Ctrl+C to stop")
    
    try:
        watcher.start()
    except KeyboardInterrupt:
        print("\n🛑 Watch stopped")
    
    watcher.stop()
    server.shutdown()
    server.server_close()
    return 0

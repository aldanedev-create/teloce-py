"""
Main CLI entry point.

Provides the command-line interface for Teloce.
"""

import sys
import argparse
from typing import Optional

from teloce.cli.dev import dev_command
from teloce.cli.build import build_command
from teloce.cli.watch import watch_command
from teloce.cli.debug import debug_command
from teloce.cli.doctor import doctor_command
from teloce.cli.lint import lint_command
from teloce.cli.create import create_command
from teloce.cli.benchmark import benchmark_command
from teloce.cli.compile import compile_command
from teloce.version import __version__


def main(args: Optional[list] = None) -> int:
    """
    Main CLI entry point.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    # Windows users often run the CLI with a legacy cp1252 console.  Teloce's
    # status output contains useful Unicode symbols, so make output reliable
    # without requiring users to set PYTHONIOENCODING themselves.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(
        prog='teloce',
        description='Teloce - A Python compiler for .vel Single File Components',
        epilog='For more information, visit https://teloce.dev'
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'Teloce-Py {__version__}'
    )
    
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to run',
        required=True
    )
    
    # Dev command
    dev_parser = subparsers.add_parser('dev', help='Start development server')
    dev_parser.add_argument(
        '-p', '--port',
        type=int,
        default=None,
        help='Port to run on (default: teloce.config.json or 5173)'
    )
    dev_parser.add_argument(
        '-H', '--host',
        default=None,
        help='Host to bind to (default: teloce.config.json or 127.0.0.1)'
    )
    dev_parser.add_argument(
        '--no-hmr',
        action='store_true',
        help='Disable hot module replacement'
    )
    dev_parser.add_argument(
        '--proxy',
        help='Proxy target URL'
    )
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build for production')
    build_parser.add_argument(
        '-o', '--out-dir',
        default=None,
        help='Output directory (default: teloce.config.json or dist)'
    )
    build_parser.add_argument(
        '--minify',
        action='store_true',
        help='Minify output'
    )
    build_parser.add_argument(
        '--no-minify',
        action='store_true',
        help='Disable minification'
    )
    build_parser.add_argument(
        '--source-map',
        action='store_true',
        help='Generate source maps'
    )

    compile_parser = subparsers.add_parser('compile', help='Compile one .vel component')
    compile_parser.add_argument('source', help='Path to a .vel file')
    compile_parser.add_argument('-o', '--output', help='JavaScript output path (default: next to source)')
    compile_parser.add_argument('--source-map', action='store_true', help='Write a source map')
    compile_parser.add_argument('--json', action='store_true', help='Print structured diagnostics as JSON')
    build_parser.add_argument(
        '--no-clean',
        action='store_true',
        help='Keep the existing output directory before building'
    )
    build_parser.add_argument(
        '--hash-assets',
        action='store_true',
        help='Add content hashes to generated JavaScript and CSS filenames'
    )
    build_parser.add_argument(
        '--no-hash-assets',
        action='store_true',
        help='Keep generated JavaScript and CSS filenames stable'
    )
    build_parser.add_argument(
        '--no-extract-css',
        action='store_true',
        help='Keep component CSS in JavaScript instead of extracting stylesheets'
    )
    build_parser.add_argument(
        '--bundle',
        action='store_true',
        help='Create a dependency-aware production ES module bundle'
    )
    build_parser.add_argument(
        '--bundler', choices=('teloce', 'esbuild'), default=None,
        help='Bundler backend: dependency-free Teloce or optional industrial esbuild',
    )
    build_parser.add_argument(
        '--no-splitting', action='store_true',
        help='Disable code splitting when using esbuild',
    )
    build_parser.add_argument(
        '--entry',
        help='Bundle entry module relative to the output directory'
    )
    build_parser.add_argument(
        '--report',
        nargs='?', const='build-report.json',
        help='Write a JSON bundle-size/build report (default: build-report.json)'
    )
    build_parser.add_argument(
        '--max-size',
        type=int,
        default=0,
        help='Warn when a generated file exceeds this many bytes'
    )
    build_parser.add_argument(
        '--ssr',
        action='store_true',
        help='Emit Jinax server-rendered HTML templates alongside browser modules'
    )
    build_parser.add_argument(
        '--static',
        action='store_true',
        help='Emit server-rendered Jinax HTML artifacts for static/server-only pages',
    )
    build_parser.add_argument(
        '--lazy-components',
        default=None,
        help='Comma-separated component names to emit as dynamic lazy chunks'
    )
    build_parser.add_argument(
        '--no-tree-shake',
        action='store_true',
        help='Keep unused local component imports in generated modules'
    )
    
    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Watch for changes and rebuild')
    watch_parser.add_argument(
        '-o', '--out-dir',
        default=None,
        help='Output directory (default: teloce.config.json or dist)'
    )
    watch_parser.add_argument(
        '--no-hmr',
        action='store_true',
        help='Disable hot module replacement'
    )
    watch_parser.add_argument('-p', '--port', type=int, default=None, help='Server port')
    watch_parser.add_argument('-H', '--host', default=None, help='Server host')
    watch_parser.add_argument('--proxy', help='Backend proxy target URL')
    
    # Debug command
    debug_parser = subparsers.add_parser('debug', help='Open debugger dashboard')
    debug_parser.add_argument(
        '-p', '--port',
        type=int,
        default=9000,
        help='Debugger port (default: 9000)'
    )
    debug_parser.add_argument(
        '-H', '--host',
        default='localhost',
        help='Debugger host (default: localhost)'
    )
    debug_parser.add_argument(
        '--no-open',
        action='store_true',
        help="Don't open browser automatically"
    )
    
    # Doctor command
    doctor_parser = subparsers.add_parser('doctor', help='Check environment and configuration')
    doctor_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show verbose output'
    )
    
    # Lint command
    lint_parser = subparsers.add_parser('lint', help='Lint Teloce templates')
    lint_parser.add_argument(
        '-f', '--fix',
        action='store_true',
        help='Fix linting issues'
    )
    lint_parser.add_argument(
        '--strict',
        action='store_true',
        help='Strict linting mode'
    )
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new Teloce project')
    create_parser.add_argument(
        'name',
        nargs='?',
        default='my-teloce-app',
        help='Project name'
    )

    benchmark_parser = subparsers.add_parser('benchmark', help='Benchmark .vel compilation')
    benchmark_parser.add_argument('root', nargs='?', default='.', help='Project root')
    benchmark_parser.add_argument('-n', '--iterations', type=int, default=1)
    benchmark_parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON')
    create_parser.add_argument(
        '-t', '--template',
        default='flask',
        help='Template to use (default: flask)'
    )
    create_parser.add_argument(
        '--no-install',
        action='store_true',
        help="Skip dependency installation"
    )
    create_parser.add_argument(
        '--no-git',
        action='store_true',
        help="Skip git initialization"
    )
    
    parsed_args = parser.parse_args(args)
    
    # Execute command
    command_map = {
        'dev': dev_command,
        'build': build_command,
        'watch': watch_command,
        'debug': debug_command,
        'doctor': doctor_command,
        'lint': lint_command,
        'create': create_command,
        'benchmark': benchmark_command,
        'compile': compile_command,
    }
    
    command_func = command_map.get(parsed_args.command)
    if command_func:
        return command_func(parsed_args)
    
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())

"""Compare identical generated Teloce entries with published MinifyJS and Node.

Usage: python scripts/benchmark_minifyjs.py --esbuild /path/to/esbuild
"""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from minifyjs import __version__
from teloce.build import build_project, MinifyJSBundler


def compare(esbuild):
    original = MinifyJSBundler.bundle
    rows = []
    for shared in (False, True):
        with tempfile.TemporaryDirectory(prefix='teloce-minify-bench-') as tmp:
            project = Path(tmp)
            source = Path(__file__).resolve().parents[1] / 'examples/flask/static/js/App.vel'
            (project / 'App.vel').write_text(source.read_text())
            def checked_bundle(backend, entry, output=None, **options):
                native = original(backend, entry, output, **options)
                node_out = project / 'node'
                subprocess.run([str(esbuild), str(entry), '--bundle', '--minify',
                    '--format=esm', '--target=es2020', '--charset=utf8', '--splitting',
                    '--entry-names=' + native.stem, '--chunk-names=chunks/[name]-[hash]',
                    '--outdir=' + str(node_out)], cwd=project, check=True, capture_output=True)
                node = node_out / native.name
                assert native.read_bytes() == node.read_bytes(), 'Node esbuild differs'
                raw_bytes = sum(item['bytes'] for item in backend.result.metafile['inputs'].values())
                size = native.stat().st_size
                rows.append({'shared_runtime':shared, 'minifyjs_version':__version__,
                    'input_graph_bytes':raw_bytes, 'minifyjs_bytes':size,
                    'node_esbuild_bytes':node.stat().st_size,
                    'gzip_bytes':len(gzip.compress(native.read_bytes(), mtime=0)),
                    'reduction_percent':round(100*(1-size/raw_bytes),2), 'byte_identical':True})
                return native
            with patch.object(MinifyJSBundler, 'bundle', checked_bundle):
                build_project(project, options={'bundle':True, 'bundler':'minifyjs',
                    'minifier':'minifyjs', 'minify':True, 'shared_runtime':shared,
                    'source_maps':False, 'extract_css':False, 'hash_assets':False})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--esbuild', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.esbuild.resolve()), indent=2))

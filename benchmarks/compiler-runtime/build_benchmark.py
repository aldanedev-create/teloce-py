"""Repeatable compiler workloads; run from a checkout with PYTHONPATH=src."""
import argparse
import json
import platform
from importlib.metadata import version
import statistics
import tempfile
import time
from pathlib import Path
from teloce.build.builder import Builder

SOURCE = '<template><p>{{ title }}</p></template><script lang="ts">import { label } from "./shared.ts"; export default { data() { return { title: label }; } };</script><style scoped>p { color: navy; }</style>'

def run(count, production=False):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / 'static'
        source.mkdir()
        shared = source / 'shared.ts'
        shared.write_text('export const label: string = "Hello";')
        for i in range(count):
            (source / f'Card{i}.html').write_text(SOURCE)
        builder = Builder({'dev': not production, 'production': production,
                           'html_mode': True, 'source_maps': production,
                           'minifier': 'minifyjs', 'static_dir': 'static',
                           'direct_dom_updates': True, 'clean': False})
        results = {}
        for name in ('cold', 'unchanged', 'component_edit', 'shared_ts_edit'):
            if name == 'component_edit':
                (source / 'Card0.html').write_text(SOURCE.replace('navy', 'green'))
            if name == 'shared_ts_edit':
                shared.write_text('export const label: string = "Updated";')
            start = time.perf_counter()
            result = builder.build(root)
            elapsed = time.perf_counter() - start
            assert not result['failed'], result['errors']
            results[name] = {'seconds': elapsed, 'compiled': result['compiled'],
                             'cache_hits': result['cache_hits'],
                             'output_bytes': sum(item['size'] for item in result['files'])}
        return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--sizes', type=int, nargs='+', default=[10, 100, 1000])
    args = parser.parse_args()
    report = {'python': platform.python_version(), 'platform': platform.platform(), 'minifyjs': version('minifyjs'), 'tree_sitter': version('tree-sitter'), 'runs': {}}
    for count in args.sizes:
        runs = [run(count) for _ in range(args.repeat)]
        report['runs'][str(count)] = {'raw': runs, 'median': {
            scenario: statistics.median(item[scenario]['seconds'] for item in runs)
            for scenario in runs[0]}}
    report['production_100'] = run(100, production=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value['median'] for key, value in report['runs'].items()}, indent=2))

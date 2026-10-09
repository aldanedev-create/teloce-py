"""Cache correctness across edits, deletions, languages and parallel workers."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from teloce.build.builder import Builder
from teloce.javascript.tree_sitter_backend import parse_tree


def test_sources_read_once_and_unchanged_outputs_keep_mtime(tmp_path, monkeypatch):
    source = tmp_path / 'static'; source.mkdir()
    component = source / 'App.html'
    component.write_text('<template><p>{{ name }}</p></template><script>export default { data() { return { name: "Ada" }; } };</script>')
    types = source / 'types.ts'; types.write_text('export type Name = string;')
    builder = Builder({'dev': True, 'html_mode': True, 'ssr': True, 'source_maps': False})
    reads = Counter(); original = Path.read_text
    def read(path, *args, **kwargs):
        if path in {component, types}: reads[path] += 1
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    result = builder.build(tmp_path); assert result['failed'] == 0
    assert reads == {component: 1, types: 1}
    outputs = [tmp_path / 'dist/static/App.js', tmp_path / 'dist/static/teloce-runtime.js', tmp_path / 'dist/static/signals.js']
    mtimes = [path.stat().st_mtime_ns for path in outputs]
    reads.clear(); result = builder.build(tmp_path)
    assert result['compiled'] == 0; assert reads == {component: 1, types: 1}
    assert mtimes == [path.stat().st_mtime_ns for path in outputs]


def test_transitive_component_and_typescript_dependencies(tmp_path):
    source = tmp_path / 'static'; source.mkdir()
    (source / 'shared.ts').write_text('export const label: string = "A";')
    (source / 'Leaf.html').write_text('<template><p>{{ label }}</p></template><script lang="ts">import { label } from "./shared.ts"; export default {data() { return {label}; }};</script>')
    (source / 'App.html').write_text('<template><Leaf /></template><script>import Leaf from "./Leaf.html"; export default {components: {Leaf}};</script>')
    options = {'dev': True, 'html_mode': True, 'source_maps': False}
    first = Builder(options).build(tmp_path); assert first['failed'] == 0
    (source / 'shared.ts').write_text('export const label: string = "B";')
    # A fresh Builder must reuse persisted dependency analysis safely.
    changed = Builder(options).build(tmp_path); assert changed['failed'] == 0
    assert changed['compiled'] == 3
    (source / 'Leaf.html').unlink()
    deleted = Builder(options).build(tmp_path)
    assert deleted['failed'] == 1
    assert any('Component import not found' in error['error'] for error in deleted['errors'])


def test_parser_languages_threads_and_tree_edit_isolation():
    sources = [('js', 'const name = "é";'), ('ts', 'const count: number = 1;'), ('tsx', 'const view = <p>Hello</p>;')]
    def parse(item):
        language, source = item
        program = parse_tree(source, language)
        assert not program.root_node.has_error
        return program
    with ThreadPoolExecutor(max_workers=4) as pool:
        programs = list(pool.map(parse, sources * 20))
    tree = parse_tree(sources[0][1]).tree
    tree.edit(start_byte=0, old_end_byte=0, new_end_byte=1, start_point=(0, 0), old_end_point=(0, 0), new_end_point=(0, 1))
    assert parse_tree(sources[0][1]).root_node.start_byte == 0
    assert programs[0].root_node.text == sources[0][1].encode()


def test_persistent_workers_receive_fresh_sources_and_close(tmp_path):
    source = tmp_path / 'static'; source.mkdir()
    path = source / 'App.html'
    path.write_text('<template><p>First</p></template>')
    options = {'dev': True, 'html_mode': True, 'source_maps': False, 'jobs': 2,
               'parallel_min_files': 1, 'persistent_workers': True}
    (source / 'Other.html').write_text('<template><p>Other</p></template>')
    with Builder(options) as builder:
        assert builder.build(tmp_path)['failed'] == 0
        pool = builder._pool
        path.write_text('<template><p>Second</p></template>')
        (source / 'Other.html').write_text('<template><p>Changed</p></template>')
        assert builder.build(tmp_path)['failed'] == 0
        assert builder._pool is pool
        assert 'Second' in (tmp_path / 'dist/static/App.js').read_text()
    assert builder._pool is None


def test_parallel_workers_support_spawn(tmp_path):
    import subprocess
    import sys
    source = tmp_path / 'static'; source.mkdir()
    for name in ('One', 'Two'):
        (source / f'{name}.html').write_text(f'<template><p>{name}</p></template>')
    script = tmp_path / 'spawn_check.py'
    script.write_text('''import multiprocessing
from pathlib import Path
from teloce.build import Builder
if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')
    with Builder({'dev': True, 'html_mode': True, 'source_maps': False,
                  'jobs': 2, 'parallel_min_files': 1, 'persistent_workers': True}) as builder:
        result = builder.build(Path(__file__).parent)
        assert not result['failed'], result['errors']
        assert builder._pool is not None
''')
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_dependency_resolution_reacts_to_added_files(tmp_path):
    source = tmp_path / 'static'; source.mkdir()
    (source / 'App.html').write_text('<template><p>App</p></template><script>import {label} from "./helper.js"; export default {};</script>')
    builder = Builder({'dev': True, 'html_mode': True, 'source_maps': False})
    first = builder.build(tmp_path); assert first['failed'] == 0
    # A JavaScript-facing import can resolve to a newly authored TS module.
    (source / 'helper.ts').write_text('export const label: string = "Hello";')
    result = builder.build(tmp_path); assert result['failed'] == 0
    assert result['dependencies']['static/App.html'] == ['static/helper.ts']
    (source / 'helper.ts').write_text('export const label: string = "Changed";')
    assert builder.build(tmp_path)['compiled'] == 2

"""Real published-wheel coverage for Teloce's native backend."""
import json
from pathlib import Path

import pytest
from minifyjs import Options, __version__
from teloce.build import Builder, MinifyJSBundler, TeloceMinifyJSAdapter, build_project


def test_adapter_preserves_path_and_public_exports(tmp_path):
    path = tmp_path / 'module.js'
    path.write_text('export function calculate(longParameter) { return longParameter + 1; }')
    adapter = TeloceMinifyJSAdapter(Options(compress=True, mangle=True, format='esm'))
    result = adapter.minify_file(path)
    assert adapter.output_name(path) == path
    assert 'calculate' in result.code and 'longParameter' not in result.code
    assert path.read_text() == result.code


def test_transform_composes_original_source_map():
    adapter = TeloceMinifyJSAdapter(Options(compress=True, mangle=True, format='esm'))
    result = adapter.transform('export const value = 42;', source_name='App.js', source_map={
        'version':3, 'sources':['App.vel'], 'sourcesContent':['<template>original</template>'],
        'names':[], 'mappings':'AAAA'})
    source_map = json.loads(result.map)
    assert source_map['sources'] == ['App.vel']
    assert source_map['sourcesContent'] == ['<template>original</template>']
    assert source_map['mappings']


@pytest.mark.parametrize('splitting', [False, True])
@pytest.mark.parametrize('hashed', [False, True])
def test_bundle_metadata_hashes_maps_and_lazy_import(tmp_path, splitting, hashed):
    (tmp_path / 'entry.js').write_text('export const load = () => import("./lazy.js");')
    (tmp_path / 'lazy.js').write_text('export const value = "lazy-value";')
    bundler = MinifyJSBundler(tmp_path)
    entry = bundler.bundle(tmp_path / 'entry.js', tmp_path / 'out/app.js',
                          splitting=splitting, hash_assets=hashed, minify=True, sourcemap=True)
    assert entry.is_file()
    assert entry.name.startswith('app-') if hashed else entry.name == 'app.js'
    files = bundler.result.output_files
    assert all(Path(item['path']).exists() for item in files)
    assert any(item['path'].endswith('.map') for item in files)
    assert any('/chunks/' in item['path'] for item in files) == splitting
    assert bundler.result.minified_bytes == sum(Path(item['path']).stat().st_size for item in files)
    assert 'sourceMappingURL=' in entry.read_text()


def test_define_drop_packages_and_tree_shaking(tmp_path):
    dep = tmp_path / 'node_modules/fixture';dep.mkdir(parents=True)
    (dep / 'package.json').write_text('{"main":"index.js"}')
    (dep / 'index.js').write_text('export const value = 42; export const unused = "UNUSED_SENTINEL";')
    (tmp_path / 'entry.js').write_text('import {value} from "fixture"; if(DEBUG) console.log("DEBUG_SENTINEL"); debugger; export const answer = value;')
    bundler = MinifyJSBundler(tmp_path)
    output = bundler.bundle(tmp_path / 'entry.js', minify=True, splitting=False,
                            define={'DEBUG':'false'}, drop=['debugger'])
    code = output.read_text()
    assert 'fixture' not in code and 'UNUSED_SENTINEL' not in code and 'DEBUG_SENTINEL' not in code and 'debugger' not in code
    output = bundler.bundle(tmp_path / 'entry.js', packages='external')
    assert 'fixture' in output.read_text()


def test_errors_are_reported_without_silent_fallback(tmp_path):
    (tmp_path / 'App.vel').write_text('<template><h1>Hello</h1></template><script>import missing from "./missing.js"; export default {mounted(){ console.log(missing); }};</script>')
    result = Builder({'bundle':True, 'shared_runtime':False}).build(tmp_path)
    assert result['failed'] and result['errors']


@pytest.mark.parametrize('shared', [False, True])
def test_production_build_updates_asset_map_and_report(tmp_path, shared):
    (tmp_path / 'App.vel').write_text('<template><button @click="increment">{{count}}</button></template><script>export default { data(){return {count:0};}, methods:{increment(){this.count++;}} };</script>')
    result = build_project(tmp_path, options={'mode':'production', 'bundle':True,
        'shared_runtime':shared, 'report':'report.json', 'source_maps':True})
    out = tmp_path / 'dist'
    assert result['bundler'] == 'minifyjs' and result['minifyjs_version'] == __version__
    assert result['asset_map']['App.js'] == result['bundle']
    assert (out / result['bundle']).exists()
    assert result['bundle_bytes'] == sum(item['size'] for item in result['bundle_outputs'])
    report = json.loads((out / 'report.json').read_text())
    manifest = json.loads((out / 'manifest.json').read_text())
    assert report['bundle_outputs'] == manifest['bundle_outputs'] == result['bundle_outputs']
    maps = [(out / item['output']) for item in result['bundle_outputs'] if item['output'].endswith('.map')]
    assert any(any('App.vel' in source for source in json.loads(p.read_text())['sources']) for p in maps)


def test_production_unbundled_map_is_composed(tmp_path):
    (tmp_path / 'App.vel').write_text('<template><h1>{{title}}</h1></template><script>export default {data(){return {title:"hello"};}};</script>')
    result = build_project(tmp_path, options={'mode':'production','source_maps':True,'hash_assets':False})
    source_map = json.loads((tmp_path / 'dist/App.js.map').read_text())
    assert source_map['sources'] == ['App.vel']
    assert source_map['mappings']


def test_authored_imports_use_hashed_files_without_rewriting_strings(tmp_path):
    from teloce.build.minifyjs import rewrite_module_paths
    source = 'import "./Lazy.js"; export * from "./Lazy.js"; const load=()=>import("./Lazy.js"); const label="./Lazy.js";'
    result = rewrite_module_paths(source, {'./Lazy.js':'./Lazy.123.js'})
    assert result.count('./Lazy.123.js') == 3
    assert 'label="./Lazy.js"' in result
    js = tmp_path / 'static/js';js.mkdir(parents=True)
    (js / 'App.vel').write_text('<template><h1>Hello</h1></template>')
    (js / 'Lazy.js').write_text('export const value=42;')
    (js / 'main.js').write_text('import {mount} from "./App.js"; mount("#app"); export const load=()=>import("./Lazy.js");')
    result = build_project(tmp_path, options={'mode':'production','bundle':True,
        'bundle_entry':'static/js/main.js','hash_assets':True})
    assert result['failed'] == 0
    assert any('/chunks/' in item['output'] for item in result['bundle_outputs'])

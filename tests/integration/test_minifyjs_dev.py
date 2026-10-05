"""Opt-in native development transforms, rebuilds and Flask output."""
import json
from pathlib import Path
import pytest
from teloce.build import Builder

SOURCE = '''<template><button @click="increment">{{count}}</button><h1>Hello dev</h1></template><script>export default {data(){return {count:0};},methods:{increment(){this.count++;}}};</script>'''

@pytest.mark.parametrize('shared', [False, True])
def test_native_dev_rebuild_and_maps(tmp_path, shared):
    js=tmp_path/'static/js'; js.mkdir(parents=True)
    component=js/'App.vel';component.write_text(SOURCE)
    builder=Builder({'dev':True,'minifier':'minifyjs','minify':False,
                     'source_maps':True,'shared_runtime':shared})
    assert not builder.native_adapter.default_options.compress
    assert not builder.native_adapter.default_options.mangle
    result=builder.build(tmp_path)
    assert not result['failed'],result['errors']
    output=tmp_path/'dist/static/js/App.js'
    initial=output.read_text()
    assert '\n' in initial and 'increment' in initial
    sm=json.loads(output.with_suffix('.js.map').read_text())
    assert any('App.vel' in name for name in sm['sources']) and sm['mappings']
    for i in range(3):
        component.write_text(SOURCE.replace('Hello dev',f'Edit {i}'))
        result=builder.build(tmp_path)
        assert not result['failed'],result['errors']
        assert f'Edit {i}' in output.read_text()
    from flask import Flask
    app=Flask(__name__,static_folder=str(tmp_path/'dist/static'))
    response=app.test_client().get('/static/js/App.js')
    assert response.status_code==200 and b'Edit 2' in response.data
    assert app.test_client().get('/static/js/App.js.map').status_code==200


def test_default_dev_backend_unchanged():
    assert Builder({'dev':True}).options['minifier']=='teloce'

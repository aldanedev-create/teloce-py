import asyncio
import json
import pytest

from jinja2 import Environment

from teloce.ssr import render_ssr, to_jinax_template
from teloce.build.builder import Builder


def test_teloce_template_translates_to_jinax_directives():
    result = to_jinax_template('<ul><li v-for="item in items" v-if="item.visible">{{ item.name }}</li></ul>')
    assert "{% for item in items %}" in result
    assert "{% if item.visible %}" in result
    assert "v-for" not in result


def test_jinax_renders_teloce_template_server_side():
    pytest.importorskip('flaxon.jinax', reason='optional Flaxon adapter requires Python >=3.11')
    html = asyncio.run(render_ssr('<h1>{{ title }}</h1><p v-if="visible">Ready</p>', {"title": "Teloce", "visible": True}))
    assert html == '<h1>Teloce</h1><p>Ready</p>'


def test_ssr_accepts_a_framework_owned_jinja_compatible_engine():
    html = asyncio.run(render_ssr('<h1>{{ title }}</h1>', {"title": "Flask"}, engine=Environment()))
    assert html == '<h1>Flask</h1>'


def test_ssr_accepts_a_framework_owned_async_render_adapter():
    class AsyncAdapter:
        async def render(self, template, values):
            return f"<h1>{values['title']}</h1>"

    html = asyncio.run(render_ssr('<h1>{{ title }}</h1>', {"title": "FastAPI"}, engine=AsyncAdapter()))
    assert html == '<h1>FastAPI</h1>'


def test_static_build_emits_jinax_artifact_and_static_manifest(tmp_path):
    source_dir = tmp_path / 'static' / 'js'
    source_dir.mkdir(parents=True)
    (source_dir / 'App.vel').write_text('<template><h1>{{ title }}</h1></template>', encoding='utf-8')
    result = Builder({'static': True, 'ssr': True, 'clean': True}).build(tmp_path)
    assert result['mode'] == 'static'
    assert (tmp_path / 'dist' / 'static' / 'js' / 'App.html').is_file()
    manifest = json.loads((tmp_path / 'dist' / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['mode'] == 'static'

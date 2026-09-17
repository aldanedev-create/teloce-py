import json
import subprocess
from pathlib import Path

from teloce.build.builder import Builder
from teloce.compiler.compiler import compile as compile_component
from teloce.ssr import render_static_component


FEATURE_SOURCE = '''
<template>
  <section v-scrolly>
    <article v-step="one" v-memo="activeStep">{{ activeStep | number }}</article>
    <div v-virtual-for="row in rows" :key="row.id" item-height="32" overscan="2">{{ row.name }}</div>
    <div v-data-table="{ rows: rows, columns: columns, pageSize: 5 }"></div>
    <div v-chart-annotation="{ text: note, x: 50 }" use:focusPanel="{ label: note }"></div>
    <output poll="/api/stats" interval="10000" poll-target="stats"></output>
    <output live="feed" live-target="stats"></output>
  </section>
</template>
<script>
function focusPanel(node, params) { return { update() {}, destroy() {} }; }
export default {
  data() { return { rows: [], columns: [], activeStep: 1, note: "ready", stats: {} }; },
  queryState: { activeStep: { type: "number", key: "step" } }
};
</script>
'''


def test_advanced_features_compile_and_are_diagnosed():
    result = compile_component(FEATURE_SOURCE, filename="Feature.vel", source_maps=False)
    assert result["success"], result["diagnostics"]
    code = result["code"]
    assert "data-teloce-memo" in code
    assert 'data-teloce-memo=\\"{{ activeStep }}\\"' in code
    assert "<virtual-for" in code
    assert "data-teloce-data-table" in code
    assert "data-teloce-chart-annotation" in code
    assert 'queryState: { activeStep' in code
    assert 'const __actions' in code


def test_virtual_for_without_key_gets_a_source_diagnostic():
    result = compile_component(
        "<template><div v-virtual-for=\"row in rows\">{{ row }}</div></template>",
        filename="NoKey.vel",
        source_maps=False,
    )
    warnings = result["diagnostics"]["warnings"]
    assert any(item["code"] == "W2001" for item in warnings)


def test_shared_build_emits_manifest_runtime_data_modules_and_deduped_css(tmp_path: Path):
    source = tmp_path / "static" / "js"
    source.mkdir(parents=True)
    (source / "App.vel").write_text(FEATURE_SOURCE, encoding="utf-8")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "index.html").write_text(
        '<main id="app"></main><script type="module" src="/static/js/App.js"></script>',
        encoding="utf-8",
    )
    result = Builder({"dev": True, "clean": True, "source_maps": False}).build(tmp_path)
    assert result["failed"] == 0, result["errors"]
    assert (tmp_path / "dist" / "static" / "data.js").exists()
    assert (tmp_path / "dist" / "static" / "table.js").exists()
    manifest = json.loads((tmp_path / "dist" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["components"]["App"]["source"] == "static/js/App.vel"
    app = tmp_path / "dist" / "static" / "js" / "App.js"
    checked = subprocess.run(["node", "--check", str(app)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


class FakeEnvironment:
    def from_string(self, source):
        class Template:
            def render(self, **context):
                # This fake engine intentionally proves that child props were
                # translated into template context rather than JS execution.
                assert "{% with title='Hello' %}" in source
                return "<article>Hello</article>"

        return Template()


def test_static_component_expansion_is_allow_listed_and_does_not_run_script():
    import asyncio

    result = asyncio.run(render_static_component(
        '<template><Card title="Hello" /></template><script>raiseIfExecuted()</script>',
        components={"Card": '<template><article>{{ title }}</article></template><script>bad()</script>'},
        engine=FakeEnvironment(),
    ))
    assert result == "<article>Hello</article>"

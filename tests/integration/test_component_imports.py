"""Production-style nested `.vel` component build tests."""

import subprocess
import tempfile
from pathlib import Path

from teloce.build.builder import Builder
from teloce.build.bundler import BundleError, ModuleBundler
from teloce.compiler.compiler import compile as compile_component


PARENT = '''
<template><section><Child /></section></template>
<script>
import Child from "./components/Child.vel";
export default { name: "Parent", components: { Child } };
</script>
'''

CHILD = '''
<template><article class="child">{{ message }}</article></template>
<script>export default { data() { return { message: "Loaded child" }; } };</script>
<style scoped>.child { color: purple; }</style>
'''


def test_nested_vel_components_are_resolved_and_mounted():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        parent = root / "static" / "js" / "App.vel"
        child = root / "static" / "js" / "components" / "Child.vel"
        child.parent.mkdir(parents=True)
        parent.write_text(PARENT, encoding="utf-8")
        child.write_text(CHILD, encoding="utf-8")

        result = Builder({"dev": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        assert result["compiled"] == 2
        assert result["dependencies"]["static/js/App.vel"] == ["static/js/components/Child.vel"]
        manifest = (root / "dist" / "manifest.json").read_text(encoding="utf-8")
        assert "static/js/components/Child.vel" in manifest

        parent_js = root / "dist" / "static" / "js" / "App.js"
        child_js = root / "dist" / "static" / "js" / "components" / "Child.js"
        parent_code = parent_js.read_text(encoding="utf-8")
        assert 'import Child from "./components/Child.js";' in parent_code
        assert '"Child": Child' in parent_code
        assert "__teloceCreateCompiledComponent" in parent_code
        assert "__readProps" not in parent_code
        assert child_js.exists()

        for generated in (parent_js, child_js):
            checked = subprocess.run(["node", "--check", str(generated)], capture_output=True, text=True)
            assert checked.returncode == 0, checked.stderr


def test_missing_vel_component_import_fails_the_build():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text(PARENT, encoding="utf-8")

        result = Builder().build(root)
        assert result["failed"] == 1
        assert result["compiled"] == 0
        assert "Component import not found" in result["errors"][0]["error"]


def test_production_build_can_clean_and_hash_assets():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text("<template><div>Release</div></template>", encoding="utf-8")
        stale = root / "dist" / "old.js"
        stale.parent.mkdir(parents=True)
        stale.write_text("stale", encoding="utf-8")

        result = Builder({"clean": True, "hash_assets": True, "minify": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        assert not stale.exists()
        generated = list((root / "dist" / "static" / "js").glob("App.*.js"))
        assert len(generated) == 1
        assert generated[0].stem.startswith("App.")


def test_release_build_extracts_shared_component_glue_and_styles(tmp_path: Path):
    source_dir = tmp_path / "static" / "js"
    source_dir.mkdir(parents=True)
    (source_dir / "Child.vel").write_text(
        '<template><button @click="$emit(\'press\')">{{ label }}</button></template>'
        '<script>export default { props: { label: { default: "Child" } } };</script>'
        '<style scoped>button { color: purple; }</style>',
        encoding="utf-8",
    )
    (source_dir / "App.vel").write_text(
        '<template><main><Child label="Ready" /></main></template>'
        '<script>import Child from "./Child.vel"; export default {};</script>'
        '<style scoped>main { padding: 1rem; }</style>',
        encoding="utf-8",
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "index.html").write_text(
        '<!doctype html><html><head></head><body><div id="app"></div>'
        '<script type="module" src="/static/js/App.js"></script></body></html>',
        encoding="utf-8",
    )

    result = Builder({"mode": "production", "source_maps": False}).build(tmp_path)

    assert result["failed"] == 0, result["errors"]
    runtime = next((tmp_path / "dist" / "static").glob("teloce-runtime.*.js"))
    generated = list((tmp_path / "dist" / "static" / "js").glob("*.js"))
    app = next(path for path in generated if path.name.startswith("App."))
    css = list((tmp_path / "dist" / "static" / "js").glob("*.css"))
    assert runtime.exists()
    assert app.stat().st_size < 10_000
    assert "__teloceCreateCompiledComponent" in app.read_text(encoding="utf-8")
    assert "const __patch =" not in app.read_text(encoding="utf-8")
    assert css and all("padding:1rem" in path.read_text(encoding="utf-8") or "color:purple" in path.read_text(encoding="utf-8") for path in css)
    index = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert app.name in index
    assert all(path.name in index for path in css)
    for path in [runtime, *generated]:
        checked = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert checked.returncode == 0, f"{path}: {checked.stderr}"


def test_build_writes_size_report_and_threshold_warnings():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text("<template><div>Release</div></template>", encoding="utf-8")

        result = Builder({"report": "metrics.json", "max_asset_size": 1}).build(root)
        report = root / "dist" / "metrics.json"
        assert result["mode"] == "production"
        assert report.exists()
        assert result["total_bytes"] > 1
        assert result["size_warnings"]
        assert '"total_bytes"' in report.read_text(encoding="utf-8")


def test_generated_css_is_present_in_the_asset_map():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text(
            "<template><main>Styled</main></template>"
            "<style scoped>main { color: purple; }</style>",
            encoding="utf-8",
        )

        result = Builder({"dev": True}).build(root)

        assert result["failed"] == 0, result["errors"]
        assert result["asset_map"]["static/js/App.js"] == "static/js/App.js"
        assert result["asset_map"]["static/js/App.css"] == "static/js/App.css"


def test_custom_static_directory_copies_non_component_assets():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_dir = root / "client" / "js"
        source_dir.mkdir(parents=True)
        (root / "client" / "images").mkdir(parents=True)
        (root / "client" / "images" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        (source_dir / "App.vel").write_text(
            '<template><img src="/client/images/logo.svg">Ready</template>',
            encoding="utf-8",
        )

        result = Builder({
            "dev": True,
            "static_dir": "client",
            "hash_assets": True,
        }).build(root)

        assert result["failed"] == 0, result["errors"]
        image = next((root / "dist" / "client" / "images").glob("logo.*.svg"))
        assert image.exists()
        assert result["asset_map"]["client/images/logo.svg"].endswith(image.name)


def test_incremental_cache_invalidates_when_build_options_change():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text("<template><main>Cached</main></template>", encoding="utf-8")

        first = Builder({"dev": True, "minify": False}).build(root)
        assert first["compiled"] == 1
        second = Builder({"dev": True, "minify": True}).build(root)

        assert second["compiled"] == 1
        assert second["cache_hits"] == 0


def test_incremental_dev_build_reuses_unchanged_components_and_invalidates_dependents():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        js = root / "static" / "js"
        js.mkdir(parents=True)
        child = js / "Child.vel"
        app = js / "App.vel"
        child.write_text("<template><span>Child</span></template>", encoding="utf-8")
        app.write_text('<template><Child /></template><script>\nimport Child from "./Child.vel";\n</script>', encoding="utf-8")
        first = Builder({"dev": True}).build(root)
        assert first["compiled"] == 2
        second = Builder({"dev": True}).build(root)
        assert second["compiled"] == 0
        assert second["cache_hits"] == 2
        child.write_text("<template><span>Changed</span></template>", encoding="utf-8")
        third = Builder({"dev": True}).build(root)
        assert third["compiled"] == 2
        assert third["cache_hits"] == 0


def test_shared_runtime_build_emits_one_helper_module_and_imports_it():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_dir = root / "static" / "js"
        source_dir.mkdir(parents=True)
        (source_dir / "App.vel").write_text(
            "<template><div>Use `.vel` safely; ${templateText}</div></template>",
            encoding="utf-8",
        )
        result = Builder({"shared_runtime": True, "dev": False}).build(root)
        assert result["failed"] == 0, result["errors"]
        runtime = root / "dist" / "static" / "teloce-runtime.js"
        app = root / "dist" / "static" / "js" / "App.js"
        assert runtime.exists()
        app_source = app.read_text(encoding="utf-8")
        assert "../teloce-runtime.js" in app_source
        assert "__teloceCreateCompiledComponent" in app_source
        assert "const __patch =" not in app_source
        assert "const __reactive =" not in app_source
        assert result["runtime"] == "static/teloce-runtime.js"
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", (
                "const url = new URL(" + repr(app.as_uri()) + ");"
                "const module = await import(url);"
                "if (typeof module.mount !== 'function') process.exit(2);"
            )],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert completed.returncode == 0, completed.stderr


def test_lazy_component_import_emits_dynamic_chunk_loader():
    source = '''<template><Child /></template><script>
import Child from "./Child.vel";
</script>'''
    result = compile_component(source, filename="App.vel", source_maps=False,
                     component_imports={"Child": "./Child.js"},
                     lazy_components=["Child"])
    assert result["success"]
    assert 'import("./Child.js")' in result["code"]
    assert "const Child = __teloceLazy" in result["code"]
    assert result["code"].count("const Child = __teloceLazy") == 1
    assert 'import Child from "./Child.js"' not in result["code"]


def test_production_tree_shaking_removes_unused_local_component_imports():
    source = '''<template><Used /></template><script>
import Used from "./Used.vel";
import Unused from "./Unused.vel";
</script>'''
    result = compile_component(source, filename="App.vel", source_maps=False,
                               component_imports={"Used": "./Used.js", "Unused": "./Unused.js"},
                               tree_shake=True)
    assert result["success"]
    assert 'import Used from "./Used.js"' in result["code"]
    assert 'import Unused from "./Unused.js"' not in result["code"]


def test_tree_shaking_does_not_select_filters_from_javascript_strings():
    source = '''<template><p>{{ name }}</p></template><script>
export default { data() { return { name: "a | orderBy" }; } };
</script>'''
    result = compile_component(source, filename="App.vel", source_maps=False,
                               tree_shake=True)
    assert result["success"]
    assert '"orderBy":' not in result["code"]


def test_hash_assets_fingerprints_static_files_and_rewrites_dev_entrypoint():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        (root / "static" / "images").mkdir(parents=True)
        (root / "static" / "images" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        source.write_text("<template><div>Release</div></template>", encoding="utf-8")
        (root / "templates").mkdir()
        (root / "templates" / "index.html").write_text(
            '<img src="/static/images/logo.svg"><script type="module" src="/static/js/App.js"></script>',
            encoding="utf-8",
        )

        result = Builder({"dev": True, "hash_assets": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        image = next((root / "dist" / "static" / "images").glob("logo.*.svg"))
        generated = next((root / "dist" / "static" / "js").glob("App.*.js"))
        html = (root / "dist" / "index.html").read_text(encoding="utf-8")
        assert image.name in html
        assert generated.name in html
        assert result["asset_map"]["static/images/logo.svg"].endswith(image.name)


def test_build_writes_valid_source_maps_when_enabled():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "static" / "js" / "App.vel"
        source.parent.mkdir(parents=True)
        source.write_text("<template><div>Release</div></template>", encoding="utf-8")

        result = Builder({"source_maps": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        source_map = root / "dist" / "static" / "js" / "App.js.map"
        assert source_map.exists()
        assert '"version": 3' in source_map.read_text(encoding="utf-8")
        assert "sourceMappingURL=App.js.map" in (root / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")


def test_component_props_slots_events_and_dynamic_components_compile():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        parent = root / "static" / "js" / "App.vel"
        child = root / "static" / "js" / "components" / "Child.vel"
        parent.parent.mkdir(parents=True)
        child.parent.mkdir(parents=True)
        parent.write_text('''
<template>
  <Child title="Hello" :value="count" @save="onSave"><strong>Slot content</strong></Child>
  <component :is="activeComponent" />
</template>
<script>
import Child from "./components/Child.vel";
export default { data() { return { count: 1, activeComponent: "Child" }; }, methods: { onSave() {} } };
</script>
''', encoding="utf-8")
        child.write_text('''
<template><article><h2>{{ title }}</h2><slot /></article></template>
<script>
export default { props: ["title", "value"], methods: { save() { this.$emit("save", this.value); } } };
</script>
''', encoding="utf-8")

        result = Builder({"dev": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        code = (root / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")
        assert "data-teloce-is" in code
        assert "__teloceCreateCompiledComponent" in code
        assert "data-teloce-is" in code
        checked = subprocess.run(
            ["node", "--check", str(root / "dist" / "static" / "js" / "App.js")],
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 0, checked.stderr


def test_named_slots_and_child_prop_updates_are_emitted():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        parent = root / "static" / "js" / "App.vel"
        child = root / "static" / "js" / "components" / "Child.vel"
        parent.parent.mkdir(parents=True)
        child.parent.mkdir(parents=True)
        parent.write_text('''<template><Child :title="title"><strong slot="heading">Heading</strong></Child></template><script>import Child from "./components/Child.vel"; export default { data() { return { title: "One" }; }, components: { Child } };</script>''', encoding="utf-8")
        child.write_text('''<template><article><slot name="heading"></slot><h1>{{ title }}</h1></article></template><script>export default { props: { title: { type: String, required: true } } };</script>''', encoding="utf-8")
        result = Builder({"dev": True}).build(root)
        assert result["failed"] == 0, result["errors"]
        code = (root / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")
        assert "__teloceCreateCompiledComponent" in code


def test_production_bundle_resolves_nested_components_and_is_valid_js():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        parent = root / "static" / "js" / "App.vel"
        child = root / "static" / "js" / "components" / "Child.vel"
        child.parent.mkdir(parents=True)
        parent.write_text('<template><Child /></template><script>import Child from "./components/Child.vel"; export default {};</script>', encoding="utf-8")
        child.write_text('<template><p>Bundled</p></template>', encoding="utf-8")
        result = Builder({"bundle": True, "source_maps": False}).build(root)
        assert result["failed"] == 0, result["errors"]
        bundle = root / "dist" / "static" / "js" / "App.bundle.js"
        assert bundle.exists()
        checked = subprocess.run(["node", "--check", str(bundle)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr


def test_hashed_production_bundle_updates_entrypoint_and_asset_warnings():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_dir = root / "static" / "js"
        source_dir.mkdir(parents=True)
        (root / "static" / "images").mkdir(parents=True)
        (root / "static" / "images" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        (source_dir / "App.vel").write_text(
            '<template><main><img src="/static/images/logo.svg">Release</main></template>',
            encoding="utf-8",
        )
        (root / "templates").mkdir()
        (root / "templates" / "index.html").write_text(
            '<main id="app"></main><script type="module" src="/static/js/App.js"></script>',
            encoding="utf-8",
        )

        result = Builder({
            "mode": "production",
            "bundle": True,
            "source_maps": False,
            "max_asset_size": 1,
        }).build(root)

        assert result["failed"] == 0, result["errors"]
        bundle = root / "dist" / result["bundle"]
        assert bundle.exists()
        assert "." in bundle.stem
        html = (root / "dist" / "index.html").read_text(encoding="utf-8")
        assert bundle.name in html
        assert "/static/js/App.js" not in html
        assert result["asset_bytes"] >= 1
        assert any(item["output"].endswith(".svg") for item in result["size_warnings"])
        checked = subprocess.run(["node", "--check", str(bundle)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr


def test_bundler_supports_namespace_imports_and_reports_escape_errors():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "entry.js").write_text('import * as helper from "./helper.js"; export default helper;', encoding="utf-8")
        (root / "helper.js").write_text('export const value = 1;', encoding="utf-8")
        bundle = ModuleBundler(root).bundle("entry.js")
        assert "const helper = __teloce_modules['helper.js'];" in bundle.read_text(encoding="utf-8")

        (root / "escape.js").write_text('import value from "../outside.js"; export default value;', encoding="utf-8")
        try:
            ModuleBundler(root).bundle("escape.js")
        except BundleError as error:
            assert "escapes output directory" in str(error)
        else:
            raise AssertionError("expected an actionable BundleError")

        (root / "external.js").write_text('import runtime from "some-runtime"; export default runtime;', encoding="utf-8")
        try:
            ModuleBundler(root).bundle("external.js")
        except BundleError as error:
            assert "External import" in str(error)
        else:
            raise AssertionError("expected an external-import BundleError")


def test_named_vel_imports_preserve_named_import_syntax():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        parent = root / "static" / "js" / "App.vel"
        child = root / "static" / "js" / "components" / "Child.vel"
        child.parent.mkdir(parents=True)
        parent.write_text(
            '<template><Alias /></template><script>import { Button as Alias } from "./components/Child.vel"; export default {};</script>',
            encoding="utf-8",
        )
        child.write_text(
            '<template><p>Named</p></template><script>export const Button = {}; export default {};</script>',
            encoding="utf-8",
        )
        result = Builder({"source_maps": False}).build(root)
        assert result["failed"] == 0, result["errors"]
        parent_code = (root / "dist" / "static" / "js" / "App.js").read_text(encoding="utf-8")
        assert 'import { Button as Alias } from "./components/Child.js";' in parent_code

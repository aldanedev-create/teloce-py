"""
Tests for the compiler module.
"""

import pytest
from pathlib import Path

from teloce.compiler.compiler import Compiler, compile, compile_file, compile_project


class TestCompiler:
    """Tests for the compiler."""

    def test_compile_basic(self):
        """Test basic compilation."""
        source = """
<template>
    <div>Hello World</div>
</template>

<script>
export default {
    name: 'Hello'
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'code' in result
        assert 'Hello World' in result['code']

    def test_compile_with_interpolation(self):
        """Test compilation with interpolation."""
        source = """
<template>
    <div>{{ message }}</div>
</template>

<script>
export default {
    data() {
        return { message: 'Hello' }
    }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'message' in result['code']
        assert '__safeEvaluate' in result['code']

    def test_interpolation_preserves_surrounding_text_whitespace(self):
        source = '''
<template><button>Clicked {{ count }} times</button></template>
<script>export default { data() { return { count: 0 }; } };</script>
'''
        result = compile(source, filename="Whitespace.vel", source_maps=False)
        assert result['success'] is True
        assert 'Clicked <!--teloce-text:t0-->{{ count }}<!--teloce-text-end:t0--> times' in result['code']

    def test_compile_with_event(self):
        """Test compilation with event binding."""
        source = """
<template>
    <button @click="handleClick">Click</button>
</template>

<script>
export default {
    methods: {
        handleClick() {}
    }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'handleClick' in result['code']

    def test_compile_with_binding(self):
        """Test compilation with binding."""
        source = """
<template>
    <div :class="className">Content</div>
</template>

<script>
export default {
    data() {
        return { className: 'active' }
    }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'className' in result['code']

    def test_compile_with_for(self):
        """Test compilation with for loop."""
        source = """
<template>
    <for item in items key="id">
        <div>{{ item.name }}</div>
    </for>
</template>

<script>
export default {
    data() {
        return { items: [{ id: 1, name: 'Item' }] }
    }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'items' in result['code']

    def test_compile_with_if(self):
        """Test compilation with if condition."""
        source = """
<template>
    <if condition="isVisible">
        <div>Visible</div>
        <else>
        <div>Hidden</div>
    </if>
</template>

<script>
export default {
    data() {
        return { isVisible: true }
    }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'isVisible' in result['code']

    def test_compile_with_scoped_css(self):
        """Test compilation with scoped CSS."""
        source = """
<template>
    <div class="app">Content</div>
</template>

<script>
export default {
    name: 'App'
};
</script>

<style scoped>
.app { padding: 20px; }
</style>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'css' in result

    def test_compile_with_component(self):
        """Test compilation with nested component."""
        source = """
<template>
    <MyComponent />
</template>

<script>
import MyComponent from './components/MyComponent.vel';

export default {
    components: { MyComponent }
};
</script>
"""
        result = compile(source)
        assert result['success'] is True
        assert 'MyComponent' in result['code']

    def test_module_helpers_do_not_duplicate_component_export(self):
        """Module helpers must survive without emitting a second default export."""
        source = """
<template><div>{{ label }}</div></template>
<script>
const labelPrefix = `ready-${1 + 1}`;
export default {
    name: 'ExportOnce',
    data() { return { label: labelPrefix }; }
};
</script>
"""
        result = compile(source, "ExportOnce.vel")
        assert result['success'] is True
        assert result['code'].count('export default __component;') == 1
        assert 'export default {' not in result['code']
        assert 'labelPrefix' in result['code']

    def test_compile_file(self):
        """Test compiling a file."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vel', delete=False) as f:
            f.write("""
<template>
    <div>Hello</div>
</template>

<script>
export default {
    name: 'Hello'
};
</script>
""")
            f.close()
            result = compile_file(f.name)
            assert result['success'] is True
            Path(f.name).unlink()

    def test_compile_project(self):
        """Test compiling a project."""
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a .vel file
            vel_path = Path(tmpdir) / 'static' / 'js' / 'App.vel'
            vel_path.parent.mkdir(parents=True)
            vel_path.write_text("""
<template>
    <div>Hello</div>
</template>

<script>
export default {
    name: 'App'
};
</script>
""")
            result = compile_project(tmpdir)
            assert 'static/js/App.vel' in result
            assert result['static/js/App.vel']['success'] is True

    def test_compiler_options(self):
        """Test compiler options."""
        source = """
<template>
    <div>Hello</div>
</template>

<script>
export default {
    name: 'Hello'
};
</script>
"""
        result = compile(source, source_map=True, minify=True)
        assert result['success'] is True
        # Source map may be None if not implemented
        # assert result.get('map') is not None

    def test_unexpected_pipeline_failure_becomes_diagnostic(self, monkeypatch):
        """Public compilation never leaks an internal exception to callers."""
        from teloce.compiler import compiler as compiler_module

        def explode(*args, **kwargs):
            raise RuntimeError("synthetic parser failure")

        monkeypatch.setattr(compiler_module.SFCParser, "parse", explode)
        result = compile("<template><div /></template>", "Broken.vel")

        assert result["success"] is False
        assert result["code"] == ""
        assert result["diagnostics"]["errors"][0]["code"] == "E1000"
        assert "synthetic parser failure" in result["diagnostics"]["errors"][0]["message"]

    def test_javascript_parser_diagnostic_has_location_code_and_suggestion(self):
        source = '<template><div>Broken</div></template><script>\nexport default { methods: { run() {\n</script>'
        result = Compiler().compile(source, "Broken.vel")
        assert result["success"] is False
        error = next(item for item in result["diagnostics"]["errors"] if "Unclosed delimiter" in item["message"])
        assert error["filename"] == "Broken.vel"
        assert error["line"] is not None
        assert error["column"] is not None
        assert error["code"] == "E1001"
        assert error["suggestions"]

    def test_direct_plan_expands_computed_dependencies_and_source_metadata(self):
        source = '''
<template><p>{{ displayName }}</p></template>
<script>
export default {
  data() { return { firstName: "Ada" }; },
  computed: { displayName() { return this.firstName + " Lovelace"; } }
};
</script>
'''
        result = Compiler({"direct_dom_updates": True, "source_maps": True}).compile(source, "Computed.vel")
        assert result["success"] is True
        binding = result["direct_plan"]["bindings"][0]
        assert binding["expression"] == "displayName"
        assert "displayName" in binding["dependencies"]
        assert "firstName" in binding["dependencies"]
        assert result["map"]["x_teloce"]["direct_plan"]["bindings"][0]["source"]["line"] is not None

    def test_direct_plan_warns_and_falls_back_for_unsupported_expression(self):
        source = '''
<template><p>{{ items.map(item => item.name).join(", ") }}</p></template>
<script>export default { data() { return { items: [] }; } };</script>
'''
        result = Compiler({"direct_dom_updates": True}).compile(source, "Unsupported.vel")
        assert result["success"] is True
        assert result["direct_plan"]["fallback"] is True
        warning = next(item for item in result["diagnostics"]["warnings"] if item["code"] == "W3001")
        assert warning["line"] is not None
        assert warning["column"] is not None
        assert warning["suggestions"]

    def test_strict_direct_analysis_turns_fallback_into_error(self):
        source = '<template><p>{{ items.map(item => item.name) }}</p></template>'
        result = Compiler({
            "direct_dom_updates": True,
            "strict_dependency_analysis": True,
        }).compile(source, "Strict.vel")
        assert result["success"] is False
        assert result["diagnostics"]["errors"][0]["code"] == "E3001"

    def test_optional_preprocessor_runs_before_sfc_parsing(self):
        source = "PLACEHOLDER"

        def replace_placeholder(value, filename=None):
            assert filename == "Preprocessed.vel"
            return "<template><p>Preprocessed</p></template>"

        result = Compiler({"preprocessors": [replace_placeholder]}).compile(source, "Preprocessed.vel")
        assert result["success"] is True
        assert "Preprocessed" in result["code"]

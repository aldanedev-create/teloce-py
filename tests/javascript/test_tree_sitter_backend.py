"""Regression tests for the bundled Tree-sitter JavaScript backend."""

import pytest

from teloce.compiler.compiler import compile
from teloce.javascript import (
    JavaScriptSyntaxError,
    default_export_object_source,
    parse_javascript,
    parse_javascript_language,
    parse_valid_tree,
    tree_sitter_available,
)


def test_tree_sitter_dependencies_are_available_for_the_default_install():
    assert tree_sitter_available()


def test_tree_sitter_parses_modern_ecmascript_and_preserves_source_locations():
    source = """const load = async (url) => {
  const response = await fetch(url);
  return (await response.json())?.items ?? [];
};
class Store { #ready = true; }
"""

    program = parse_javascript_language(source)

    assert [node.kind for node in program.body] == [
        "VariableDeclaration",
        "ClassDeclaration",
    ]
    assert program.body[0].name == "load"
    assert program.body[0].line == 1
    assert program.body[0].column == 1
    assert "?.items ?? []" in program.body[0].source
    assert program.body[1].name == "Store"


def test_typescript_grammar_validates_type_syntax_without_executing_it():
    source = """interface User { id: number; name: string }
const getUser = async (id: number): Promise<User> => ({ id, name: String(id) });
"""

    tree = parse_valid_tree(source, language="ts")
    program = parse_javascript_language(source, language="typescript")

    assert tree.language == "typescript"
    assert not tree.root_node.has_error
    assert program.body[0].source.startswith("interface User")
    assert program.body[1].kind == "VariableDeclaration"


def test_javascript_and_typescript_grammars_cover_jsx_and_tsx():
    jsx = "const view = <Panel title={user.name}>Hello</Panel>;"
    tsx = "type Props = { title: string }; const view = <Panel {...props} />;"

    assert not parse_valid_tree(jsx, language="jsx").root_node.has_error
    assert not parse_valid_tree(tsx, language="tsx").root_node.has_error


def test_parser_backend_can_be_selected_and_module_exports_keep_boundaries():
    source = '''const text = "export default { not: 'a component }' }";
export async function load() { return await Promise.resolve(true); }
export { load as default };
'''

    program = parse_javascript(source, backend="tree-sitter")
    legacy = parse_javascript("const value = 1;", backend="legacy")

    assert [node.kind for node in program.body] == [
        "VariableDeclaration",
        "ExportDeclaration",
        "ExportDeclaration",
    ]
    assert program.body[1].source.startswith("export async function load")
    assert legacy.body[0].kind == "VariableDeclaration"


def test_default_export_object_uses_ast_boundaries_for_nested_literals():
    source = r'''const helper = { text: "not an export }" };
export default defineComponent({
  data() { return { text: "}", pattern: /[{}]/ }; },
  async mounted() { await Promise.resolve(`value ${helper.text}`); }
});
'''

    result = default_export_object_source(source)

    assert result is not None
    assert result.startswith("{")
    assert 'pattern: /[{}]/' in result
    assert "async mounted()" in result
    assert "not an export" not in result


def test_tree_sitter_reports_a_source_located_error_with_a_fix_hint():
    with pytest.raises(JavaScriptSyntaxError, match="expected") as error:
        parse_javascript_language("const value = ({ broken: true ]);")

    assert error.value.token is not None
    assert error.value.token.line == 1
    assert error.value.token.column > 1
    assert error.value.suggestion


def test_vel_component_async_lifecycle_is_preserved_in_generated_javascript():
    source = """
<template><button @click="refresh">{{ status }}</button></template>
<script>
export default {
  data() { return { status: "idle" }; },
  async mounted() { await Promise.resolve(); this.status = "ready"; },
  methods: {
    async refresh() { this.status = (await Promise.resolve("updated")); }
  }
};
</script>
"""

    result = compile(source, "TreeSitterAsync.vel", source_maps=False)

    assert result["success"], result["diagnostics"]
    assert "async mounted()" in result["code"]
    assert "async refresh()" in result["code"]

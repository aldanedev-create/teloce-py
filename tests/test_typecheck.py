"""Tests for ``teloce typecheck`` (pytscheck adapter). Compiler-backed tests need ``pytscheck``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from teloce.typecheck.adapter import (
    _match_brace,
    free_identifiers,
    rewrite_default_export,
)

# --------------------------------------------------------------------------- pure helpers (no compiler needed)


def test_free_identifiers_ignores_properties_keys_globals_and_loop_vars():
    ids = free_identifiers(
        "post.tags.filter(t => t.hot).length > 0 && open ? { hot: tag.hot, label } : Math.max(a, 1)",
        {"tag"},
    )
    assert ids == ["a", "label", "open", "post"]


def test_free_identifiers_reads_template_literals_and_strings():
    assert free_identifiers("`hi ${user.name} and ${count}` + 'ignored'") == [
        "count",
        "user",
    ]


def test_free_identifiers_handles_numbers_and_spread():
    assert free_identifiers("[...items, 1.5, 2]") == ["items"]


def test_rewrite_default_export_survives_braces_in_strings_and_comments():
    body = 'const a = "}";\nexport default {\n  // }\n  data() { return { s: "{" }; },\n};\nconst after = 1;\n'
    wrapped = rewrite_default_export(body)
    assert wrapped is not None
    assert wrapped.startswith('const a = "}";\nexport default __define({')
    assert "});\nconst after = 1;" in wrapped


def test_rewrite_default_export_returns_none_without_object_export():
    assert rewrite_default_export("export const x = 1;") is None


def test_match_brace_handles_nested_template_literals():
    text = "{ a: `x ${ {b: 1}.b } y` }"
    assert _match_brace(text, 0) == len(text) - 1


# --------------------------------------------------------------------------- compiler-backed behaviour


@pytest.fixture
def installed_pytscheck():
    pytest.importorskip("pytscheck")


from teloce.cli.main import main  # noqa: E402
from teloce.typecheck import TypecheckUnavailable, check_project  # noqa: E402

GOOD = """<template>
  <main>
    <h1>{{ title }}</h1>
    <ul><li v-for="c in categories" :key="c.id" :class="{ on: c.id === picked }" @click="pick(c.id)">{{ c.name }}</li></ul>
    <button :disabled="busy" @click="busy = !busy">Go</button>
  </main>
</template>
<script lang="ts">
export default {
  data() {
    const categories: { id: number; name: string }[] = [];
    return { title: "Shop", categories, picked: 0, busy: false };
  },
  methods: { pick(id: number) { this.picked = id; } },
};
</script>
"""


def _project(tmp_path: Path, source: str, name: str = "App.html") -> Path:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / name).write_text(source, encoding="utf-8")
    return ui


def _position(source: str, needle: str) -> tuple[int, int]:
    index = source.index(needle)
    line = source.count("\n", 0, index) + 1
    return line, index - (source.rfind("\n", 0, index) + 1) + 1


@pytest.mark.usefixtures("installed_pytscheck")
def test_clean_component_has_no_findings(tmp_path):
    assert check_project([_project(tmp_path, GOOD)]).ok


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        ("{{ title }}", "{{ titel }}", "titel"),
        (':disabled="busy"', ':disabled="bussy"', "bussy"),
        ('v-for="c in categories"', 'v-for="c in categoriez"', "categoriez"),
        ('@click="pick(c.id)"', '@click="pik(c.id)"', "pik"),
        ("{{ c.name }}", "{{ c.nme }}", "nme"),
    ],
)
@pytest.mark.usefixtures("installed_pytscheck")
def test_template_typos_are_reported_at_the_exact_identifier(
    tmp_path, old, new, needle
):
    source = GOOD.replace(old, new)
    result = check_project([_project(tmp_path, source)])
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.file == "App.html"
    assert (finding.line, finding.column) == _position(source, needle)
    assert needle in finding.message


@pytest.mark.usefixtures("installed_pytscheck")
def test_loop_variable_is_typed_from_its_source(tmp_path):
    source = GOOD.replace("{{ c.name }}", "{{ c.name.toFixed(2) }}")
    result = check_project([_project(tmp_path, source)])
    assert [f.code for f in result.findings] == [2339] or [
        f.code for f in result.findings
    ] == [2551]
    assert "toFixed" in result.findings[0].message


@pytest.mark.usefixtures("installed_pytscheck")
def test_script_errors_keep_original_line_numbers(tmp_path):
    source = GOOD.replace("this.picked = id;", 'this.picked = "x";')
    finding = check_project([_project(tmp_path, source)]).findings[0]
    assert finding.file == "App.html"
    assert finding.line == _position(source, 'this.picked = "x"')[0]


@pytest.mark.usefixtures("installed_pytscheck")
def test_messages_do_not_dump_the_generated_component_type(tmp_path):
    finding = check_project(
        [_project(tmp_path, GOOD.replace("{{ title }}", "{{ titel }}"))]
    ).findings[0]
    assert "on this component" in finding.message
    assert "Computed<" not in finding.message


@pytest.mark.usefixtures("installed_pytscheck")
def test_templates_can_be_skipped(tmp_path):
    ui = _project(tmp_path, GOOD.replace("{{ title }}", "{{ titel }}"))
    assert check_project([ui], templates=False).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_javascript_components_are_checked(tmp_path):
    source = "<template><p>{{ nope }}</p></template>\n<script>export default { data() { return {}; } };</script>\n"
    assert not check_project([_project(tmp_path, source)]).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_plain_ts_files_are_checked(tmp_path):
    ui = _project(tmp_path, GOOD)
    (ui / "api.ts").write_text('export const n: number = "x";\n', encoding="utf-8")
    finding = check_project([ui]).findings[0]
    assert (finding.file, finding.line) == ("api.ts", 1)


@pytest.mark.usefixtures("installed_pytscheck")
def test_multiple_roots_resolve_cross_folder_imports(tmp_path):
    (tmp_path / "ui").mkdir()
    (tmp_path / "modules" / "shop" / "ui").mkdir(parents=True)
    (tmp_path / "modules" / "shop" / "ui" / "types.ts").write_text(
        "export interface P { id: number }\n", encoding="utf-8"
    )
    (tmp_path / "ui" / "App.html").write_text(
        '<template><p>{{ p.id }}</p></template>\n<script lang="ts">\n'
        'import type { P } from "../modules/shop/ui/types.ts";\n'
        "export default { data() { const p: P = { id: 1 }; return { p }; } };\n</script>\n",
        encoding="utf-8",
    )
    result = check_project([tmp_path / "ui", tmp_path / "modules" / "shop" / "ui"])
    assert result.ok, [f.format() for f in result.findings]


@pytest.mark.usefixtures("installed_pytscheck")
def test_cli_exit_codes(tmp_path, capsys):
    clean = _project(tmp_path, GOOD)
    assert main(["typecheck", str(clean)]) == 0
    (clean / "App.html").write_text(
        GOOD.replace("{{ title }}", "{{ titel }}"), encoding="utf-8"
    )
    assert main(["typecheck", str(clean)]) == 1
    assert "titel" in capsys.readouterr().out
    assert main(["typecheck", str(tmp_path / "missing")]) == 2


@pytest.mark.usefixtures("installed_pytscheck")
def test_cli_json_output(tmp_path, capsys):
    ui = _project(tmp_path, GOOD.replace("{{ title }}", "{{ titel }}"))
    assert main(["typecheck", "--json", str(ui)]) == 1
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["findings"][0]["file"] == "App.html"


def test_missing_pytscheck_gives_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pytscheck", None)
    message = (
        r"Python 3.11" if sys.version_info < (3, 11) else r"teloce-py\[typecheck\]"
    )
    with pytest.raises(TypecheckUnavailable, match=message):
        check_project([_project(tmp_path, GOOD)])


def test_rewrite_ignores_fake_exports_and_regex_braces():
    source = 'const label = "export default { nope: 1 }"; // export default { nope: 2 }\nexport default { data() { return { pattern: /}/ }; } };'
    wrapped = rewrite_default_export(source)
    assert wrapped.startswith('const label = "export default { nope: 1 }";')
    assert (
        "export default __define({ data() { return { pattern: /}/ }; } });" in wrapped
    )


@pytest.mark.usefixtures("installed_pytscheck")
def test_inline_script_error_retains_original_column_and_unicode(tmp_path):
    source = '<template>😀</template><script lang="ts">export default { data() { const wrong: number = "x"; return {wrong}; } };</script>'
    result = check_project([_project(tmp_path, source)])
    error = result.findings[0]
    original_column = len(source[: source.index("wrong")].encode("utf-16-le")) // 2 + 1
    assert (error.code, error.line, error.column) == (2322, 1, original_column)
    assert result.elapsed > 0


@pytest.mark.usefixtures("installed_pytscheck")
def test_multiline_template_does_not_shift_following_expression(tmp_path):
    source = GOOD.replace("{{ title }}", "{{ title\n .lenght }}").replace(
        ':disabled="busy"', ':disabled="bussy"'
    )
    result = check_project([_project(tmp_path, source)])
    assert len(result.findings) == 2
    for finding in result.findings:
        needle = "lenght" if "lenght" in finding.message else "bussy"
        assert (finding.line, finding.column) == _position(source, needle)


@pytest.mark.usefixtures("installed_pytscheck")
def test_template_unicode_columns(tmp_path):
    source = GOOD.replace("{{ title }}", "😀 {{ titel }}")
    finding = check_project([_project(tmp_path, source)]).findings[0]
    line, column = _position(source, "titel")
    assert (finding.line, finding.column) == (line, column + 1)


@pytest.mark.usefixtures("installed_pytscheck")
def test_declaration_files_resolve_imports(tmp_path):
    ui = _project(tmp_path, GOOD)
    (ui / "types.d.ts").write_text("export interface Product { id: number }\n")
    (ui / "api.ts").write_text(
        "import type { Product } from './types'; export const p: Product = {id: 1};"
    )
    assert check_project([ui]).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_empty_input_and_file_paths_are_explicit_errors(tmp_path):
    with pytest.raises(TypecheckUnavailable, match="at least one"):
        check_project([])
    source = tmp_path / "app.ts"
    source.write_text("const x = 1;")
    assert main(["typecheck", str(source)]) == 2


@pytest.mark.usefixtures("installed_pytscheck")
def test_missing_compiler_is_cli_exit_two(tmp_path, capsys):
    from pytscheck.runner import binary_path

    binary = binary_path()
    backup = binary.with_name(binary.name + ".typecheck-test-backup")
    assert not backup.exists()
    binary.rename(backup)
    try:
        assert main(["typecheck", str(_project(tmp_path, GOOD))]) == 2
        assert "could not run" in capsys.readouterr().err
    finally:
        backup.rename(binary)


@pytest.mark.usefixtures("installed_pytscheck")
def test_project_config_aliases_real_files_and_strictness(tmp_path):
    import json

    ui = tmp_path / "ui"
    ui.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.ts").write_text('export const title: string = "Hello";')
    config = tmp_path / "tsconfig.json"
    config.write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": False,
                    "paths": {"@/*": ["./src/*"]},
                    "module": "esnext",
                    "moduleResolution": "bundler",
                },
                "include": ["src"],
            }
        )
    )
    component = ui / "App.html"
    component.write_text(
        '<script lang="ts">import { title } from "@/utils"; export default { data() { let label: string = null; return { title, label }; } };</script><template>{{ title }}</template>'
    )
    before = component.read_bytes()
    assert check_project([ui]).ok
    assert any(f.code == 2322 for f in check_project([ui], strict=True).findings)
    assert component.read_bytes() == before
    assert not (ui / "App.html.ts").exists()
    (src / "utils.ts").write_text("export const title: string = 123;")
    assert any(f.file == "src/utils.ts" for f in check_project([ui]).findings)


@pytest.mark.usefixtures("installed_pytscheck")
def test_explicit_config_and_invalid_config(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "plain.ts").write_text("const label: string = null;")
    (tmp_path / "custom.json").write_text(
        '{"compilerOptions":{"strict":false},"include":["ui"]}'
    )
    assert check_project([ui], project_root=tmp_path, tsconfig="custom.json").ok
    with pytest.raises(TypecheckUnavailable, match="could not run"):
        check_project([ui], project_root=tmp_path, tsconfig="missing.json")
    (tmp_path / "tsconfig.json").write_text("{ invalid")
    with pytest.raises(TypecheckUnavailable, match="could not run"):
        check_project([ui], project_root=tmp_path)


@pytest.mark.usefixtures("installed_pytscheck")
def test_object_props_have_types_in_scripts_and_templates(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    component = ui / "App.html"
    component.write_text(
        '<script lang="ts">export default { props: { title: { type: String, required: true }, count: { type: Number, default: 0 }, active: { type: Boolean, default: false } }, methods: { label() { return this.title.toUpperCase(); } } };</script><template>{{ title.toUpperCase() }} {{ count.toFixed() }} {{ active }}</template>'
    )
    assert check_project([ui]).ok
    component.write_text(
        component.read_text().replace("count.toFixed()", "count.toUpperCase()")
    )
    assert any(
        "toUpperCase" in f.message and "number" in f.message
        for f in check_project([ui]).findings
    )


@pytest.mark.usefixtures("installed_pytscheck")
def test_extended_config_and_installed_package_types(tmp_path):
    import json

    ui = tmp_path / "ui"
    ui.mkdir()
    package = tmp_path / "node_modules/example"
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"name":"example","types":"index.d.ts"}')
    (package / "index.d.ts").write_text("export declare const value: number;")
    (tmp_path / "base.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": False,
                    "module": "esnext",
                    "moduleResolution": "bundler",
                }
            }
        )
    )
    (tmp_path / "tsconfig.json").write_text(
        '{"extends":"./base.json","include":["ui"]}'
    )
    (ui / "App.html").write_text(
        '<script lang="ts">import { value } from "example"; export default { data() { let label: string = null; return { value, label }; } };</script><template>{{ value.toFixed() }}</template>'
    )
    assert check_project([ui]).ok
    page = ui / "App.html"
    page.write_text(page.read_text().replace("value.toFixed()", "value.toUpperCase()"))
    result = check_project([ui])
    assert any(
        "toUpperCase" in finding.message and "number" in finding.message
        for finding in result.findings
    )


def child_project(tmp_path, markup):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "Child.html").write_text("""<script lang="ts">
export default { props: {
  label: { type: String, required: true },
  count: { type: Number, default: 0 },
  active: { type: Boolean },
} };
</script><template>{{ label }} {{ count }}</template>""")
    parent = ui / "Parent.html"
    parent.write_text(
        """<script lang="ts">
import Counter from "./Child.html";
export default { components: { Counter }, data() {
  return { amount: 3, text: "Hi", rows: [1, 2] };
} };
</script><template>"""
        + markup
        + "</template>"
    )
    return ui, parent


@pytest.mark.usefixtures("installed_pytscheck")
@pytest.mark.parametrize(
    "markup",
    [
        '<Counter label="Hello" :count="amount" :active="true" />',
        '<Counter :label="text" />',
        '<Counter v-for="row in rows" label="Hello" :count="row" />',
        '<Counter label="Hello" class="card" style="color:red" id="counter" aria-label="Counter" data-test="counter" @click="amount++" />',
    ],
)
def test_parent_supplies_valid_child_props(tmp_path, markup):
    ui, parent = child_project(tmp_path, markup)
    result = check_project([ui])
    assert result.ok, result.findings


@pytest.mark.usefixtures("installed_pytscheck")
@pytest.mark.parametrize(
    "markup, expected",
    [
        ('<Counter label="Hello" :count="text" />', "number"),
        ('<Counter :count="amount" />', "label"),
        ('<Counter label="Hello" :coutn="amount" />', "coutn"),
        ('<Counter label="Hello" count="3" />', "number"),
        ('<Counter label="Hello" :active="amount" />', "boolean"),
        (
            '<Counter v-for="row in rows" label="Hello" :count="row.toFixed()" />',
            "number",
        ),
    ],
)
def test_parent_prop_errors_map_back_to_parent(tmp_path, markup, expected):
    ui, parent = child_project(tmp_path, markup)
    before = parent.read_bytes()
    result = check_project([ui])
    assert any(
        f.file == "Parent.html" and f.line == 6 and expected in f.message
        for f in result.findings
    ), result.findings
    assert parent.read_bytes() == before
    assert not (ui / "Parent.html.tpl.ts").exists()
    assert check_project([ui], templates=False).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_unknown_props_on_component_without_declared_props(tmp_path):
    ui, _ = child_project(tmp_path, '<Counter :extra="amount" />')
    (ui / "Child.html").write_text(
        '<script lang="ts">export default { };</script><template>Hi</template>'
    )
    result = check_project([ui])
    assert any(
        f.file == "Parent.html" and "never" in f.message for f in result.findings
    )


@pytest.mark.usefixtures("installed_pytscheck")
def test_untyped_javascript_child_keeps_working(tmp_path):
    ui, _ = child_project(tmp_path, '<Counter :unknown="amount" />')
    (ui / "Child.html").write_text(
        '<script>export default { props: ["unknown"] };</script><template>Hi</template>'
    )
    assert check_project([ui]).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_multiline_child_prop_finding_points_to_attribute_line(tmp_path):
    ui, parent = child_project(tmp_path, '<Counter label="Hello"\n  :count="text" />')
    result = check_project([ui])
    assert any(
        f.file == "Parent.html"
        and f.line == 7
        and f.column == 3
        and "number" in f.message
        for f in result.findings
    ), result.findings


@pytest.mark.usefixtures("installed_pytscheck")
def test_named_object_child_export_has_a_typed_contract(tmp_path):
    ui, _ = child_project(tmp_path, '<Counter :unknown="amount" />')
    (ui / "Child.html").write_text(
        '<script lang="ts">const component = {}; export default component;</script>'
    )
    assert not check_project([ui]).ok


@pytest.mark.usefixtures("installed_pytscheck")
def test_kebab_case_attributes_match_camel_case_prop_contract(tmp_path):
    ui, parent = child_project(
        tmp_path, '<Counter label="Hi" :item-count="amount" :project-name="text" />'
    )
    (ui / "Child.html").write_text(
        '<script lang="ts">export default { props: { label: {type: String, required: true}, itemCount: {type: Number, required: true}, projectName: {type: String} } };</script>'
    )
    assert check_project([ui]).ok
    parent.write_text(
        parent.read_text().replace(':item-count="amount"', ':item-count="text"')
    )
    assert any("number" in finding.message for finding in check_project([ui]).findings)

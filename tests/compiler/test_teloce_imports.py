"""Bare ``teloce/...`` imports in component scripts."""

from pathlib import Path

import pytest

from teloce.build import build_project
from teloce.compiler.compiler import Compiler
from teloce.compiler.runtime_imports import rewrite_teloce_imports, unknown_teloce_imports

RUNTIME = "../../teloce-runtime.js"


@pytest.mark.parametrize(
    "source, expected",
    [
        ('import { http } from "teloce/runtime";', f'import {{ http }} from "{RUNTIME}";'),
        ("import { http } from 'teloce/runtime';", f'import {{ http }} from "{RUNTIME}";'),
        ('import { http } from "teloce";', f'import {{ http }} from "{RUNTIME}";'),
        ('import { http } from "teloce/network";', 'import { http } from "../../network.js";'),
        ('import { createSignal } from "teloce/signals";', 'import { createSignal } from "../../signals.js";'),
        ('const mod = await import("teloce/runtime");', f'const mod = await import("{RUNTIME}");'),
        ('export { http } from "teloce/runtime";', f'export {{ http }} from "{RUNTIME}";'),
    ],
)
def test_specifiers_are_rewritten_relative_to_the_importing_file(source, expected):
    assert rewrite_teloce_imports(source, RUNTIME) == expected


@pytest.mark.parametrize(
    "source",
    [
        'import x from "./teloce-runtime.js";',
        'import x from "teloce-signals";',
        'import x from "teloce/nope";',
        'const text = "teloce/runtime is a module";',
        'import x from "../teloce/runtime";',
    ],
)
def test_other_specifiers_are_left_alone(source):
    assert rewrite_teloce_imports(source, RUNTIME) == source


def test_without_a_shared_runtime_nothing_is_rewritten():
    source = 'import { http } from "teloce/runtime";'
    assert rewrite_teloce_imports(source, None) == source


def test_unknown_modules_are_reported():
    assert [name for _, name in unknown_teloce_imports('import a from "teloce/nope"; import b from "teloce/network";')] == [
        "teloce/nope"
    ]


def test_compiler_rewrites_and_warns():
    source = (
        "<template><p>{{ x }}</p></template>\n<script>\n"
        'import { http } from "teloce/runtime";\nimport { nope } from "teloce/nope";\n'
        "export default { data() { return { x: typeof http }; } };\n</script>"
    )
    compiler = Compiler({"shared_runtime_import": RUNTIME})
    code = compiler.compile(source, "pages/P.vel")["code"]
    assert f'import {{ http }} from "{RUNTIME}";' in code
    assert 'from "teloce/nope"' in code
    warnings = [d for d in compiler.diagnostics.diagnostics if d.code == "W1002"]
    assert len(warnings) == 1 and warnings[0].line == 4 and "teloce/nope" in warnings[0].message


def test_project_build_computes_the_path_for_each_component_depth(tmp_path: Path):
    (tmp_path / "static" / "js" / "pages").mkdir(parents=True)
    body = (
        "<template><p>{{ kind }}</p></template>\n<script>\n"
        'import { http } from "teloce/runtime";\n'
        "export default { data() { return { kind: typeof http }; } };\n</script>\n"
    )
    (tmp_path / "static" / "js" / "App.vel").write_text(body, encoding="utf-8")
    (tmp_path / "static" / "js" / "pages" / "Page.vel").write_text(body, encoding="utf-8")
    build_project(tmp_path, options={"dev": True})
    assert 'from "../teloce-runtime.js"' in (tmp_path / "dist/static/js/App.js").read_text(encoding="utf-8")
    assert 'from "../../teloce-runtime.js"' in (tmp_path / "dist/static/js/pages/Page.js").read_text(encoding="utf-8")
    assert (tmp_path / "dist/static/teloce-runtime.js").is_file()

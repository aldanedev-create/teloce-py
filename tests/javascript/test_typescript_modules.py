"""Pure-Python .ts support: standalone modules, .vel imports, and type stripping."""

import pytest

from teloce.build import build_project
from teloce.javascript.ts_transpile import TSUnsupported, transpile


def test_ts_module_is_compiled_and_vel_import_rewritten(tmp_path):
    js = tmp_path / "static" / "js"
    js.mkdir(parents=True)
    (js / "utils.ts").write_text(
        "export interface Item { id: number }\n"
        "export function double(n: number): number { return n * 2; }\n"
    )
    (js / "App.vel").write_text(
        '<template><div>{{ n }}</div></template>\n'
        '<script lang="ts">\n'
        'import { double } from "./utils.ts";\n'
        'import type { Item } from "./utils.ts";\n'
        'export default { data() { return { n: double(2) as number }; } };\n'
        "</script>\n"
    )
    result = build_project(str(tmp_path))
    assert result["failed"] == 0, result["errors"]

    out = tmp_path / "dist" / "static" / "js"
    emitted = (out / "utils.js").read_text()
    assert "interface" not in emitted and ": number" not in emitted
    assert "function double(n" in emitted
    app = (out / "App.js").read_text()
    assert 'from "./utils.js"' in app and "./utils.ts" not in app


def test_typescript_option_can_be_disabled(tmp_path):
    js = tmp_path / "static" / "js"
    js.mkdir(parents=True)
    (js / "a.ts").write_text("export const a: number = 1;\n")
    (js / "App.vel").write_text("<template><div>x</div></template>\n")
    build_project(str(tmp_path), options={"typescript": False})
    assert not (tmp_path / "dist" / "static" / "js" / "a.js").exists()


def test_type_only_syntax_is_removed():
    out = transpile(
        'import { type A, b } from "./m.ts";\n'
        "type T = string;\n"
        "export function f<U>(x: U, y?: number): U { return x as U; }\n"
        "class C<T> implements I { private v?: T; }\n"
    )
    assert 'import {' in out and "b" in out and "type A" not in out
    assert "./m.js" in out
    assert "type T" not in out and "implements" not in out and "<U>" not in out


@pytest.mark.parametrize("code", [
    "enum E { A }",
    "namespace N { export const a = 1 }",
    "class A { constructor(private x: number) {} }",
])
def test_unsupported_constructs_fail_loudly(code):
    with pytest.raises(TSUnsupported):
        transpile(code)


def test_syntax_error_is_reported():
    with pytest.raises(SyntaxError):
        transpile("const x: number = ;")
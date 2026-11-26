"""``teloce/runtime`` imports in type-checked components, and the tsgo version reporting."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from teloce.typecheck import checker_info
from teloce.typecheck.adapter import runtime_declaration_files, user_bound_names

# --------------------------------------------------------------------------- pure helpers


def test_user_bound_names_reads_every_import_form_and_local_declaration():
    names = user_bound_names(
        'import { http, signal as sig, type Foo } from "teloce/runtime";\n'
        'import def from "./d";\nimport * as ns from "./n";\nimport type { T } from "./t";\n'
        "const c = 1; function f() {} class K {}\nconst x = await import(\"./lazy\");"
    )
    assert {"http", "sig", "Foo", "def", "ns", "T", "c", "f", "K", "x"} <= names
    assert "signal" not in names  # only the alias is bound


def test_runtime_declaration_files_cover_every_public_module():
    files = runtime_declaration_files()
    assert set(files) == {
        "node_modules/teloce/runtime.d.ts",
        "node_modules/teloce/index.d.ts",
        "node_modules/teloce/network.d.ts",
        "node_modules/teloce/signals.d.ts",
        "node_modules/teloce/data.d.ts",
        "node_modules/teloce/scheduler.d.ts",
        "node_modules/teloce/table.d.ts",
    }
    assert 'export * from "' in files["node_modules/teloce/network.d.ts"]
    assert "createSignal as signal" in files["node_modules/teloce/runtime.d.ts"]


# --------------------------------------------------------------------------- compiler-backed

pytestmark_compiler = pytest.mark.skipif(sys.version_info < (3, 11), reason="type checking needs Python 3.11+")


@pytest.fixture
def check(tmp_path: Path):
    pytest.importorskip("pytscheck")
    from teloce.typecheck import check_project

    def run(script: str, template: str = "<p>{{ n }}</p>", extra_files: dict[str, str] | None = None):
        ui = tmp_path / "ui"
        ui.mkdir(exist_ok=True)
        (ui / "App.vel").write_text(
            f'<template>{template}</template>\n<script lang="ts">\n{script}\n</script>\n', encoding="utf-8"
        )
        for name, text in (extra_files or {}).items():
            (ui / name).write_text(text, encoding="utf-8")
        return check_project([ui])

    return run


COMPONENT = "export default { data() { return { n: 1 as number }; } };"


@pytestmark_compiler
def test_bare_runtime_imports_resolve_with_no_errors(check):
    result = check(
        'import { http, action, createScope, signal, NetworkError } from "teloce/runtime";\n'
        'import { createHttp } from "teloce/network";\n'
        'import { createSignal } from "teloce/signals";\n'
        'import { createDataTable } from "teloce/table";\n' + COMPONENT.replace(
            "};",
            "};\n",
        ).replace("data()", "async mounted() { const r = await http.get('/x'); const s: number = r.status;"
                  " const a = await action.call('x', {}); createScope().dispose(); },\n  data()")
    )
    assert result.ok, [f.format() for f in result.findings]


@pytestmark_compiler
def test_runtime_types_are_the_real_ones(check):
    result = check('import { http } from "teloce/runtime";\nconst n: number = http.get;\n' + COMPONENT)
    assert [f.code for f in result.findings] == [2322]
    assert "RequestConfig" in result.findings[0].message


@pytestmark_compiler
def test_wrong_argument_types_are_reported(check):
    result = check('import { http } from "teloce/runtime";\nhttp.get(42);\n' + COMPONENT)
    assert [f.code for f in result.findings] == [2345]


@pytestmark_compiler
def test_the_relative_runtime_path_resolves_too(check):
    result = check('import { http } from "../teloce-runtime.js";\nhttp.get("/x");\n' + COMPONENT)
    assert result.ok, [f.format() for f in result.findings]


@pytestmark_compiler
def test_unknown_teloce_modules_are_reported_once_at_the_import(check):
    result = check('import { nope } from "teloce/nope";\n' + COMPONENT)
    assert [(f.code, f.line) for f in result.findings] == [(2307, 3)]


@pytestmark_compiler
def test_runtime_source_diagnostics_do_not_leak_into_findings(check):
    result = check('import { http } from "teloce/runtime";\nhttp.get("/x");\n' + COMPONENT)
    assert not [f for f in result.findings if "runtime" in f.file]


@pytestmark_compiler
@pytest.mark.parametrize(
    "import_line, call",
    [
        ('import { signal } from "teloce/runtime";', "signal(0)"),
        ('import { createSignal } from "teloce/signals";', 'createSignal("x")'),
        ('import { signal } from "./sig";', "signal(0)"),
    ],
)
def test_explicit_signal_imports_do_not_conflict_in_typescript_scripts(check, import_line, call):
    """Regression: TypeScript syntax hid the import, so the checker declared the helper a second time."""
    result = check(
        f"{import_line}\nconst c = {call};\n{COMPONENT}",
        extra_files={"sig.ts": "export const signal = (n: number) => n;\n"},
    )
    assert result.ok, [f.format() for f in result.findings]


@pytestmark_compiler
def test_unimported_signal_helpers_are_still_provided(check):
    result = check(f"const c = signal(0);\n{COMPONENT}")
    assert result.ok, [f.format() for f in result.findings]


# --------------------------------------------------------------------------- tsgo reporting


@pytestmark_compiler
def test_checker_info_names_tsgo_and_pytscheck():
    pytest.importorskip("pytscheck")
    info = checker_info()
    assert info and info["engine"] == "tsgo" and info["tsgo"] and info["pytscheck"]


@pytestmark_compiler
def test_cli_reports_the_compiler_in_text_and_json(tmp_path: Path, capsys):
    pytest.importorskip("pytscheck")
    from teloce.cli.typecheck import typecheck_command

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "App.vel").write_text(f'<template><p>{{{{ n }}}}</p></template>\n<script lang="ts">\n{COMPONENT}\n</script>\n')
    args = Namespace(paths=[str(ui)], no_templates=False, no_strict=False, json=False, project_root=None, tsconfig=None)
    assert typecheck_command(args) == 0
    out = capsys.readouterr().out
    assert "No type errors found." in out and "Checked with tsgo " in out
    args.json = True
    assert typecheck_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checker"]["engine"] == "tsgo" and payload["compiler"] == payload["checker"]["tsgo"]


def test_doctor_reports_the_type_checker(capsys):
    from teloce.cli.doctor import doctor_command

    doctor_command(Namespace(verbose=False, show_config=False))
    assert "Type checker:" in capsys.readouterr().out

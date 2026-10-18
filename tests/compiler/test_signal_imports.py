"""Zero-configuration helper imports must also fire for generic helper calls.

``signal<number>(0)`` is an ordinary call, but the old detector required the
opening parenthesis to follow the name directly, so the import was skipped and
the page threw ``ReferenceError: signal is not defined``.

Generic type arguments are written in a ``lang="ts"`` script; a plain
``<script>`` block is parsed as JavaScript, where nested generics such as
``Record<string, Task[]>`` are not valid syntax at all.
"""

import pytest

from teloce.compiler.compiler import compile

RUNTIME = "./signals.js"


def imports_of(body, *, lang="ts", setup=True):
    """Compile one component and return its runtime helper import lines."""
    script_open = '<script setup lang="ts">' if setup else "<script>"
    source = f"<template><p>{{n}}</p></template>\n{script_open}\n{body}\n</script>\n"
    compiled = compile(source, filename="Widget.html", dev=True, shared_runtime_import=RUNTIME)
    assert compiled["success"], compiled["diagnostics"]["errors"]
    return [
        line
        for line in compiled["code"].split("\n")
        if line.startswith("import ") and "signals.js" in line and "__teloceCreateCompiledComponent" not in line
    ]


@pytest.mark.parametrize(
    "expression",
    [
        "signal(0)",
        "signal<number>(0)",
        "signal< number >(0)",
        "signal<Record<string, Task[]>>({})",
        "signal<Map<string, Array<number>>>(new Map())",
    ],
)
def test_signal_calls_import_the_runtime_helper(expression):
    body = f"const n = {expression};"
    assert any("createSignal as signal" in line for line in imports_of(body))


def test_the_same_works_in_a_plain_script_block():
    """`signal<number>(0)` also parses as JavaScript, where it is written most often."""
    body = "export default { setup() { const n = signal<number>(0); return { n }; } };"
    assert any("createSignal as signal" in line for line in imports_of(body, setup=False))


def test_computed_and_effect_generics_are_detected():
    body = "const d = computed<number>(() => 1);\neffect<number>(() => d());"
    lines = imports_of(body)
    assert any("createComputed as computed" in line for line in lines)
    assert any("createEffect as effect" in line for line in lines)


@pytest.mark.parametrize(
    "expression",
    [
        "store.signal(0)",          # member access is not the helper
        "signal < 3 ? 1 : 2",       # a comparison, not a call
        "signal",                   # mentioned, never called
        "mySignal<number>(0)",      # a different identifier
        "signalFoo<number>(0)",     # a different identifier
    ],
)
def test_non_calls_do_not_import_the_helper(expression):
    body = f"const n = {expression};"
    assert imports_of(body) == []


def test_a_locally_declared_name_is_never_imported():
    body = (
        "function signal(value) { return () => value; }\n"
        "export default { setup() { const n = signal<number>(0); return { n }; } };"
    )
    assert imports_of(body, setup=False) == []


def test_an_explicit_import_is_never_duplicated():
    body = (
        "import { signal } from './other.js';\n"
        "export default { setup() { const n = signal<number>(0); return { n }; } };"
    )
    assert imports_of(body, setup=False) == []


def test_explicit_create_names_still_import():
    body = "const n = createSignal<number>(0);"
    assert any("createSignal" in line and " as " not in line for line in imports_of(body))

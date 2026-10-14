"""Runtime contracts must accept supported features without hiding type errors."""

from pathlib import Path

import pytest

pytest.importorskip("pytscheck")

from teloce.typecheck import check_project


def check(tmp_path: Path, script: str, template: str = "<p>{{ count }}</p>"):
    root = tmp_path / "ui"
    root.mkdir(exist_ok=True)
    (root / "App.html").write_text(
        f'<template>{template}</template>\n<script lang="ts">\n{script}\n</script>'
    )
    return check_project([root], project_root=tmp_path)


@pytest.mark.parametrize(
    "hook",
    [
        "beforeCreate",
        "created",
        "beforeMount",
        "mounted",
        "beforeUpdate",
        "updated",
        "activated",
        "deactivated",
        "beforeUnmount",
        "unmounted",
    ],
)
def test_lifecycle_context_accepts_valid_and_rejects_invalid_assignment(tmp_path, hook):
    script = f'export default {{ data() {{ return {{ count: 1 }}; }}, {hook}() {{ this.count = 2; this.$emit("ready", this.count); }} }};'
    assert check(tmp_path, script).ok
    result = check(tmp_path, script.replace("this.count = 2", 'this.count = "bad"'))
    assert not result.ok and any(f.code == 2322 for f in result.findings)


def test_emits_attrs_watch_and_methods_keep_context(tmp_path):
    script = """export default {
      emits: ['save'], data() { return { count: 1 }; },
      watch: { count(value: number, previous: number) { this.save(); } },
      methods: { save() { this.$emit('save', { count: this.count }); const attrs: Record<string, unknown> = this.$attrs; } }
    };"""
    assert check(tmp_path, script, '<button @click="save()">{{ count }}</button>').ok
    assert not check(tmp_path, script.replace("this.save()", "this.svae()")).ok


@pytest.mark.parametrize("factory", ["signal", "createSignal", "toSignal"])
def test_signal_contract_preserves_value_type(tmp_path, factory):
    script = f"""const count = {factory}(1);
    count.set(2); count.update(value => value + 1);
    const stop = count.subscribe(value => console.log(value.toFixed())); stop();
    export default {{ data() {{ return {{ count }}; }} }};"""
    assert check(tmp_path, script, "<p>{{ count() }}</p>").ok
    result = check(
        tmp_path,
        script.replace("count.set(2)", 'count.set("bad")'),
        "<p>{{ count() }}</p>",
    )
    assert not result.ok and any(f.code == 2345 for f in result.findings)


def test_computed_effect_and_local_shadowing(tmp_path):
    script = """const count = signal(1);
    const doubled = computed(() => count() * 2);
    const watcher = effect(() => console.log(doubled())); watcher.stop();
    batch(() => count.set(untracked(() => count()) + 1));
    export default { data() { return { count: doubled() }; } };"""
    assert check(tmp_path, script).ok
    local = """function signal(value: string): string { return value; }
    const count = signal('hello'); export default { data() { return { count }; } };"""
    assert check(tmp_path, local).ok
    assert not check(tmp_path, local.replace("signal('hello')", "signal(1)")).ok


def test_implicit_signals_do_not_leak_into_ordinary_typescript(tmp_path):
    root = tmp_path / "ui"
    root.mkdir()
    (root / "plain.ts").write_text("export const count = signal(1);")
    result = check_project([root], project_root=tmp_path)
    assert not result.ok and any(f.code == 2304 for f in result.findings)


def test_conditional_template_narrowing_and_real_error(tmp_path):
    script = """export default { data() { return { user: null as { name: string } | null }; } };"""
    template = '<div v-if="user"><span>{{ user.name }}</span></div><p v-else>{{ user === null }}</p>'
    assert check(tmp_path, script, template).ok
    assert not check(tmp_path, script, template.replace("user.name", "user.missing")).ok
    assert not check(tmp_path, script, "<p>{{ user.name }}</p>").ok


def test_else_if_and_else_preserve_discriminated_union(tmp_path):
    script = """type Result = { kind: 'ok'; value: number } | { kind: 'error'; message: string } | null;
    export default { data() { return { result: null as Result }; } };"""
    template = """<p v-if="result === null">Empty</p>
    <p v-else-if="result.kind === 'ok'">{{ result.value.toFixed() }}</p>
    <p v-else>{{ result.message.toUpperCase() }}</p>"""
    assert check(tmp_path, script, template).ok
    assert not check(
        tmp_path, script, template.replace("result.message", "result.value")
    ).ok


def test_nested_loop_condition_and_void_element(tmp_path):
    script = """export default { data() { return { users: [] as ({ name: string } | null)[] }; } };"""
    template = '<div v-for="user in users"><input v-if="user" :value="user.name" /><span v-else>Empty</span></div>'
    assert check(tmp_path, script, template).ok


def test_prop_constructor_union_is_checked(tmp_path):
    script = """export default { props: { count: { type: [String, Number], required: true } }, methods: { show() { const value: string | number = this.count; } } };"""
    assert check(tmp_path, script).ok
    assert not check(tmp_path, script.replace("string | number", "boolean")).ok


def test_emitted_event_name_and_watch_value_are_checked(tmp_path):
    script = """export default {
      emits: ['save'], data() { return { count: 1 }; },
      watch: { count(value, previous) { const number: number = value; } },
      methods: { save() { this.$emit('save', this.count); } }
    };"""
    assert check(tmp_path, script).ok
    assert not check(
        tmp_path, script.replace("this.$emit('save'", "this.$emit('typo'")
    ).ok
    assert not check(
        tmp_path, script.replace("const number: number", "const number: string")
    ).ok


def test_expression_lexical_scopes_regex_and_comments():
    from teloce.typecheck.adapter import free_identifiers

    assert free_identifiers("items.map(item => item.name).join(',') + item") == [
        "item",
        "items",
    ]
    assert free_identifiers("/word/.test(title) /* ignoredName */") == ["title"]
    assert free_identifiers("items.map(({name}) => name + suffix)") == [
        "items",
        "suffix",
    ]
    assert free_identifiers(
        "(() => { const local = value; return local + extra; })()"
    ) == ["extra", "value"]


def test_default_parameter_references_respect_scope():
    from teloce.typecheck.adapter import free_identifiers

    assert free_identifiers("items.map((item = fallback) => item.name)") == [
        "fallback",
        "items",
    ]

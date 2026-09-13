"""Regression coverage for security and nested-template runtime helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from teloce.compiler import compile


def _node_eval(code: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for generated runtime hardening tests")
    module = tmp_path / "generated.mjs"
    module.write_text(code, encoding="utf-8")
    return subprocess.run([node, "--check", str(module)], capture_output=True, text=True, check=False)


def test_hardened_generated_runtime_is_valid_and_blocks_prototype_assignment(tmp_path: Path):
    source = '''
<template>
  <button @click="user.__proto__.polluted = true">Unsafe</button>
  <a :href="url">Link</a>
  <div v-html="content"></div>
</template>
<script>
export default { data() { return { url: "java\\nscript:alert(1)", content: "<script>bad()</script><p>ok</p>", user: {} }; } };
</script>
'''
    result = compile(source, "RuntimeHardening.vel", source_maps=False)
    assert result["success"], result["diagnostics"]
    assert "blocked" in result["code"]
    assert "__proto__" in result["code"]
    assert "__sanitizeHtml" in result["code"]
    checked = _node_eval(result["code"], tmp_path)
    assert checked.returncode == 0, checked.stderr


def test_nested_conditional_runtime_helper_is_emitted_as_valid_javascript(tmp_path: Path):
    source = '''
<template>
  <section v-if="outer"><p v-if="inner">yes</p></section>
</template>
<script>export default { data() { return { outer: true, inner: false }; } };</script>
'''
    result = compile(source, "NestedConditional.vel", source_maps=False)
    assert result["success"], result["diagnostics"]
    assert "__resolveIfBlocks" in result["code"]
    checked = _node_eval(result["code"], tmp_path)
    assert checked.returncode == 0, checked.stderr


def test_static_and_dynamic_class_bindings_are_merged_without_erasing_static_class(tmp_path: Path):
    source = '''
<template><button class="file-row" :class="{ active: selected }">Open</button></template>
<script>export default { data() { return { selected: true }; } };</script>
'''
    result = compile(source, "StaticDynamicClass.vel", source_maps=False)
    assert result["success"], result["diagnostics"]
    assert 'data-teloce-static-class=\\"file-row\\"' in result["code"]
    assert "element.__teloceStaticClass" in result["code"]
    checked = _node_eval(result["code"], tmp_path)
    assert checked.returncode == 0, checked.stderr


def test_standalone_runtime_preserves_imperative_widget_children(tmp_path: Path):
    source = '<template><div data-teloce-preserve><canvas></canvas></div></template>'
    result = compile(source, "PreservedWidget.vel", source_maps=False, shared_runtime=False)
    assert result["success"], result["diagnostics"]
    assert 'oldNode.hasAttribute("data-teloce-preserve")' in result["code"]
    checked = _node_eval(result["code"], tmp_path)
    assert checked.returncode == 0, checked.stderr

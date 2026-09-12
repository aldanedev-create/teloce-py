"""Keep the copy-paste signal-in-`.vel` lesson executable."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from teloce.build.builder import Builder
from teloce.compiler import compile

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "docs" / "lessons" / "36-signals-in-vel.md"


def test_shared_signal_vel_lesson_compiles_and_emits_valid_javascript(tmp_path: Path):
    content = LESSON.read_text(encoding="utf-8")
    blocks = re.findall(r"```html\s*\n([\s\S]*?)\n```", content)
    source = next(block for block in blocks if "Shared signal" in block and "signal(0)" in block)
    assert 'from "/static/teloce/signals.js"' not in source
    result = compile(
        source,
        "SharedCounter.vel",
        source_maps=False,
        shared_runtime_import="./teloce-runtime.js",
    )
    assert result["success"], result["diagnostics"]
    assert "createSignal" in result["code"]
    assert "createEffect" in result["code"]

    node = shutil.which("node")
    if node:
        emitted = tmp_path / "SharedCounter.mjs"
        emitted.write_text(result["code"], encoding="utf-8")
        checked = subprocess.run(
            [node, "--check", str(emitted)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stderr


def test_project_build_auto_wires_signal_runtime_without_component_imports(tmp_path: Path):
    source_dir = tmp_path / "static"
    source_dir.mkdir()
    (source_dir / "App.vel").write_text(
        """<template><button @click=\"increment\">{{ count }}</button></template>
<script>
const countSignal = signal(0)
export default {
  data() { return { count: countSignal() } },
  mounted() { this.sync = effect(() => { this.count = countSignal() }) },
  beforeUnmount() { this.sync?.stop() },
  methods: { increment() { countSignal.update(value => value + 1) } },
}
</script>
""",
        encoding="utf-8",
    )

    result = Builder({"shared_runtime": True, "source_maps": False}).build(tmp_path)
    assert result["failed"] == 0, result["errors"]

    output = tmp_path / "dist" / "static"
    app = output / "App.js"
    generated = app.read_text(encoding="utf-8")
    assert 'createSignal as signal' in generated
    assert 'createEffect as effect' in generated
    assert (output / "teloce-runtime.js").is_file()
    assert (output / "signals.js").is_file()
    assert (output / "scheduler.js").is_file()

    node = shutil.which("node")
    if node:
        for module in (output / "teloce-runtime.js", output / "signals.js", output / "scheduler.js", app):
            checked = subprocess.run(
                [node, "--check", str(module)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert checked.returncode == 0, (module, checked.stderr)

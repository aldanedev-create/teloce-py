from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_signal_runtime_public_api_and_effects(tmp_path: Path):
    runtime = Path(__file__).parents[2] / "src" / "teloce" / "runtime" / "signals.js"
    script = tmp_path / "signals.mjs"
    script.write_text(
        f"import {{ createSignal, createEffect, createComputed, batch, untracked, isSignal, isComputed }} from {runtime.as_uri()!r};\n"
        "const count = createSignal(1); const seen = [];\n"
        "const [destructured, setDestructured] = createSignal(2); setDestructured(3); if (destructured() !== 3) throw new Error('tuple signal API');\n"
        "const double = createComputed(() => count() * 2);\n"
        "const effect = createEffect(() => seen.push(double()));\n"
        "if (!isSignal(count) || !isComputed(double) || untracked(() => count()) !== 1) throw new Error('API');\n"
        "batch(() => { count.set(2); count.update(value => value + 1); });\n"
        "await Promise.resolve(); await Promise.resolve();\n"
        "if (double.get() !== 6 || seen.at(-1) !== 6) throw new Error(JSON.stringify({double: double.get(), seen}));\n"
        "if (seen.length !== 2) throw new Error('batch did not coalesce effects: ' + seen.length);\n"
        "effect.stop(); count.set(9); await Promise.resolve(); await Promise.resolve();\n"
        "if (seen.at(-1) !== 6) throw new Error('stop failed');\n",
        encoding="utf-8",
    )
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_modular_runtime_exports_reactive_component_dependencies(tmp_path: Path):
    runtime = Path(__file__).parents[2] / "src" / "teloce" / "runtime"
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    script = tmp_path / "modular.mjs"
    script.write_text(
        f"import {{ reactive, createEffect, isReactive }} from {str((runtime / 'runtime.js').as_uri())!r};\n"
        "const state = reactive({ count: 0 }); let observed = 0;\n"
        "createEffect(() => { observed = state.count; }); state.count = 4;\n"
        "await Promise.resolve(); if (!isReactive(state) || observed !== 4) throw new Error(String(observed));\n",
        encoding="utf-8",
    )
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_modular_component_reacts_and_unmounts_with_dom_stub(tmp_path: Path):
    runtime = Path(__file__).parents[2] / "src" / "teloce" / "runtime"
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    for name in ("component.js", "reactivity.js", "signals.js", "scheduler.js"):
        (tmp_path / name).write_text((runtime / name).read_text(encoding="utf-8"), encoding="utf-8")
    script = tmp_path / "component.mjs"
    script.write_text(
        "import { createComponent } from './component.js';\n"
        "const target = { children: [], replaceChildren(...children) { this.children = children; } };\n"
        "const elements = [];\n"
        "globalThis.document = { querySelector() { return target; }, createElement(tag) { const element = { tagName: tag.toUpperCase(), textContent: '', onclick: null }; elements.push(element); return element; }, createDocumentFragment() { return {}; } };\n"
        "const instance = createComponent({ data: () => ({ count: 0 }), render(state) { const button = document.createElement('button'); button.textContent = String(state.count); button.onclick = () => { state.count += 1; }; return button; } });\n"
        "instance.mount('#app'); if (target.children[0].textContent !== '0') throw new Error('initial render');\n"
        "target.children[0].onclick(); await Promise.resolve(); await Promise.resolve(); if (target.children[0].textContent !== '1') throw new Error('reactive render');\n"
        "instance.unmount(); if (target.children.length) throw new Error('unmount cleanup');\n",
        encoding="utf-8",
    )
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

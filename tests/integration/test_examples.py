"""Run the shipped example applications through the real build pipeline."""

import importlib
import importlib.util
import pkgutil
import subprocess
import shutil
import tempfile
from pathlib import Path

import teloce
from teloce.build.builder import Builder
from teloce.compiler.compiler import compile_file


ROOT = Path(__file__).parents[2]


def test_every_python_module_imports():
    modules = [module.name for module in pkgutil.walk_packages(teloce.__path__, "teloce.")]
    for name in modules:
        importlib.import_module(name)


def test_examples_compile_and_build():
    examples = sorted(path for path in (ROOT / "examples").iterdir() if path.is_dir())
    assert examples
    for example in examples:
        vel_files = sorted(example.rglob("*.vel"))
        build_options = {"dev": True, "clean": True}
        if not vel_files:
            # HTML-mode examples (such as flask-youtube-ssr) keep their components in ui/*.html.
            vel_files = sorted((example / "ui").rglob("*.html"))
            build_options.update({"html_mode": True, "source_roots": ["ui"]})
        assert vel_files, f"Example has no .vel or ui/*.html component: {example}"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / example.name
            shutil.copytree(example, workspace)
            for vel_file in vel_files:
                copied = workspace / vel_file.relative_to(example)
                result = compile_file(copied)
                assert result["success"], (vel_file, result["diagnostics"])
                assert result["code"]
                generated = workspace / ".test-dist" / copied.relative_to(workspace).with_suffix(".js")
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_text(result["code"], encoding="utf-8")
                checked = subprocess.run(["node", "--check", str(generated)], capture_output=True, text=True)
                assert checked.returncode == 0, (vel_file, checked.stderr)

            # A copied example may contain a generated manifest from a local
            # editable run. The test workspace must always exercise a full
            # rebuild instead of inheriting that cache.
            build = Builder(build_options).build(workspace)
            assert build["total"] == len(vel_files)
            assert build["compiled"] == len(vel_files)

            if example.name == "flask":
                spec = importlib.util.spec_from_file_location("flask_example_app", workspace / "app.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                client = module.create_app().test_client()
                assert client.get("/").status_code == 200
                assert client.get("/static/js/App.js").status_code == 200
                assert client.get("/api/health").get_json()["ok"] is True


def test_bundled_runtime_javascript_is_syntax_valid():
    runtime_dir = ROOT / "src" / "teloce" / "runtime"
    runtime_files = sorted(runtime_dir.glob("*.js"))
    assert runtime_files
    for runtime_file in runtime_files:
        checked = subprocess.run(["node", "--check", str(runtime_file)], capture_output=True, text=True)
        assert checked.returncode == 0, (runtime_file, checked.stderr)

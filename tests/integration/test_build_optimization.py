"""Production-build regression coverage for configuration and runtime sharing."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from teloce.build import build_project


def _write_project(root: Path, static_dir: str = "static") -> None:
    (root / "pyproject.toml").write_text("[project]\nname = \"build-audit\"\n", encoding="utf-8")
    source = root / static_dir / "js"
    source.mkdir(parents=True)
    (source / "Card.vel").write_text(
        """<template><article class=\"card\">{{ label }}</article></template>
<script>export default { props: { label: { type: String, default: \"Card\" } } };</script>
<style scoped>.card { padding: 1rem; border-radius: .5rem; }</style>""",
        encoding="utf-8",
    )
    (source / "App.vel").write_text(
        """<template><main><h1>{{ title }}</h1><Card :label=\"title\" /></main></template>
<script>
import Card from \"./Card.vel\";
export default {
  data() { return { title: \"Shared runtime\" }; },
  async mounted() { await Promise.resolve(); },
  components: { Card }
};
</script>
<style scoped>main { max-width: 48rem; margin: 0 auto; }</style>""",
        encoding="utf-8",
    )
    (root / "Ignored.vel").write_text(
        "<template><p>Do not build me from the configured static directory.</p></template>",
        encoding="utf-8",
    )


def _node_check(path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    check = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True, check=False
    )
    assert check.returncode == 0, check.stderr


def test_project_build_shares_runtime_and_minifies_modules(tmp_path: Path):
    _write_project(tmp_path)
    shared_out = tmp_path / "shared"
    embedded_out = tmp_path / "embedded"
    minified_out = tmp_path / "minified"

    shared = build_project(tmp_path, shared_out, options={"minify": False})
    embedded = build_project(
        tmp_path, embedded_out, options={"shared_runtime": False, "minify": False}
    )
    minified = build_project(tmp_path, minified_out, options={"minify": True})

    assert shared["failed"] == 0
    assert embedded["failed"] == 0
    assert minified["failed"] == 0
    assert shared["runtime"] == "static/teloce-runtime.js"
    runtime = shared_out / shared["runtime"]
    assert runtime.is_file()
    assert "__createReactive" in runtime.read_text(encoding="utf-8")

    shared_app = shared_out / "static" / "js" / "App.js"
    shared_card = shared_out / "static" / "js" / "Card.js"
    embedded_app = embedded_out / "static" / "js" / "App.js"
    minified_app = minified_out / "static" / "js" / "App.js"
    assert 'from "../teloce-runtime.js"' in shared_app.read_text(encoding="utf-8")
    assert 'from "../teloce-runtime.js"' in shared_card.read_text(encoding="utf-8")
    assert "teloce-runtime.js" not in embedded_app.read_text(encoding="utf-8")
    assert shared_app.stat().st_size < embedded_app.stat().st_size
    assert minified_app.stat().st_size < shared_app.stat().st_size
    assert (
        (minified_out / "static" / "teloce-runtime.js").stat().st_size
        < runtime.stat().st_size
    )
    _node_check(runtime)
    _node_check(shared_app)
    _node_check(shared_card)
    _node_check(minified_out / "static" / "teloce-runtime.js")
    _node_check(minified_app)


def test_cli_build_honors_teloce_config_json(tmp_path: Path):
    _write_project(tmp_path, static_dir="client")
    (tmp_path / "teloce.config.json").write_text(
        json.dumps(
            {
                "compiler": {"source_maps": False},
                "build": {
                    "out_dir": "release-assets",
                    "static_dir": "client",
                    "clean": True,
                    "minify": True,
                    "shared_runtime": True,
                    "tree_shake": True,
                },
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "teloce", "build"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = tmp_path / "release-assets"
    app_files = list((output / "client" / "js").glob("App.*.js"))
    runtime_files = list((output / "client").glob("teloce-runtime*.js"))
    assert len(app_files) == 1
    assert len(runtime_files) == 1
    app = app_files[0]
    assert app.is_file()
    assert not (output / "Ignored.js").exists()
    assert runtime_files[0].name in app.read_text(encoding="utf-8")
    assert not app.with_suffix(".js.map").exists()
    _node_check(app)


def test_create_scaffold_writes_production_build_defaults(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "teloce",
            "create",
            "configured-app",
            "--template",
            "flask",
            "--no-install",
            "--no-git",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((tmp_path / "configured-app" / "teloce.config.json").read_text(encoding="utf-8"))
    assert config["build"]["static_dir"] == "static"
    assert config["build"]["minify"] is True
    assert config["build"]["shared_runtime"] is True
    assert config["build"]["tree_shake"] is True

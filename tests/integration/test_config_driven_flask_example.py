"""Verify the example uses `teloce.config.json` as its real build contract."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for emitted module validation")
def test_config_driven_flask_example_uses_custom_source_and_shared_runtime(tmp_path: Path) -> None:
    pytest.importorskip("flask")
    project = tmp_path / "config-driven-flask"
    shutil.copytree(ROOT / "examples" / "config-driven-flask", project)

    _run(project, "-m", "teloce", "build")
    app_module = project / "public-assets" / "client" / "js" / "App.js"
    child_module = project / "public-assets" / "client" / "js" / "components" / "StatusCard.js"
    app_bundled = next((project / "public-assets" / "client" / "js").glob("App.*.js"))
    child_bundled = next((project / "public-assets" / "client" / "js" / "components").glob("StatusCard.*.js"))
    runtime = next((project / "public-assets" / "client").glob("teloce-runtime*.js"))
    assert app_module.is_file()
    assert child_module.is_file()
    assert app_bundled.is_file()
    assert child_bundled.is_file()
    assert runtime.is_file()
    assert not (project / "public-assets" / "static").exists()
    assert app_bundled.name in app_module.read_text(encoding="utf-8")
    assert child_bundled.name in child_module.read_text(encoding="utf-8")
    assert runtime.name in app_bundled.read_text(encoding="utf-8")
    assert runtime.name in child_bundled.read_text(encoding="utf-8")
    assert app_bundled.stat().st_size < 30_000

    _run(project, "-c", "from app import create_app; response = create_app().test_client().get('/'); assert response.status_code == 200; assert b'/static/js/App.js' in response.data")
    for module in (app_module, child_module, app_bundled, child_bundled, runtime):
        checked = subprocess.run(
            [shutil.which("node") or "node", "--check", str(module)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stderr

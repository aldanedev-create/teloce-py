"""Verify that a developer gets a useful fix, not only a raw error dump."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_compile_cli_prints_location_context_and_fix_suggestion(tmp_path: Path):
    source = tmp_path / "Broken.vel"
    source.write_text(
        "<template>\n  <main><p>Missing close\n</template>\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "teloce", "compile", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "ERROR" in result.stderr
    assert "Broken.vel" in result.stderr
    assert "Fix:" in result.stderr
    assert "closing tag" in result.stderr.lower()


def test_compile_cli_keeps_json_diagnostics_for_tooling(tmp_path: Path):
    source = tmp_path / "Broken.vel"
    source.write_text("<template><div>\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "teloce", "compile", "--json", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["errors"]
    assert payload["errors"][0]["filename"].endswith("Broken.vel")

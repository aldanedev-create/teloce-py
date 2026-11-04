import json
import subprocess
import sys
from pathlib import Path


EXAMPLE = Path(__file__).parents[2] / "examples" / "ssr-python"


def test_python_ssr_example_builds_hashed_artifacts():
    result = subprocess.run(
        [sys.executable, "app.py", "--build-only"],
        cwd=EXAMPLE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    dist = EXAMPLE / "dist"
    manifest = json.loads((dist / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["ssr"]["entries"]["ui/App.html"]
    assert (dist / entry["artifact"]).is_file()
    assert (dist / entry["client"]).is_file()
    assert "\\" not in entry["artifact"]
    assert "\\" not in entry["client"]

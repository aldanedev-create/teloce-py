"""Run the Node unit tests for runtime JavaScript (network clients, PWA plugin) in the normal suite."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_runtime_javascript_unit_tests():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required")
    suites = [str(path) for path in sorted(Path(__file__).parent.glob("*.test.mjs"))]
    result = subprocess.run([node, "--test", *suites], capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]

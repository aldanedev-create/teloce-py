"""Publishing uploads only fresh artifacts after successful build and validation."""

import importlib.util
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def publisher(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/publish.py"
    if not script.exists():
        script = Path(__file__).resolve().parents[2] / "scripts/publish.py"
    spec = importlib.util.spec_from_file_location("release_publisher", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: object())
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[2] == "build":
            output = Path(command[command.index("--outdir") + 1])
            (output / "example-1.0-py3-none-any.whl").write_text("wheel")
            (output / "example-1.0.tar.gz").write_text("source")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, calls


def test_build_only_never_uploads_and_ignores_stale_artifacts(publisher, tmp_path):
    module, calls = publisher
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/old-0.1.whl").write_text("stale")
    assert module.main(["--build-only"]) == 0
    assert len(calls) == 2
    assert calls[1][3:5] == ["check", "--strict"]
    assert all(
        "old-0.1.whl" not in argument for command in calls for argument in command
    )


def test_upload_uses_selected_repository_and_only_checked_files(publisher):
    module, calls = publisher
    assert module.main(["--repository", "testpypi", "--non-interactive"]) == 0
    upload = calls[-1]
    assert "https://test.pypi.org/legacy/" in upload
    assert "--non-interactive" in upload
    assert upload[-2:] == calls[-2][-2:]


def test_failed_validation_prevents_upload(publisher, monkeypatch):
    module, calls = publisher
    original = module.subprocess.run

    def fail_check(command, **kwargs):
        if "check" in command:
            raise subprocess.CalledProcessError(1, command)
        return original(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", fail_check)
    assert module.main([]) == 1
    assert not any("upload" in command for command in calls)


def test_missing_tools_explains_setup_without_building(publisher, monkeypatch):
    module, calls = publisher
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)
    assert module.main([]) == 2
    assert calls == []

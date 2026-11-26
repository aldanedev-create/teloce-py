"""AGENTS.md, CLAUDE.md and the offline docs that every Teloce project gets."""

import re
import subprocess
import sys
from argparse import Namespace
from importlib import resources
from pathlib import Path

import pytest

from teloce.ai import BACKENDS, DOCS_DIR, write_ai_files
from teloce.build import build_project
from teloce.cli.ai_docs import detect_backend
from teloce.cli.create import create_command
from teloce.cli.main import main

ROOT = Path(__file__).parents[2]


def make_project(tmp_path, monkeypatch, template="flask", **flags):
    monkeypatch.chdir(tmp_path)
    args = Namespace(name="news-app", template=template, no_install=True, no_git=True, **flags)
    assert create_command(args) == 0
    return tmp_path / "news-app"


def test_write_ai_files_renders_every_placeholder(tmp_path):
    result = write_ai_files(tmp_path, project_name="demo", backend="flask")
    assert (tmp_path / "AGENTS.md").is_file() and (tmp_path / "CLAUDE.md").is_file()
    assert result["skipped"] == []
    for path in result["written"]:
        assert "@@" not in path.read_text(encoding="utf-8"), path
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "**demo**" in agents and "python app.py" in agents and DOCS_DIR in agents


def test_claude_md_imports_agents_md(tmp_path):
    write_ai_files(tmp_path)
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.splitlines()[2] == "@AGENTS.md"


def test_existing_files_are_kept_unless_forced(tmp_path):
    (tmp_path / "AGENTS.md").write_text("mine", encoding="utf-8")
    result = write_ai_files(tmp_path)
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine"
    assert tmp_path / "AGENTS.md" in result["skipped"]
    write_ai_files(tmp_path, force=True)
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") != "mine"


def test_unknown_backend_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_ai_files(tmp_path, backend="rails")


@pytest.mark.parametrize("template", ["flask", "fastapi", "django", "flaxon", "basic"])
def test_every_generated_project_gets_the_files(tmp_path, monkeypatch, template):
    project = make_project(tmp_path, monkeypatch, template)
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert BACKENDS[template]["run"] in agents
    assert (project / "CLAUDE.md").is_file()
    assert (project / DOCS_DIR / "index.md").is_file()
    assert (project / DOCS_DIR / "known-issues.md").is_file()
    assert (project / DOCS_DIR / "directives.md").is_file()


def test_no_ai_docs_flag_skips_everything(tmp_path, monkeypatch):
    project = make_project(tmp_path, monkeypatch, no_ai_docs=True)
    assert not (project / "AGENTS.md").exists()
    assert not (project / "CLAUDE.md").exists()
    assert not (project / "docs").exists()


def test_generated_project_still_builds_with_the_docs_folder(tmp_path, monkeypatch):
    project = make_project(tmp_path, monkeypatch)
    build_project(project, options={"dev": True})
    assert (project / "dist" / "static" / "js" / "App.js").is_file()


def test_ai_docs_command_adds_files_to_an_existing_project(tmp_path, capsys):
    (tmp_path / "manage.py").write_text("", encoding="utf-8")
    assert detect_backend(tmp_path) == "django"
    assert main(["ai-docs", str(tmp_path)]) == 0
    assert "python manage.py runserver" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert main(["ai-docs", str(tmp_path)]) == 0
    assert "Kept" in capsys.readouterr().out


def test_ai_docs_command_no_docs_flag(tmp_path):
    assert main(["ai-docs", str(tmp_path), "--no-docs"]) == 0
    assert (tmp_path / "AGENTS.md").is_file()
    assert not (tmp_path / "docs").exists()


def test_detect_backend_reads_app_py(tmp_path):
    (tmp_path / "app.py").write_text("from fastapi import FastAPI", encoding="utf-8")
    assert detect_backend(tmp_path) == "fastapi"
    (tmp_path / "app.py").write_text("from flaxon import Flaxon", encoding="utf-8")
    assert detect_backend(tmp_path) == "flaxon"


def test_docs_index_only_links_to_files_that_exist():
    docs = resources.files("teloce.ai").joinpath("docs")
    names = {item.name for item in docs.iterdir()}
    index = docs.joinpath("index.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"`([a-z0-9-]+\.md)`", index))
    assert referenced, "index.md should reference docs"
    assert referenced <= names, referenced - names


def test_every_doc_named_in_agents_template_exists():
    package = resources.files("teloce.ai")
    names = {item.name for item in package.joinpath("docs").iterdir()}
    template = package.joinpath("templates", "AGENTS.md.tmpl").read_text(encoding="utf-8")
    for name in re.findall(r"`([a-z0-9-]+\.md)`", template):
        assert name in names or name in {"AGENTS.md", "CLAUDE.md"}, name


def test_curated_doc_copies_match_the_repository_docs():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_ai_docs.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_package_data_lists_the_ai_files():
    assert '"teloce.ai"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")

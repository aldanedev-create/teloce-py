"""``teloce ai-docs``: add AGENTS.md, CLAUDE.md and offline docs for AI assistants to a project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from teloce.ai import BACKENDS, DOCS_DIR, write_ai_files


def detect_backend(project_path: Path) -> str:
    """Guess the backend from the project files. Falls back to Flask."""
    if (project_path / "manage.py").exists():
        return "django"
    app_py = project_path / "app.py"
    if app_py.exists():
        source = app_py.read_text(encoding="utf-8", errors="replace").lower()
        if "flaxon" in source:
            return "flaxon"
        if "fastapi" in source:
            return "fastapi"
    return "flask"


def ai_docs_command(args: Any) -> int:
    """Write the AI assistant files into an existing project."""
    project_path = Path(getattr(args, "path", ".")).resolve()
    if not project_path.is_dir():
        print(f"Error: '{project_path}' is not a directory")
        return 1
    backend = getattr(args, "backend", None) or detect_backend(project_path)
    if backend not in BACKENDS:
        print(f"Error: unknown backend '{backend}'. Choose one of: {', '.join(sorted(BACKENDS))}")
        return 1
    result = write_ai_files(
        project_path,
        project_name=project_path.name,
        backend=backend,
        force=bool(getattr(args, "force", False)),
        docs=not getattr(args, "no_docs", False),
    )
    print(f"Backend: {backend}")
    print(f"Written: {len(result['written'])} file(s)")
    for path in result["written"][:3]:
        print(f"  {path.relative_to(project_path)}")
    if len(result["written"]) > 3:
        print(f"  ... and {len(result['written']) - 3} more under {DOCS_DIR}/")
    if result["skipped"]:
        print(f"Kept {len(result['skipped'])} existing file(s). Use --force to overwrite them.")
    return 0

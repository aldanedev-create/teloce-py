"""Files that help AI coding assistants work in a Teloce project.

``write_ai_files`` writes ``AGENTS.md``, ``CLAUDE.md`` and an offline copy of the Teloce reference docs
(``docs/teloce/``) into a project. ``teloce create`` calls it for every new project, and
``teloce ai-docs`` adds the same files to an existing one.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional

from teloce.version import __version__

__all__ = ["BACKENDS", "DOCS_DIR", "write_ai_files"]

DOCS_DIR = "docs/teloce"

# label, how to run, notes for the agent
BACKENDS: Dict[str, Dict[str, str]] = {
    "flask": {
        "label": "Flask",
        "run": "python app.py",
        "notes": (
            "- Entry point: `app.py`. `python app.py` builds the `.vel` files, then starts Flask with the reloader on "
            "http://127.0.0.1:5000.\n"
            "- Flask serves `dist/static` as its static folder and renders `templates/index.html`.\n"
            "- Add JSON routes with `@app.get(...)`, `@app.put(...)` and so on. Validate every payload on the server.\n"
            "- Teloce actions mount with `werkzeug.middleware.dispatcher.DispatcherMiddleware` at `/_teloce/actions` "
            "(see `docs/teloce/network-api.md`)."
        ),
    },
    "fastapi": {
        "label": "FastAPI",
        "run": "python app.py",
        "notes": (
            "- Entry point: `app.py`. It builds the `.vel` files when imported and runs uvicorn on "
            "http://127.0.0.1:8000.\n"
            "- `dist/static` is mounted at `/static`. `templates/index.html` imports `js/App.js` from there.\n"
            "- Teloce actions mount with `app.mount(\"/_teloce/actions\", actions.asgi_app)` "
            "(see `docs/teloce/network-api.md`)."
        ),
    },
    "django": {
        "label": "Django",
        "run": "python manage.py runserver",
        "notes": (
            "- Entry point: `manage.py`. It builds the `.vel` files, then runs the normal Django command.\n"
            "- Settings are in `site/settings.py`. `STATICFILES_DIRS` points at `dist/static`.\n"
            "- Teloce actions cannot be mounted as a sub-app in Django's ASGI handler. Route by path prefix "
            "(see `docs/teloce/network-api.md`)."
        ),
    },
    "flaxon": {
        "label": "Flaxon",
        "run": "python -m flaxon run app:app --reload",
        "notes": (
            "- Entry point: `app.py` (`app:app`). It builds the `.vel` files and registers every file under `dist/` "
            "at `/assets/...`.\n"
            "- `templates/index.html` imports `/assets/static/js/App.js`.\n"
            "- Routes are `async def` handlers registered with `@app.get(...)`."
        ),
    },
}
BACKENDS["basic"] = {**BACKENDS["flask"], "label": "Flask (basic template)"}


def _package_dir():
    return resources.files("teloce.ai")


def _render(text: str, values: Dict[str, str]) -> str:
    # Plain token replacement: the templates contain `{{ }}` and `$` from Teloce syntax.
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", value)
    return text


def write_ai_files(
    project_path,
    *,
    project_name: Optional[str] = None,
    backend: str = "flask",
    force: bool = False,
    docs: bool = True,
) -> Dict[str, List[Path]]:
    """Write ``AGENTS.md``, ``CLAUDE.md`` and ``docs/teloce/*.md`` into ``project_path``.

    Existing files are kept unless ``force`` is true. Returns ``{"written": [...], "skipped": [...]}``.
    """
    root = Path(project_path)
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Choose one of: {', '.join(sorted(BACKENDS))}")
    info = BACKENDS[backend]
    values = {
        "PROJECT_NAME": project_name or root.resolve().name,
        "BACKEND_LABEL": info["label"],
        "RUN_COMMAND": info["run"],
        "BACKEND_NOTES": info["notes"],
        "DOCS_DIR": DOCS_DIR,
        "TELOCE_VERSION": __version__,
    }
    written: List[Path] = []
    skipped: List[Path] = []

    def put(target: Path, text: str) -> None:
        if target.exists() and not force:
            skipped.append(target)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)

    templates = _package_dir() / "templates"
    put(root / "AGENTS.md", _render((templates / "AGENTS.md.tmpl").read_text(encoding="utf-8"), values))
    put(root / "CLAUDE.md", _render((templates / "CLAUDE.md.tmpl").read_text(encoding="utf-8"), values))

    if docs:
        for item in sorted(_package_dir().joinpath("docs").iterdir(), key=lambda entry: entry.name):
            if item.name.endswith(".md"):
                put(root / DOCS_DIR / item.name, _render(item.read_text(encoding="utf-8"), values))
    return {"written": written, "skipped": skipped}

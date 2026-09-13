"""Compile the `.vel` interface and generate the client router."""

from __future__ import annotations

from pathlib import Path

from teloce.build import build_project


ROOT = Path(__file__).resolve().parent


def build_assets() -> dict:
    result = build_project(
        ROOT,
        options={
            "dev": True,
            "clean": True,
            "source_maps": True,
            "shared_runtime": True,
            "spa_routes": {"RepoPage.js": "/repo/:id"},
        },
    )
    if result.get("failed"):
        errors = result.get("errors") or ["Unknown Teloce build error"]
        raise RuntimeError("\n".join(errors))
    return result


if __name__ == "__main__":
    result = build_assets()
    print(f"Compiled {result['compiled']} .vel component(s) and generated router.js")

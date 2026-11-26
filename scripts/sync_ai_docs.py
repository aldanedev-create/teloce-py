#!/usr/bin/env python3
"""Copy the curated reference docs into ``src/teloce/ai/docs``.

Those copies ship inside the wheel so ``teloce create`` and ``teloce ai-docs`` can give every project an
offline copy. Run this after editing any listed file in ``docs/``. ``--check`` only verifies (used by tests).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src" / "teloce" / "ai" / "docs"

# destination file name -> source path relative to the repository root
CURATED = {
    "cheatsheet.md": "docs/cheatsheet.md",
    "vel-syntax.md": "docs/vel-syntax.md",
    "template-syntax.md": "docs/template-syntax.md",
    "directives.md": "docs/directives.md",
    "directive-contracts.md": "docs/directive-contracts.md",
    "components.md": "docs/components.md",
    "reactivity.md": "docs/reactivity.md",
    "router.md": "docs/router.md",
    "network-api.md": "docs/network-api.md",
    "ssr-and-hydration.md": "docs/ssr-and-hydration.md",
    "plugins.md": "docs/plugins.md",
    "first-party-plugins.md": "docs/first-party-plugins.md",
    "security.md": "docs/security.md",
    "production.md": "docs/production.md",
    "errors.md": "docs/errors.md",
    "troubleshooting.md": "docs/troubleshooting.md",
    "cli.md": "docs/cli.md",
    "lesson-scrollytelling.md": "docs/lessons/43-scrollytelling.md",
    "lesson-sharing-and-exports.md": "docs/lessons/44-sharing-and-exports.md",
    "lesson-live-data.md": "docs/lessons/45-live-data.md",
    "lesson-use-actions.md": "docs/lessons/46-use-actions.md",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the copies are out of date")
    args = parser.parse_args()
    stale = []
    DEST.mkdir(parents=True, exist_ok=True)
    for name, source in CURATED.items():
        text = (ROOT / source).read_text(encoding="utf-8")
        target = DEST / name
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            stale.append(name)
            if not args.check:
                target.write_text(text, encoding="utf-8")
    if args.check and stale:
        print("Out of date (run scripts/sync_ai_docs.py): " + ", ".join(stale))
        return 1
    print(f"{'Checked' if args.check else 'Synced'} {len(CURATED)} docs; {len(stale)} changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

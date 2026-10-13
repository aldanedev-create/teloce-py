#!/usr/bin/env python3
"""Build, validate, and upload fresh release distributions with PyPA tools."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_URLS = {
    "pypi": "https://upload.pypi.org/legacy/",
    "testpypi": "https://test.pypi.org/legacy/",
}


def main(argv: list[str] | None = None) -> int:
    """Publish the checkout's current version, or only build and validate it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-only", action="store_true", help="Build and check without uploading"
    )
    parser.add_argument(
        "--repository",
        choices=UPLOAD_URLS,
        default="pypi",
        help="Upload target (default: pypi)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting for credentials",
    )
    args = parser.parse_args(argv)
    missing = [
        name for name in ("build", "twine") if importlib.util.find_spec(name) is None
    ]
    if missing:
        print(
            "Install publishing tools first: python -m pip install --upgrade build twine",
            file=sys.stderr,
        )
        return 2
    output_root = ROOT / "dist"
    output_root.mkdir(exist_ok=True)
    # Retain artifacts for inspection and isolate every invocation from stale dist files.
    output = Path(tempfile.mkdtemp(prefix="publish-", dir=output_root))
    print(f"Building release artifacts in {output}", flush=True)
    try:
        subprocess.run(  # noqa: S603 -- Fixed modules and freshly built artifact paths.
            [sys.executable, "-m", "build", "--outdir", str(output), str(ROOT)],
            cwd=ROOT,
            check=True,
        )
        wheels, sdists = sorted(output.glob("*.whl")), sorted(output.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise ValueError(
                "Expected exactly one fresh wheel and one source distribution"
            )
        artifacts = [str(path) for path in (*wheels, *sdists)]
        subprocess.run(  # noqa: S603 -- Fixed modules and freshly built artifact paths.
            [sys.executable, "-m", "twine", "check", "--strict", *artifacts],
            cwd=ROOT,
            check=True,
        )
        if not args.build_only:
            command = [
                sys.executable,
                "-m",
                "twine",
                "upload",
                "--repository-url",
                UPLOAD_URLS[args.repository],
            ]
            if args.non_interactive:
                command.append("--non-interactive")
            subprocess.run(  # noqa: S603 -- Fixed modules and freshly built artifact paths.
                [*command, *artifacts], cwd=ROOT, check=True
            )
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        print(
            f"Publishing failed: {error}. Artifacts retained in {output}",
            file=sys.stderr,
        )
        return 1
    print(f"{'Built and checked' if args.build_only else 'Published'}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

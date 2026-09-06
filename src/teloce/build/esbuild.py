"""Optional esbuild integration for production JavaScript output."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class EsbuildUnavailable(RuntimeError):
    """Raised when the optional esbuild executable is not installed."""


class EsbuildBundler:
    """Run esbuild without making it a mandatory Teloce dependency."""

    def __init__(self, project_root: str | Path, executable: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.executable = executable or self._find_executable()

    def _find_executable(self) -> str | None:
        """Prefer a project-local npm binary, then the system PATH."""
        local_dir = self.project_root / "node_modules" / ".bin"
        candidates = [local_dir / "esbuild", local_dir / "esbuild.cmd",
                      local_dir / "esbuild.exe"]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return shutil.which("esbuild")

    def bundle(self, entry: str | Path, output: str | Path | None = None, *,
               splitting: bool = True, minify: bool = False,
               sourcemap: bool = False, metafile: str | Path | None = None,
               target: str | None = None, drop: list[str] | None = None,
               legal_comments: str | None = None,
               charset: str | None = None) -> Path:
        if not self.executable:
            raise EsbuildUnavailable(
                "esbuild was requested but is not installed. Install it with "
                "npm install --save-dev esbuild, then rerun the build."
            )
        entry_path = Path(entry).resolve()
        output_path = Path(output).resolve() if output else entry_path.with_name(entry_path.stem + ".bundle.js")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.executable, str(entry_path), "--bundle", "--format=esm"]
        if splitting:
            # esbuild requires an output directory for multiple chunks.
            command.extend(["--splitting", f"--outdir={output_path.parent}",
                             f"--entry-names={output_path.stem.replace('.bundle', '')}.bundle"])
        else:
            command.append(f"--outfile={output_path}")
        if minify:
            command.append("--minify")
        if sourcemap:
            command.append("--sourcemap")
        if target:
            command.append(f"--target={target}")
        if drop:
            for name in drop:
                command.append(f"--drop:{name}")
        if legal_comments:
            command.append(f"--legal-comments={legal_comments}")
        if charset:
            command.append(f"--charset={charset}")
        if metafile:
            metafile_path = Path(metafile).resolve()
            metafile_path.parent.mkdir(parents=True, exist_ok=True)
            command.append(f"--metafile={metafile_path}")
        completed = subprocess.run(command, cwd=self.project_root,
                                   capture_output=True, text=True, check=False)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"esbuild failed ({completed.returncode}): {detail}")
        if not output_path.is_file():
            raise RuntimeError(f"esbuild completed without producing {output_path}")
        return output_path

    @staticmethod
    def read_metafile(path: str | Path) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))
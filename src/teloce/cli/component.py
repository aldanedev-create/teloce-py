"""Component-focused CLI commands."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from teloce.cli.compile import _print_diagnostics
from teloce.compiler.compiler import compile_file
from teloce.cli.server import start_dev_server


def _compile(path: Path, args: Any) -> tuple[int, dict[str, Any] | None]:
    result = compile_file(path, source_maps=bool(getattr(args, "source_map", False)), dev=False)
    if not result.get("success"):
        _print_diagnostics(path, result.get("diagnostics", {}), as_json=bool(getattr(args, "json", False)))
        return 1, result
    return 0, result


def _chrome_path() -> str | None:
    candidates = [
        shutil.which("chrome"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).exists()), None)


def _browser_mount_check(source_name: str, code: str) -> int:
    """Mount the generated module in a disposable real Chromium process."""
    chrome = _chrome_path()
    if not chrome:
        print("Browser test requested but Chrome/Chromium was not found.")
        return 2
    with tempfile.TemporaryDirectory(prefix="teloce-component-browser-") as directory:
        root = Path(directory)
        module = root / "Component.js"
        module.write_text(code, encoding="utf-8")
        (root / "index.html").write_text(
            '<!doctype html><title>boot</title><div id="app"></div>'
            '<script type="module">'
            'import { mount } from "./Component.js";'
            'try { mount("#app"); setTimeout(() => document.title = '
            'document.querySelector("#app")?.firstElementChild ? "mounted" : "empty", 50); } '
            'catch (error) { document.title = "error:" + error.message; }'
            '</script>',
            encoding="utf-8",
        )
        server = start_dev_server("127.0.0.1", 0, root, hmr=False)
        try:
            time.sleep(0.1)
            with tempfile.TemporaryDirectory(prefix="teloce-component-chrome-profile-") as profile:
                result = subprocess.run(
                    [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                     "--disable-extensions", "--disable-sync", "--no-first-run",
                     "--no-default-browser-check", f"--user-data-dir={profile}",
                     "--dump-dom", "--virtual-time-budget=1000",
                     f"http://127.0.0.1:{server.server_port}/?no_hmr=1"],
                    capture_output=True, text=True, timeout=30, check=False,
                )
            if result.returncode or "<title>mounted</title>" not in result.stdout:
                print(result.stderr or result.stdout)
                print(f"FAIL {source_name}: generated component did not mount in Chrome")
                return result.returncode or 1
            print(f"PASS {source_name}: mounted in Chrome")
            return 0
        finally:
            server.shutdown()
            server.server_close()


def component_command(args: Any) -> int:
    path = Path(args.source)
    if not path.is_file() or path.suffix.lower() != ".vel":
        print(f"Component source is not a .vel file: {path}")
        return 1
    code, result = _compile(path, args)
    if code:
        return code
    command = args.component_command
    if command == "check":
        print(f"OK {path}: template, script, and style compiled")
        return 0
    output = Path(args.output) if getattr(args, "output", None) else path.with_suffix(".js")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result["code"], encoding="utf-8")
    if result.get("css"):
        output.with_suffix(".css").write_text(result["css"], encoding="utf-8")
    if command == "build":
        print(f"Built {path} -> {output}")
        return 0
    if command == "test":
        node = shutil.which("node")
        if node:
            checked = subprocess.run([node, "--check", str(output)], capture_output=True, text=True, check=False)
            if checked.returncode:
                print(checked.stderr)
                return checked.returncode or 1
            print(f"PASS {path}: generated JavaScript syntax")
        else:
            print(f"PASS {path}: compiled (Node.js unavailable; browser syntax check skipped)")
        if getattr(args, "browser", False):
            browser_code = _browser_mount_check(str(path), result["code"])
            if browser_code:
                return browser_code
        return 0
    return 1

"""Real browser coverage for npm/CDN-style standalone Teloce usage."""

import shutil
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from teloce.cli.server import start_dev_server


_subprocess_run = subprocess.run


def _stable_chrome_run(command, *args, **kwargs):
    """Make repeated Windows headless-Chrome launches deterministic."""
    command = list(command)
    if "--headless=new" not in command:
        return _subprocess_run(command, *args, **kwargs)
    if "--dump-dom" in command:
        # dump-dom waits for a page to become quiescent. HMR's intentional
        # long-lived SSE/WebSocket connection prevents that, so disable HMR
        # for dump-only probes unless the caller already did so.
        for index, argument in enumerate(command):
            if str(argument).startswith("http") and "no_hmr=" not in str(argument):
                command[index] = f"{argument}{'&' if '?' in str(argument) else '?'}no_hmr=1"
    for flag in (
        "--disable-software-rasterizer",
        "--disable-extensions",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--no-first-run",
        "--no-default-browser-check",
    ):
        if flag not in command:
            command.insert(1, flag)
    kwargs["timeout"] = min(kwargs.get("timeout", 60), 60)
    failure = None
    for _attempt in range(3):
        # A timed-out Chrome process can keep its profile lock and continue
        # consuming resources on Windows.  Give every attempt an isolated
        # profile and explicitly reap the process before retrying.
        profile = Path(tempfile.mkdtemp(prefix="teloce-chrome-"))
        process = None
        try:
            attempt_command = [arg for arg in command if not str(arg).startswith("--user-data-dir=")]
            attempt_command.append(f"--user-data-dir={profile}")
            run_kwargs = dict(kwargs)
            timeout = run_kwargs.pop("timeout", 30)
            if run_kwargs.pop("capture_output", False):
                run_kwargs["stdout"] = subprocess.PIPE
                run_kwargs["stderr"] = subprocess.PIPE
            process = subprocess.Popen(attempt_command, *args, **run_kwargs)
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return subprocess.CompletedProcess(attempt_command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired as error:
                failure = error
                if os.name == "nt":
                    _subprocess_run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.kill()
                process.communicate()
        finally:
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    _subprocess_run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.kill()
                process.communicate()
            # Chrome can briefly retain cache-file handles after its headless
            # parent exits on Windows. Cleanup is best-effort test hygiene and
            # must never turn a successful browser assertion into a failure.
            for _cleanup_attempt in range(20):
                try:
                    shutil.rmtree(profile)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    time.sleep(0.1)
            else:
                shutil.rmtree(profile, ignore_errors=True)
    raise failure


subprocess.run = _stable_chrome_run


def _chrome() -> str | None:
    candidate = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    return str(candidate) if candidate.exists() else None


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_create_app_reacts_to_events_in_real_chrome(tmp_path: Path):
    shutil.copy(Path(__file__).parents[2] / "src/teloce/runtime/standalone.js", tmp_path / "teloce.js")
    (tmp_path / "index.html").write_text(
        '<div id="app"><h1>{{ name }}</h1><button @click="count++">{{ count }}</button></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", {name: "Python", count: 0}); '
        'setTimeout(() => { document.querySelector("button").click(); setTimeout(() => document.title = document.querySelector("button").textContent, 50); }, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu",
             "--disable-software-rasterizer", "--disable-extensions", "--disable-sync",
             "--disable-background-networking", "--disable-component-update",
             "--no-first-run", "--no-default-browser-check", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/?no_hmr=1"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>1</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()
@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_invokes_event_methods_with_state_context(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><button @click="increment">{{ count }}</button></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { count: 0, increment() { this.count += 1; } });'
        'setTimeout(() => { document.querySelector("button").click(); setTimeout(() => document.title = document.querySelector("button").textContent, 50); }, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu",
             "--disable-software-rasterizer", "--disable-extensions", "--disable-sync",
             "--disable-background-networking", "--disable-component-update",
             "--no-first-run", "--no-default-browser-check", "--dump-dom",
             "--virtual-time-budget=1200", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>1</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_standalone_supports_npm_style_directives(tmp_path: Path):
    (tmp_path / "teloce.js").write_text(
        Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text(
        '<div id="app"><p v-if="visible">Visible</p><strong>{{ name | capitalize }}</strong>'
        '<span v-for="(item, index) in items">{{ index }}:{{ item }}</span></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { visible: false, name: "hello world", items: ["A", "B"] });'
        'setTimeout(() => document.title = document.querySelector("#app").textContent, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1200", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "Hello world0:A1:B" in result.stdout
        assert "Visible" not in result.stdout.split("<title>", 1)[-1].split("</title>", 1)[0]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_standalone_plugin_directive_runs_render_hook_in_real_chrome(tmp_path: Path):
    (tmp_path / "teloce.js").write_text(
        Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text(
        '<div id="app"><p v-highlight="name">original</p></div>'
        '<script src="/teloce.js"></script><script>teloce.use({ directives: [{ name: "highlight", render(el, binding) { el.textContent = binding.value.toUpperCase(); } }] });'
        'teloce.createApp("#app", { name: "plugin works" }); setTimeout(() => document.title = document.querySelector("p").textContent, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>PLUGIN WORKS</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_supports_v_else_if_and_v_else(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><p v-if="first">first</p><p v-else-if="second">second</p><p v-else>fallback</p></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { first: false, second: true });'
        'setTimeout(() => document.title = document.querySelector("#app").textContent, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>second</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_supports_v_model_alias_and_selects(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><input v-model="name"><select v-model="choice"><option value="b">B</option></select><p>{{ name }}:{{ choice }}</p></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { name: "A", choice: "a" });'
        'setTimeout(() => { const input = document.querySelector("input"); input.value = "C"; input.dispatchEvent(new Event("input", {bubbles: true})); const select = document.querySelector("select"); select.value = "b"; select.dispatchEvent(new Event("change", {bubbles: true})); setTimeout(() => document.title = document.querySelector("p").textContent, 50); }, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1200", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>C:b</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_reacts_to_nested_objects_and_arrays(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><p>{{ user.name }}:{{ items.length }}</p><button @click="(user.name = \'B\', items.push(2))">Change</button></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { user: { name: "A" }, items: [1] });'
        'setTimeout(() => { document.querySelector("button").click(); setTimeout(() => document.title = document.querySelector("p").textContent, 50); }, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1500", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>B:2</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_standalone_loop_events_keep_live_item_scope(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><button v-for="item in items" @click="item.done = !item.done">{{ item.name }}:{{ item.done }}</button></div>'
        '<script src="/teloce.js"></script><script>teloce.createApp("#app", { items: [{name: "A", done: false}, {name: "B", done: false}] });'
        'setTimeout(() => { document.querySelectorAll("button")[1].click(); setTimeout(() => document.title = document.querySelector("#app").textContent, 50); }, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1500", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "A:falseB:true" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_standalone_plugin_component_renders_props(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime", "standalone.js")
    (tmp_path / "teloce.js").write_text(runtime.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><Badge label="Ready"></Badge><p>{{ hello() }}</p></div>'
        '<script src="/teloce.js"></script><script>teloce.use({ helpers: { hello() { return "works"; } }, components: { Badge: { render(el, props) { return "<strong>" + props.label + "</strong>"; } } } });'
        'teloce.createApp("#app", {}); setTimeout(() => document.title = document.querySelector("strong").textContent + ":" + document.querySelector("p").textContent, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>Ready:works</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_modular_runtime_preserves_static_classes_with_dynamic_class_helper(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime")
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    for name in ("dom.js", "signals.js", "scheduler.js"):
        (tmp_path / name).write_text((runtime / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"><button class="base">Ready</button></div>'
        '<script type="module">import { createClass } from "/dom.js"; import { createSignal } from "/signals.js"; '
        'const source = createSignal("active"); createClass(document.querySelector("button"), source); '
        'setTimeout(() => document.title = document.querySelector("button").className, 50);</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>base active</title>" in result.stdout
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(_chrome() is None, reason="Chrome is not installed")
def test_lazy_component_does_not_mount_after_unmount(tmp_path: Path):
    runtime = Path(__file__).parents[2].joinpath("src", "teloce", "runtime")
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    for name in ("component.js", "reactivity.js", "signals.js", "scheduler.js"):
        (tmp_path / name).write_text((runtime / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div id="app"></div>'
        '<script type="module">import { defineAsyncComponent } from "/component.js"; '
        'const lazy = defineAsyncComponent(() => new Promise(resolve => setTimeout(() => resolve({default: {mount(target) { target.textContent = "STALE"; return { unmount() {} }; }}}), 100))); '
        'const pending = lazy.mount("#app"); lazy.unmount(); pending.then(() => setTimeout(() => document.title = document.querySelector("#app").textContent || "empty", 120));</script>',
        encoding="utf-8",
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path, hmr=False)
    try:
        time.sleep(0.1)
        result = subprocess.run(
            [_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--dump-dom",
             "--virtual-time-budget=1000", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "<title>empty</title>" in result.stdout
        assert "<title>STALE</title>" not in result.stdout
    finally:
        server.shutdown()
        server.server_close()

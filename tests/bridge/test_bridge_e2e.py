"""End to end: the real browser-side JS clients against real Python servers.

HTTP actions run through wsgiref; WebSocket channels run through uvicorn. Both halves of the
protocol are exercised together so they cannot drift apart. Skipped when node/uvicorn are missing.
"""
import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

from teloce.bridge import ActionError, ActionRegistry, Bridge, ChannelHub, allow_all

NODE = shutil.which("node")
NETWORK_JS = (Path(__file__).resolve().parents[2] / "src" / "teloce" / "runtime" / "network.js").as_posix()

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")


def run_node(script: str, tmp_path: Path, timeout: int = 40):
    path = tmp_path / "scenario.mjs"
    path.write_text(f"import * as net from {json.dumps('file://' + NETWORK_JS)};\n{script}", encoding="utf-8")
    result = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------- HTTP actions
@pytest.fixture()
def http_server():
    counter = {"calls": 0}
    registry = ActionRegistry(
        max_body_bytes=2_000,
        authorize=lambda request: request.cookies.get("sid") == "ok" or request.name in ("todos.create", "stats", "validate", "boom", "big"),
    )

    @registry.action("todos.create")
    def create(data):
        if not data or not data.get("title"):
            raise ActionError("validation_error", "Title is required", status=422, details={"title": ["required"]})
        return {"id": 1, "title": data["title"]}

    @registry.action("stats")
    def stats(data):
        counter["calls"] += 1
        return {"n": counter["calls"]}

    @registry.action("validate")
    def validate(data):
        raise ActionError("out_of_stock", "Sold out", status=409)

    @registry.action("boom")
    def boom(data):
        raise RuntimeError("secret")

    @registry.action("big")
    def big(data):
        return len(json.dumps(data))

    @registry.action("private")
    def private(data):
        return "classified"

    class Quiet(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    server = make_server("127.0.0.1", 0, registry.wsgi_app, handler_class=Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", counter
    server.shutdown()


def test_action_client_against_a_real_server(http_server, tmp_path):
    base, counter = http_server
    out = run_node(f"""
const action = new net.ActionClient({{ baseURL: {json.dumps(base)}, actionPath: '/_teloce/actions' }});
const r = {{}};
r.created = await action.call('todos.create', {{ title: 'Write docs' }});
r.invalid = await action.call('todos.create', {{}});
r.conflict = await action.call('validate', null);
r.unknown = await action.call('nope', null);
r.forbidden = await action.call('private', null);
r.boom = await action.call('boom', null);
r.toobig = await action.call('big', {{ blob: 'x'.repeat(5000) }});
const a = await action.call('stats', null, {{ cache: {{ ttl: 5000 }} }});
const b = await action.call('stats', null, {{ cache: {{ ttl: 5000 }} }});
action.invalidate('stats');
const c = await action.call('stats', null, {{ cache: {{ ttl: 5000 }} }});
r.cache = [a.data.n, b.data.n, c.data.n];
const res = action.resource('stats', null);
await new Promise(ok => setTimeout(ok, 150));
r.resource = [res.data(), res.loading(), res.error()];
console.log(JSON.stringify(r));
""", tmp_path)
    assert out["created"] == {"success": True, "status": 200, "data": {"id": 1, "title": "Write docs"}}
    assert out["invalid"]["status"] == 422 and out["invalid"]["code"] == "validation_error"
    assert out["invalid"]["details"] == {"title": ["required"]}
    assert (out["conflict"]["status"], out["conflict"]["code"]) == (409, "out_of_stock")
    assert (out["unknown"]["status"], out["unknown"]["code"]) == (404, "action_not_found")
    assert (out["forbidden"]["status"], out["forbidden"]["code"]) == (403, "forbidden")
    assert out["boom"]["status"] == 500 and "secret" not in json.dumps(out["boom"])
    assert (out["toobig"]["status"], out["toobig"]["code"]) == (413, "payload_too_large")
    assert out["cache"] == [1, 1, 2]                       # second call cached, invalidate forces a new one
    assert out["resource"][0]["n"] >= 3 and out["resource"][1:] == [False, None]


def test_server_rejects_what_the_client_does_not_send(http_server, tmp_path):
    base, _ = http_server
    out = run_node(f"""
const http = new net.HttpClient({{ baseURL: {json.dumps(base)} }});
const url = '/_teloce/actions/stats';
const r = {{}};
r.noHeader = (await http.post(url, {{ data: null }})).data.code;                       // missing X-Teloce-Action
r.withHeader = (await http.post(url, {{ data: null }}, {{ headers: {{ 'X-Teloce-Action': '1' }} }})).status;
r.formPost = (await http.post(url, new URLSearchParams({{ a: '1' }}), {{ headers: {{ 'X-Teloce-Action': '1' }} }})).status;
r.get = (await http.get(url)).status;
r.badOrigin = (await http.post(url, {{ data: null }}, {{ headers: {{ 'X-Teloce-Action': '1', Origin: 'https://evil.test' }} }})).status;
console.log(JSON.stringify(r));
""", tmp_path)
    assert out["noHeader"] == "csrf_failed" and out["withHeader"] == 200
    assert out["formPost"] == 415 and out["get"] in (403, 405)
    assert out["badOrigin"] in (200, 403)  # fetch strips a forbidden Origin header; real browsers always send theirs


# ---------------------------------------------------------------------------- WebSocket channels
@pytest.fixture()
def ws_server():
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("websockets")
    hub = ChannelHub(authorize=lambda c, action, channel: channel.startswith("chat") or channel == "alerts")
    bridge = Bridge(channels=hub)
    port = free_port()
    config = uvicorn.Config(bridge.asgi_app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    server = uvicorn.Server(config)
    loop_holder = {}

    def serve():
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    yield f"ws://127.0.0.1:{port}/socket", hub, loop_holder["loop"]
    server.should_exit = True
    thread.join(timeout=5)


def test_socket_client_against_a_real_asgi_server(ws_server, tmp_path):
    url, hub, loop = ws_server
    out = run_node(f"""
const opts = {{ url: {json.dumps(url)}, reconnect: {{ enabled: false }} }};
const a = new net.SocketClient({{ ...opts, heartbeat: {{ enabled: true, interval: 60, timeout: 250 }} }});
const b = new net.SocketClient(opts);
const wait = ms => new Promise(ok => setTimeout(ok, ms));
const r = {{ got: [], errors: [] }};
a.on('message', e => {{ if (e.data?.type === 'error') r.errors.push(e.data.code); }});
b.on('message', e => {{ if (e.data?.type === 'error') r.errors.push(e.data.code); }});
a.send({{ type: 'ping' }});                 // queued before connect: must be flushed on open
await Promise.all([a.connect(), b.connect()]);
b.subscribe('chat', (data, msg) => r.got.push([data, msg.channel]));
a.subscribe('private', () => {{}});         // refused by the server's authorize hook
await wait(120);
a.publish('chat', {{ text: 'hello', n: 1 }});
a.publish('private', 'nope');
await wait(120);
await wait(500);                             // several heartbeat rounds: must stay connected
r.stillOpen = a.state === 'open';
b.close(); a.close();
console.log(JSON.stringify(r));
""", tmp_path)
    assert out["got"] == [[{"text": "hello", "n": 1}, "chat"]]
    assert out["errors"].count("forbidden") >= 2          # subscribe + publish to "private"
    assert out["stillOpen"] is True                       # heartbeat ping/pong works end to end


def test_server_push_and_unsubscribe_over_a_real_socket(ws_server, tmp_path):
    url, hub, loop = ws_server
    script = f"""
const s = new net.SocketClient({{ url: {json.dumps(url)}, reconnect: {{ enabled: false }} }});
const wait = ms => new Promise(ok => setTimeout(ok, ms));
const seen = [];
await s.connect();
const off = s.subscribe('alerts', d => seen.push(d));
await wait(150);
console.error('READY');
await wait(400);
off();
await wait(150);
console.log(JSON.stringify({{ seen }}));
s.close();
"""
    path = tmp_path / "push.mjs"
    path.write_text(f"import * as net from {json.dumps('file://' + NETWORK_JS)};\n{script}", encoding="utf-8")
    proc = subprocess.Popen([NODE, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 10
    while hub.subscribers("alerts") == 0 and time.time() < deadline:
        time.sleep(0.02)
    assert hub.subscribers("alerts") == 1
    delivered = asyncio.run_coroutine_threadsafe(hub.publish("alerts", {"level": "high"}), loop).result(5)
    assert delivered == 1
    out, err = proc.communicate(timeout=20)
    assert proc.returncode == 0, err
    assert json.loads(out.strip().splitlines()[-1])["seen"] == [{"level": "high"}]
    deadline = time.time() + 5
    while hub.subscribers("alerts") and time.time() < deadline:
        time.sleep(0.02)
    assert hub.subscribers("alerts") == 0                  # unsubscribe/close cleaned up server-side

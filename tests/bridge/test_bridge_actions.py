"""Framework-agnostic server actions: protocol, security defaults and the WSGI/ASGI apps."""
import asyncio
import dataclasses
import datetime
import decimal
import io
import json
import logging
import threading
import uuid

import pytest

from teloce.bridge import ActionError, ActionRegistry

JSON = {"content-type": "application/json", "x-teloce-action": "1"}


def body(data=None, **extra):
    return json.dumps({"data": data, **extra}).encode()


def make_registry(**kwargs):
    registry = ActionRegistry(**kwargs)

    @registry.action("math.add")
    def add(data):
        return data["a"] + data["b"]

    @registry.action("whoami")
    def whoami(data, ctx):
        return {"cookie": ctx.cookies.get("sid"), "name": ctx.name}

    @registry.action("boom")
    def boom(data):
        raise RuntimeError("secret database password")

    @registry.action("reject")
    def reject(data):
        raise ActionError("out_of_stock", "Sold out", status=409, details={"sku": data["sku"]})

    @registry.action("later")
    async def later(data):
        await asyncio.sleep(0)
        return {"thread": threading.current_thread().name}

    @registry.action("sync.thread")
    def sync_thread(data):
        return threading.current_thread().name

    @registry.action("rich")
    def rich(data):
        @dataclasses.dataclass
        class Row:
            id: int

        return {
            "when": datetime.datetime(2026, 1, 2, 3, 4, 5), "price": decimal.Decimal("1.50"),
            "id": uuid.UUID(int=7), "row": Row(3), "tags": {"b", "a"},
        }

    @registry.action("unserializable")
    def unserializable(data):
        return object()

    return registry


def call(registry, name, data=None, *, method="POST", headers=None, **kwargs):
    return registry.handle(method, f"/_teloce/actions/{name}", headers or JSON, body(data), **kwargs)


# ---------------------------------------------------------------- protocol
def test_success_envelope():
    response = call(make_registry(), "math.add", {"a": 2, "b": 3})
    assert (response.status, response.body) == (200, {"success": True, "data": 5})


def test_unknown_and_invalid_names_are_404_and_never_resolve_paths():
    registry = make_registry()
    for name in ("nope", "..%2Fetc", "a/b", "../math.add", "", "x" * 300):
        response = registry.handle("POST", f"/_teloce/actions/{name}", JSON, body())
        assert response.status == 404 and response.body["code"] == "action_not_found", name


def test_only_post_is_allowed():
    response = call(make_registry(), "math.add", {"a": 1, "b": 1}, method="GET")
    assert response.status == 405 and response.headers["allow"] == "POST"


def test_content_type_and_body_validation():
    registry = make_registry()
    bad_type = registry.handle("POST", "/_teloce/actions/math.add", {"x-teloce-action": "1", "content-type": "text/plain"}, body())
    assert bad_type.status == 415
    assert registry.handle("POST", "/_teloce/actions/math.add", JSON, b"{nope").body["code"] == "invalid_json"
    assert registry.handle("POST", "/_teloce/actions/math.add", JSON, b"[1,2]").body["code"] == "invalid_body"
    assert registry.handle("POST", "/_teloce/actions/math.add", JSON, b"\xff\xfe").body["code"] == "invalid_json"


def test_body_size_limit_even_when_body_was_not_read():
    registry = make_registry(max_body_bytes=100)
    assert call(registry, "math.add", {"a": "x" * 500, "b": 1}).status == 413
    declared = registry.handle("POST", "/_teloce/actions/math.add", JSON, b"", content_length=10_000)
    assert declared.status == 413


def test_prefix_is_optional_in_the_path():
    registry = make_registry()
    assert registry.handle("POST", "/math.add", JSON, body({"a": 1, "b": 2})).body["data"] == 3
    assert registry.handle("POST", "math.add?x=1", JSON, body({"a": 1, "b": 2})).body["data"] == 3


# ---------------------------------------------------------------- csrf / origin
def test_csrf_requires_action_header():
    response = call(make_registry(), "math.add", {"a": 1, "b": 1}, headers={"content-type": "application/json"})
    assert response.status == 403 and response.body["code"] == "csrf_failed"


def test_origin_must_match_host_or_be_allowed():
    registry = make_registry(allowed_origins=["https://app.example.com/"])
    ok_same = call(registry, "math.add", {"a": 1, "b": 1}, headers={**JSON, "origin": "https://api.example.com", "host": "api.example.com"})
    ok_listed = call(registry, "math.add", {"a": 1, "b": 1}, headers={**JSON, "origin": "https://app.example.com", "host": "api.example.com"})
    evil = call(registry, "math.add", {"a": 1, "b": 1}, headers={**JSON, "origin": "https://evil.test", "host": "api.example.com"})
    opaque = call(registry, "math.add", {"a": 1, "b": 1}, headers={**JSON, "origin": "null", "host": "api.example.com"})
    assert ok_same.status == 200 and ok_listed.status == 200
    assert evil.status == 403 and opaque.status == 403


def test_csrf_can_be_replaced_or_disabled():
    custom = make_registry(csrf=lambda request: request.headers.get("x-token") == "good")
    assert call(custom, "math.add", {"a": 1, "b": 1}, headers={"content-type": "application/json", "x-token": "good"}).status == 200
    assert call(custom, "math.add", {"a": 1, "b": 1}, headers={"content-type": "application/json"}).status == 403
    off = make_registry(csrf=False)
    assert call(off, "math.add", {"a": 1, "b": 1}, headers={"content-type": "application/json"}).status == 200


# ---------------------------------------------------------------- authorization
def test_authorize_hook_and_public_actions():
    registry = ActionRegistry(authorize=lambda request: request.cookies.get("sid") == "ok")
    registry.register("private", lambda data: "secret")
    registry.register("open", lambda data: "hello", public=True)
    assert call(registry, "private").status == 403
    assert call(registry, "private", cookies={"sid": "ok"}).body["data"] == "secret"
    assert call(registry, "open").body["data"] == "hello"


def test_authorize_can_raise_401_and_be_async_and_per_action():
    async def authorize(request):
        if "authorization" not in request.headers:
            raise ActionError("unauthenticated", "Sign in", status=401)
        return True

    registry = ActionRegistry(authorize=authorize)
    registry.register("a", lambda data: 1, auth=lambda request: request.headers["authorization"] == "admin")
    assert call(registry, "a").status == 401
    assert call(registry, "a", headers={**JSON, "authorization": "user"}).status == 403
    assert call(registry, "a", headers={**JSON, "authorization": "admin"}).status == 200


# ---------------------------------------------------------------- results and errors
def test_action_error_is_structured():
    response = call(make_registry(), "reject", {"sku": "X1"})
    assert response.status == 409
    assert response.body == {"success": False, "error": "Sold out", "code": "out_of_stock", "details": {"sku": "X1"}}


def test_unexpected_errors_are_generic_and_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="teloce.bridge"):
        response = call(make_registry(), "boom")
    assert response.status == 500 and response.body["code"] == "internal_error"
    assert "secret" not in json.dumps(response.body)
    assert "secret database password" in caplog.text


def test_rich_results_are_json_encoded():
    data = call(make_registry(), "rich").to_bytes()
    decoded = json.loads(data)["data"]
    assert decoded == {"when": "2026-01-02T03:04:05", "price": "1.50", "id": str(uuid.UUID(int=7)), "row": {"id": 3}, "tags": ["a", "b"]}


def test_unserializable_result_becomes_500_in_wsgi():
    registry = make_registry()
    status, headers, payload = wsgi(registry, "unserializable", {})
    assert status.startswith("500") and json.loads(payload)["code"] == "internal_error"


def test_context_gets_cookies_and_name():
    response = call(make_registry(), "whoami", cookies={"sid": "abc"})
    assert response.body["data"] == {"cookie": "abc", "name": "whoami"}


# ---------------------------------------------------------------- handler shapes
def test_handler_signatures():
    registry = ActionRegistry(csrf=False)
    registry.register("none", lambda: "none")
    registry.register("data", lambda data: data)
    registry.register("pos2", lambda payload, context: [payload, context.name])
    registry.register("ctx", lambda ctx: ctx.name)
    registry.register("req", lambda request: request.method)
    out = lambda name, d=None: registry.handle("POST", f"/{name}", {"content-type": "application/json"}, body(d)).body["data"]
    assert out("none") == "none" and out("data", 5) == 5 and out("pos2", 1) == [1, "pos2"]
    assert out("ctx") == "ctx" and out("req") == "POST"


def test_registration_rules():
    registry = ActionRegistry()
    registry.register("a", lambda data: 1)
    with pytest.raises(ValueError):
        registry.register("a", lambda data: 2)
    with pytest.raises(ValueError):
        registry.register("../bad", lambda data: 2)

    @registry.action
    def bare(data):
        return 1

    assert registry.names() == ["a", "bare"]


def test_async_and_sync_handlers_in_both_entry_points():
    registry = make_registry()
    assert call(registry, "later").status == 200  # async handler via the sync entry point

    async def run():
        response = await registry.handle_async("POST", "/sync.thread", JSON, body())
        return response.body["data"], threading.current_thread().name

    worker, main = asyncio.run(run())
    assert worker != main  # sync handlers must not block the event loop


def test_sync_entry_point_works_inside_a_running_loop():
    registry = make_registry()

    async def run():
        return call(registry, "math.add", {"a": 4, "b": 5}).body["data"]

    assert asyncio.run(run()) == 9


# ---------------------------------------------------------------- WSGI
def wsgi(registry, name, data, *, prefix="/_teloce/actions/", headers=None, content_length=None, raw=None):
    payload = raw if raw is not None else body(data)
    environ = {
        "REQUEST_METHOD": "POST", "PATH_INFO": f"{prefix}{name}", "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(payload) if content_length is None else content_length),
        "wsgi.input": io.BytesIO(payload), "HTTP_X_TELOCE_ACTION": "1", "HTTP_COOKIE": "sid=abc; theme=dark",
    }
    environ.update(headers or {})
    captured = {}

    def start_response(status, headers):
        captured["status"], captured["headers"] = status, dict(headers)

    out = b"".join(registry.wsgi_app(environ, start_response))
    return captured["status"], captured["headers"], out


def test_wsgi_mounted_and_unmounted_and_headers():
    registry = make_registry()
    for prefix in ("/_teloce/actions/", "/"):  # full path, or mounted at the prefix
        status, headers, out = wsgi(registry, "math.add", {"a": 1, "b": 2}, prefix=prefix)
        assert status == "200 OK" and json.loads(out) == {"success": True, "data": 3}
    assert headers["cache-control"] == "no-store" and headers["x-content-type-options"] == "nosniff"
    assert headers["content-length"] == str(len(out))
    _, _, out = wsgi(registry, "whoami", {})
    assert json.loads(out)["data"]["cookie"] == "abc"


def test_wsgi_oversized_body_is_refused_without_reading_it():
    registry = make_registry(max_body_bytes=50)
    stream = io.BytesIO(b"x" * 10_000)
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/math.add", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": "10000", "wsgi.input": stream, "HTTP_X_TELOCE_ACTION": "1"}
    seen = {}
    out = b"".join(registry.wsgi_app(environ, lambda status, headers: seen.update(status=status)))
    assert seen["status"].startswith("413") and stream.tell() == 0 and b"payload_too_large" in out


# ---------------------------------------------------------------- ASGI
def run_asgi(registry, scope, chunks):
    sent = []
    queue = list(chunks)

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(registry.asgi_app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), payload


def asgi_scope(path, **extra):
    return {"type": "http", "method": "POST", "path": path, "root_path": "", "headers": [
        (b"content-type", b"application/json"), (b"x-teloce-action", b"1"), (b"cookie", b"sid=abc")], **extra}


def test_asgi_success_chunked_body_and_root_path():
    registry = make_registry()
    raw = body({"a": 20, "b": 22})
    chunks = [{"type": "http.request", "body": raw[:5], "more_body": True}, {"type": "http.request", "body": raw[5:]}]
    status, headers, payload = run_asgi(registry, asgi_scope("/api/v1/math.add", root_path="/api/v1"), chunks)
    assert status == 200 and json.loads(payload)["data"] == 42
    assert headers[b"cache-control"] == b"no-store"
    status, _, payload = run_asgi(registry, asgi_scope("/_teloce/actions/whoami"), [{"type": "http.request", "body": body({})}])
    assert json.loads(payload)["data"]["cookie"] == "abc"


def test_asgi_stops_buffering_oversized_bodies():
    registry = make_registry(max_body_bytes=64)
    chunks = [{"type": "http.request", "body": b"x" * 100, "more_body": True} for _ in range(3)]
    status, _, payload = run_asgi(registry, asgi_scope("/math.add"), chunks)
    assert status == 413 and b"payload_too_large" in payload


def test_asgi_lifespan():
    registry = make_registry()
    sent, queue = [], [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return queue.pop(0)

    async def send(message):
        sent.append(message["type"])

    asyncio.run(registry.asgi_app({"type": "lifespan"}, receive, send))
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_wsgi_never_reads_a_stream_without_content_length():
    """A live socket never reports EOF, so reading without a length would hang the request."""

    class Unreadable:
        def read(self, *args):
            raise AssertionError("the request stream must not be read without a Content-Length")

    registry = ActionRegistry()
    registry.register("echo", lambda data: {"got": data})
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/echo", "wsgi.input": Unreadable(), "HTTP_X_TELOCE_ACTION": "1"}
    seen = {}
    out = b"".join(registry.wsgi_app(environ, lambda status, headers: seen.update(status=status)))
    assert seen["status"].startswith("405") and b"method_not_allowed" in out
    post = dict(environ, REQUEST_METHOD="POST", CONTENT_TYPE="application/json")  # no Content-Length
    out = b"".join(registry.wsgi_app(post, lambda status, headers: seen.update(status=status)))
    assert seen["status"].startswith("200") and json.loads(out) == {"success": True, "data": {"got": None}}

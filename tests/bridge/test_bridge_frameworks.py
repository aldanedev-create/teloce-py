"""The bridge mounts into real frameworks without any adapter package."""
import json

import pytest

from teloce.bridge import ActionRegistry, Bridge, ChannelHub, allow_all

HEADERS = {"content-type": "application/json", "x-teloce-action": "1"}


def make_registry():
    registry = ActionRegistry()
    registry.register("greet", lambda data, ctx: {"hello": data["name"], "sid": ctx.cookies.get("sid")}, public=True)
    return registry


def test_flask_mounts_the_wsgi_app_next_to_its_own_routes():
    flask = pytest.importorskip("flask")
    from werkzeug.middleware.dispatcher import DispatcherMiddleware

    registry = make_registry()
    app = flask.Flask(__name__)

    @app.get("/")
    def index():
        return "flask page"

    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/_teloce/actions": registry.wsgi_app})
    client = app.test_client()
    assert client.get("/").data == b"flask page"
    response = client.post("/_teloce/actions/greet", json={"data": {"name": "Ada"}}, headers={"x-teloce-action": "1"})
    assert response.status_code == 200 and response.get_json() == {"success": True, "data": {"hello": "Ada", "sid": None}}
    assert client.post("/_teloce/actions/greet", json={"data": {}}).get_json()["code"] == "csrf_failed"


def test_fastapi_mounts_actions_and_serves_the_hub_from_a_websocket_route():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI, WebSocket
    from fastapi.testclient import TestClient

    registry = make_registry()
    hub = ChannelHub(authorize=allow_all)
    app = FastAPI()

    @app.get("/")
    def index():
        return {"page": "fastapi"}

    app.mount("/_teloce/actions", registry.asgi_app)

    @app.websocket("/_teloce/socket")  # recommended: keeps the browser URL free of a trailing slash
    async def socket(websocket: WebSocket):
        await hub.asgi_app(websocket.scope, websocket.receive, websocket.send)

    with TestClient(app) as client:
        assert client.get("/").json() == {"page": "fastapi"}
        client.cookies.set("sid", "s1")
        response = client.post("/_teloce/actions/greet", json={"data": {"name": "Grace"}}, headers=HEADERS)
        assert response.json() == {"success": True, "data": {"hello": "Grace", "sid": "s1"}}
        with client.websocket_connect("/_teloce/socket") as a, client.websocket_connect("/_teloce/socket") as b:
            b.send_json({"type": "subscribe", "channel": "room"})
            assert b.receive_json() == {"type": "subscribed", "channel": "room"}
            a.send_json({"type": "publish", "channel": "room", "data": {"x": 1}})
            assert b.receive_json() == {"type": "message", "channel": "room", "data": {"x": 1}}


def test_starlette_mount_needs_a_trailing_slash_for_websockets_and_the_combined_app_works():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    bridge = Bridge(make_registry(), ChannelHub(authorize=allow_all))
    app = FastAPI()
    app.mount("/_teloce", bridge.asgi_app)  # one app for HTTP actions and WebSockets
    with TestClient(app) as client:
        response = client.post("/_teloce/greet", json={"data": {"name": "Linus"}}, headers=HEADERS)
        assert response.json()["data"]["hello"] == "Linus"
        with client.websocket_connect("/_teloce/socket/") as ws:  # Mount only matches a sub-path
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}


def test_any_asgi_framework_can_route_by_path_prefix():
    """The pattern for frameworks that cannot mount apps (e.g. Django's ASGI handler)."""
    import asyncio

    registry = make_registry()
    framework_calls = []

    async def framework_app(scope, receive, send):  # stands in for get_asgi_application()
        framework_calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"framework"})

    async def application(scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/_teloce/actions/"):
            await registry.asgi_app(scope, receive, send)
        else:
            await framework_app(scope, receive, send)

    def request(path, body=b'{"data":{"name":"Z"}}'):
        sent, queue = [], [{"type": "http.request", "body": body}]

        async def receive():
            return queue.pop(0)

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": path, "headers": [
            (b"content-type", b"application/json"), (b"x-teloce-action", b"1")]}
        asyncio.run(application(scope, receive, send))
        return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    assert json.loads(request("/_teloce/actions/greet"))["data"]["hello"] == "Z"
    assert request("/dashboard") == b"framework" and framework_calls == ["/dashboard"]

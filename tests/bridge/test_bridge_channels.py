"""Framework-agnostic WebSocket channels: protocol, authorization and the ASGI app."""
import asyncio
import json

from teloce.bridge import Bridge, ChannelHub, Connection, allow_all


class Client:
    """A fake connected client that records every frame the server sends it."""

    def __init__(self, hub, **kwargs):
        self.frames = []
        self.hub = hub
        self.fail = False

        async def send(text):
            if self.fail:
                raise ConnectionError("gone")
            self.frames.append(json.loads(text))

        self.connection = Connection(send=send, **kwargs)

    async def say(self, **message):
        await self.hub.receive(self.connection, json.dumps(message))

    async def raw(self, text):
        await self.hub.receive(self.connection, text)

    def last(self):
        return self.frames[-1]


def run(coro):
    return asyncio.run(coro)


def test_everything_is_refused_without_an_authorize_hook():
    async def scenario():
        hub = ChannelHub()
        a = Client(hub)
        await a.say(type="subscribe", channel="orders")
        await a.say(type="publish", channel="orders", data=1)
        return a.frames, hub.subscribers("orders")

    frames, subscribers = run(scenario())
    assert [f["code"] for f in frames] == ["forbidden", "forbidden"] and subscribers == 0


def test_subscribe_publish_unsubscribe_flow():
    async def scenario():
        hub = ChannelHub(authorize=allow_all)
        a, b = Client(hub), Client(hub)
        await a.say(type="subscribe", channel="orders")
        await b.say(type="subscribe", channel="orders")
        await a.say(type="publish", channel="orders", data={"n": 1})
        await b.say(type="unsubscribe", channel="orders")
        await a.say(type="publish", channel="orders", data={"n": 2})
        return a.frames, b.frames

    a_frames, b_frames = run(scenario())
    assert a_frames == [{"type": "subscribed", "channel": "orders"}]  # no echo to the publisher
    assert b_frames == [
        {"type": "subscribed", "channel": "orders"},
        {"type": "message", "channel": "orders", "data": {"n": 1}},
        {"type": "unsubscribed", "channel": "orders"},
    ]


def test_echo_option_and_server_side_publish():
    async def scenario():
        hub = ChannelHub(authorize=allow_all, echo=True)
        a = Client(hub)
        await a.say(type="subscribe", channel="c")
        await a.say(type="publish", channel="c", data="hi")
        delivered = await hub.publish("c", {"from": "server"})
        return a.frames, delivered

    frames, delivered = run(scenario())
    assert frames[1] == {"type": "message", "channel": "c", "data": "hi"}
    assert frames[2]["data"] == {"from": "server"} and delivered == 1


def test_authorize_sees_connection_action_and_channel_and_may_be_async():
    calls = []

    async def authorize(connection, action, channel):
        calls.append((connection.user, action, channel))
        return channel.startswith("public:") or connection.user == "admin"

    async def scenario():
        hub = ChannelHub(authorize=authorize)
        guest, admin = Client(hub, user="guest"), Client(hub, user="admin")
        await guest.say(type="subscribe", channel="public:news")
        await guest.say(type="subscribe", channel="private:ops")
        await admin.say(type="subscribe", channel="private:ops")
        await admin.say(type="publish", channel="private:ops", data=1)
        return guest.frames, admin.frames

    guest, admin = run(scenario())
    assert [f.get("code", f["type"]) for f in guest] == ["subscribed", "forbidden"]
    assert admin[0]["type"] == "subscribed"
    assert ("guest", "subscribe", "private:ops") in calls and ("admin", "publish", "private:ops") in calls


def test_ping_and_malformed_input():
    async def scenario():
        hub = ChannelHub(authorize=allow_all, max_message_bytes=200)
        a = Client(hub)
        await a.say(type="ping")
        await a.raw("{nope")
        await a.raw("[1]")
        await a.say(type="teleport", channel="x")
        await a.say(type="subscribe", channel="has space")
        await a.say(type="subscribe", channel="../etc")
        await a.say(type="subscribe")
        await a.raw(json.dumps({"type": "publish", "channel": "x", "data": "y" * 500}))
        return [f.get("code", f["type"]) for f in a.frames]

    assert run(scenario()) == [
        "pong", "invalid_json", "invalid_message", "invalid_message", "invalid_message",
        "invalid_message", "invalid_message", "message_too_large",
    ]


def test_channel_cap_per_connection():
    async def scenario():
        hub = ChannelHub(authorize=allow_all, max_channels_per_connection=2)
        a = Client(hub)
        for name in ("a", "b", "c", "a"):  # re-subscribing to an existing channel is not a new one
            await a.say(type="subscribe", channel=name)
        return [f.get("code", f["type"]) for f in a.frames]

    assert run(scenario()) == ["subscribed", "subscribed", "too_many_channels", "subscribed"]


def test_dead_sockets_are_dropped_and_do_not_block_others():
    async def scenario():
        hub = ChannelHub(authorize=allow_all)
        a, dead, c = Client(hub), Client(hub), Client(hub)
        for client in (a, dead, c):
            await client.say(type="subscribe", channel="x")
        dead.fail = True
        delivered = await hub.publish("x", 1)
        return delivered, hub.subscribers("x"), c.last()

    delivered, subscribers, last = run(scenario())
    assert delivered == 2 and subscribers == 2 and last["data"] == 1


def test_disconnect_cleans_up_subscriptions():
    async def scenario():
        hub = ChannelHub(authorize=allow_all)
        a = Client(hub)
        await a.say(type="subscribe", channel="x")
        await hub.disconnect(a.connection)
        return hub.subscribers("x"), a.connection.channels

    assert run(scenario()) == (0, set())


def test_authorize_exceptions_do_not_kill_the_loop():
    def authorize(connection, action, channel):
        raise RuntimeError("bug")

    async def scenario():
        hub = ChannelHub(authorize=authorize)
        a = Client(hub)
        await a.say(type="subscribe", channel="x")
        await a.say(type="ping")
        return [f.get("code", f["type"]) for f in a.frames]

    assert run(scenario()) == ["internal_error", "pong"]


# ---------------------------------------------------------------- ASGI
def drive(hub, events, *, headers=(), scope_extra=None):
    """Run the ASGI app with scripted client events; returns frames sent by the server."""
    sent = []
    queue = list(events)

    async def receive():
        return queue.pop(0) if queue else {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "path": "/socket", "headers": [(k.encode(), v.encode()) for k, v in headers], **(scope_extra or {})}
    asyncio.run(hub.asgi_app(scope, receive, send))
    return sent


def text(**message):
    return {"type": "websocket.receive", "text": json.dumps(message)}


CONNECT = {"type": "websocket.connect"}


def test_asgi_connect_subscribe_and_cleanup():
    hub = ChannelHub(authorize=allow_all)
    sent = drive(hub, [CONNECT, text(type="subscribe", channel="x"), text(type="ping")])
    assert sent[0] == {"type": "websocket.accept"}
    assert [json.loads(m["text"])["type"] for m in sent[1:]] == ["subscribed", "pong"]
    assert hub.subscribers("x") == 0  # cleaned up when the client disconnected


def test_asgi_two_clients_exchange_messages_through_the_hub():
    async def scenario():
        hub = ChannelHub(authorize=allow_all)
        inbox = []
        gate = asyncio.Event()

        async def listener():
            queue = [CONNECT, text(type="subscribe", channel="chat")]

            async def receive():
                if queue:
                    return queue.pop(0)
                await gate.wait()
                return {"type": "websocket.disconnect"}

            async def send(message):
                inbox.append(message)

            await hub.asgi_app({"type": "websocket", "headers": []}, receive, send)

        task = asyncio.create_task(listener())
        while hub.subscribers("chat") == 0:
            await asyncio.sleep(0)
        await hub.publish("chat", {"hello": "world"})
        gate.set()
        await task
        return [json.loads(m["text"]) for m in inbox if m["type"] == "websocket.send"]

    frames = run(scenario())
    assert frames[-1] == {"type": "message", "channel": "chat", "data": {"hello": "world"}}


def test_asgi_rejects_cross_site_origin_but_allows_same_host_and_listed():
    hub = ChannelHub(authorize=allow_all, allowed_origins=["https://app.example.com"])
    bad = drive(hub, [CONNECT], headers=[("origin", "https://evil.test"), ("host", "api.example.com")])
    assert bad == [{"type": "websocket.close", "code": 4403}]
    for origin in ("https://api.example.com", "https://app.example.com"):
        ok = drive(hub, [CONNECT], headers=[("origin", origin), ("host", "api.example.com")])
        assert ok[0] == {"type": "websocket.accept"}
    assert drive(hub, [CONNECT])[0] == {"type": "websocket.accept"}  # non-browser client


def test_asgi_authenticate_hook_sets_user_or_closes():
    seen = []
    hub = ChannelHub(authorize=lambda c, a, ch: seen.append(c.user) or True,
                     authenticate=lambda scope: "alice" if dict(scope["headers"]).get(b"authorization") == b"ok" else None)
    denied = drive(hub, [CONNECT])
    assert denied == [{"type": "websocket.close", "code": 4401}]
    drive(hub, [CONNECT, text(type="subscribe", channel="x")], headers=[("authorization", "ok")])
    assert seen == ["alice"]


def test_asgi_handles_binary_frames_and_lifespan():
    hub = ChannelHub(authorize=allow_all)
    sent = drive(hub, [CONNECT, {"type": "websocket.receive", "bytes": b'{"type":"ping"}'}])
    assert json.loads(sent[1]["text"]) == {"type": "pong"}
    out, queue = [], [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return queue.pop(0)

    async def send(message):
        out.append(message["type"])

    asyncio.run(hub.asgi_app({"type": "lifespan"}, receive, send))
    assert out == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_bridge_routes_http_to_actions_and_websocket_to_channels():
    bridge = Bridge()
    bridge.actions.register("hi", lambda data: "hello", public=True)
    bridge.channels.authorize = allow_all
    sent = []
    queue = [{"type": "http.request", "body": b'{"data":null}'}]

    async def receive():
        return queue.pop(0)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/_teloce/actions/hi", "headers": [
        (b"content-type", b"application/json"), (b"x-teloce-action", b"1")]}
    asyncio.run(bridge.asgi_app(scope, receive, send))
    assert json.loads(sent[-1]["body"])["data"] == "hello"
    ws = drive(bridge.channels, [CONNECT, text(type="subscribe", channel="x")])
    assert ws[0] == {"type": "websocket.accept"}

"""Framework-agnostic WebSocket channels (publish / subscribe).

The browser's ``SocketClient`` speaks a small JSON protocol over a WebSocket::

    -> {"type": "subscribe",   "channel": "orders"}   <- {"type": "subscribed",   "channel": "orders"}
    -> {"type": "unsubscribe", "channel": "orders"}   <- {"type": "unsubscribed", "channel": "orders"}
    -> {"type": "publish",     "channel": "orders", "data": {...}}
    -> {"type": "ping"}                               <- {"type": "pong"}
                                                      <- {"type": "message", "channel": "orders", "data": {...}}
                                                      <- {"type": "error", "code": "forbidden", "channel": "orders"}

:class:`ChannelHub` implements the server half with no framework dependency. Its
:attr:`~ChannelHub.asgi_app` is a standard ASGI WebSocket application: mount it anywhere an ASGI
framework lets you mount an app, or run it directly under any ASGI server.

Secure by default: with no ``authorize`` hook **every subscribe and publish is refused** (a
channel name is never permission to read its data). Use ``authorize=allow_all`` only for public
demos. Connections from a different ``Origin`` are rejected to stop cross-site WebSocket
hijacking; authenticate users with the ``authenticate`` hook (cookies and headers are on the scope).
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import logging
import re
import uuid
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import urlsplit

from .actions import _lifespan, dumps

__all__ = ["ChannelHub", "Connection", "allow_all", "deny_all"]

log = logging.getLogger("teloce.bridge")

CHANNEL_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")

Authorizer = Callable[["Connection", str, str], "bool | Awaitable[bool]"]


def allow_all(connection: "Connection", action: str, channel: str) -> bool:
    """An ``authorize`` hook that permits everything. For public demos only."""
    return True


def deny_all(connection: "Connection", action: str, channel: str) -> bool:
    return False


@dataclasses.dataclass(eq=False)
class Connection:
    """One connected client. ``user`` holds whatever your ``authenticate`` hook returned."""

    send: Callable[[str], Awaitable[None]]
    scope: Any = None
    user: Any = None
    id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    channels: set[str] = dataclasses.field(default_factory=set)


class ChannelHub:
    """Subscriber registry plus the message protocol.

    Parameters
    ----------
    authorize:
        ``(connection, action, channel) -> bool`` (sync or async) where ``action`` is
        ``"subscribe"`` or ``"publish"``. ``None`` refuses everything.
    authenticate:
        ``(scope) -> user`` run before the connection is accepted; a falsy result closes the
        socket with code 4401.
    allowed_origins:
        Extra accepted ``Origin`` values; same-host origins are always accepted.
    echo:
        Deliver a client's own publishes back to it (default False).
    """

    def __init__(
        self,
        *,
        authorize: Authorizer | None = None,
        authenticate: Callable[[dict[str, Any]], Any] | None = None,
        allowed_origins: Iterable[str] = (),
        echo: bool = False,
        max_message_bytes: int = 65_536,
        max_channels_per_connection: int = 100,
    ):
        self.authorize = authorize
        self.authenticate = authenticate
        self.allowed_origins = frozenset(origin.rstrip("/").lower() for origin in allowed_origins)
        self.echo = echo
        self.max_message_bytes = max_message_bytes
        self.max_channels_per_connection = max_channels_per_connection
        self._subscribers: dict[str, set[Connection]] = {}

    # ---- membership ---------------------------------------------------------------------
    async def disconnect(self, connection: Connection) -> None:
        for channel in list(connection.channels):
            self._remove(connection, channel)

    def _remove(self, connection: Connection, channel: str) -> None:
        connection.channels.discard(channel)
        members = self._subscribers.get(channel)
        if members is not None:
            members.discard(connection)
            if not members:
                del self._subscribers[channel]

    def subscribers(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))

    # ---- publishing ---------------------------------------------------------------------
    async def publish(self, channel: str, data: Any, *, exclude: Connection | None = None) -> int:
        """Send ``data`` to everyone subscribed to ``channel``. Returns the delivery count.

        Call this from your own code (an action, a background task) to push server events.
        """
        if not CHANNEL_NAME_RE.match(channel):
            raise ValueError(f"Invalid channel name {channel!r}")
        text = dumps({"type": "message", "channel": channel, "data": data})
        targets = [c for c in self._subscribers.get(channel, ()) if c is not exclude]
        results = await asyncio.gather(*(c.send(text) for c in targets), return_exceptions=True)
        for connection, result in zip(targets, results):
            if isinstance(result, BaseException):  # a dead socket must not block the others
                await self.disconnect(connection)
        return sum(1 for result in results if not isinstance(result, BaseException))

    # ---- protocol -----------------------------------------------------------------------
    async def _allowed(self, connection: Connection, action: str, channel: str) -> bool:
        if self.authorize is None:
            return False
        allowed = self.authorize(connection, action, channel)
        if inspect.isawaitable(allowed):
            allowed = await allowed
        return bool(allowed)

    async def _reply(self, connection: Connection, **message: Any) -> None:
        await connection.send(dumps(message))

    async def receive(self, connection: Connection, text: str) -> None:
        """Handle one inbound text frame from ``connection``."""
        if len(text.encode("utf-8")) > self.max_message_bytes:
            await self._reply(connection, type="error", code="message_too_large")
            return
        try:
            message = json.loads(text)
        except ValueError:
            await self._reply(connection, type="error", code="invalid_json")
            return
        if not isinstance(message, dict):
            await self._reply(connection, type="error", code="invalid_message")
            return
        kind = message.get("type")
        if kind == "ping":
            await self._reply(connection, type="pong")
            return
        channel = message.get("channel")
        if kind not in ("subscribe", "unsubscribe", "publish") or not isinstance(channel, str) \
                or not CHANNEL_NAME_RE.match(channel):
            await self._reply(connection, type="error", code="invalid_message")
            return
        try:
            if kind == "unsubscribe":
                self._remove(connection, channel)
                await self._reply(connection, type="unsubscribed", channel=channel)
            elif not await self._allowed(connection, kind, channel):
                await self._reply(connection, type="error", code="forbidden", channel=channel)
            elif kind == "subscribe":
                if channel not in connection.channels and len(connection.channels) >= self.max_channels_per_connection:
                    await self._reply(connection, type="error", code="too_many_channels", channel=channel)
                    return
                connection.channels.add(channel)
                self._subscribers.setdefault(channel, set()).add(connection)
                await self._reply(connection, type="subscribed", channel=channel)
            else:  # publish
                await self.publish(channel, message.get("data"), exclude=None if self.echo else connection)
        except Exception:  # noqa: BLE001 - an authorize/handler bug must not kill the socket loop
            log.exception("Teloce channel message failed")
            await self._reply(connection, type="error", code="internal_error", channel=channel)

    # ---- ASGI ---------------------------------------------------------------------------
    def _origin_ok(self, headers: dict[str, str]) -> bool:
        origin = headers.get("origin")
        if not origin:
            return True  # non-browser client
        origin = origin.rstrip("/").lower()
        if origin in self.allowed_origins:
            return True
        host = headers.get("host", "").lower()
        return bool(host) and urlsplit(origin).netloc == host

    @property
    def asgi_app(self) -> Callable[..., Awaitable[None]]:
        """An ASGI WebSocket application (handles lifespan too)."""

        async def app(scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
            if scope["type"] == "lifespan":
                await _lifespan(receive, send)
                return
            if scope["type"] != "websocket":
                raise RuntimeError("ChannelHub.asgi_app only serves WebSocket connections")
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            first = await receive()
            if first["type"] != "websocket.connect":
                return
            user: Any = True
            if not self._origin_ok(headers):
                await send({"type": "websocket.close", "code": 4403})
                return
            if self.authenticate is not None:
                user = self.authenticate(scope)
                if inspect.isawaitable(user):
                    user = await user
                if not user:
                    await send({"type": "websocket.close", "code": 4401})
                    return
            await send({"type": "websocket.accept"})
            connection = Connection(
                send=lambda text: send({"type": "websocket.send", "text": text}),
                scope=scope, user=user if self.authenticate is not None else None,
            )
            try:
                while True:
                    event = await receive()
                    if event["type"] == "websocket.disconnect":
                        break
                    text = event.get("text")
                    if text is None and event.get("bytes") is not None:
                        text = event["bytes"].decode("utf-8", errors="replace")
                    if text is not None:
                        await self.receive(connection, text)
            finally:
                await self.disconnect(connection)

        return app

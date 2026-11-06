"""Framework-agnostic backend for Teloce's browser network clients.

``teloce.http`` needs no backend support. ``teloce.action`` and ``teloce.socket`` talk to the
two pieces in this package, which work with *any* Python web framework because they expose
plain functions plus standard WSGI / ASGI applications:

* :class:`ActionRegistry` — ``@registry.action("todos.create")`` functions called from the browser;
* :class:`ChannelHub` — publish/subscribe channels over WebSockets;
* :class:`Bridge` — one ASGI app serving both.

See ``docs/network-api.md`` for the wire protocol and mounting examples.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .actions import (
    ACTION_HEADER,
    DEFAULT_PREFIX,
    ActionContext,
    ActionError,
    ActionRegistry,
    ActionRequest,
    ActionResponse,
    dumps,
)
from .channels import ChannelHub, Connection, allow_all, deny_all

__all__ = [
    "ACTION_HEADER",
    "ActionContext",
    "ActionError",
    "ActionRegistry",
    "ActionRequest",
    "ActionResponse",
    "Bridge",
    "ChannelHub",
    "Connection",
    "DEFAULT_PREFIX",
    "allow_all",
    "deny_all",
    "dumps",
]


class Bridge:
    """Serve actions (HTTP) and channels (WebSocket) from one ASGI application."""

    def __init__(self, actions: ActionRegistry | None = None, channels: ChannelHub | None = None):
        self.actions = actions if actions is not None else ActionRegistry()
        self.channels = channels if channels is not None else ChannelHub()

    @property
    def asgi_app(self) -> Callable[..., Awaitable[None]]:
        actions_app = self.actions.asgi_app
        channels_app = self.channels.asgi_app

        async def app(scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
            if scope["type"] == "websocket":
                await channels_app(scope, receive, send)
            else:  # http and lifespan
                await actions_app(scope, receive, send)

        return app

    @property
    def wsgi_app(self) -> Callable[..., Any]:
        """WSGI cannot carry WebSockets, so this serves actions only."""
        return self.actions.wsgi_app

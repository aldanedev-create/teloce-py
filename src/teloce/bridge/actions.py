"""Framework-agnostic server actions.

The browser's ``teloce.action.call("todos.create", data)`` posts ``{"data": ...}`` to
``<prefix>/todos.create``. :class:`ActionRegistry` validates that request, runs the registered
Python function and answers ``{"success": true, "data": ...}`` or
``{"success": false, "error": ..., "code": ...}``.

The registry knows nothing about Flask, Django or FastAPI. It exposes:

* :meth:`ActionRegistry.handle` — plain data in, plain data out, for any framework;
* :attr:`ActionRegistry.wsgi_app` / :attr:`ActionRegistry.asgi_app` — standard apps you can
  mount at the prefix in any WSGI or ASGI framework.

Security defaults: POST only, JSON only, a request-size limit, only registered names are
callable, a custom-header plus same-origin check against cross-site requests, no stack traces
in responses. **Authentication and authorization are yours**: pass ``authorize=`` (or ``auth=``
per action); an action name sent by a browser is never treated as permission.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import decimal
import enum
import inspect
import json
import logging
import pathlib
import re
import threading
import uuid
from http.cookies import SimpleCookie
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import urlsplit

__all__ = [
    "ACTION_HEADER",
    "ActionContext",
    "ActionError",
    "ActionRegistry",
    "ActionRequest",
    "ActionResponse",
    "DEFAULT_PREFIX",
    "dumps",
]

log = logging.getLogger("teloce.bridge")

DEFAULT_PREFIX = "/_teloce/actions"
ACTION_HEADER = "x-teloce-action"
ACTION_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")

_STATUS_TEXT = {
    200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large",
    415: "Unsupported Media Type", 422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error",
}


class ActionError(Exception):
    """Raise from an action to return a structured, client-visible failure.

    ``code`` is a short machine-readable string, ``message`` is shown to the client, and
    ``details`` (optional, JSON-serializable) is passed through, e.g. field errors.
    """

    def __init__(self, code: str, message: str | None = None, *, status: int = 400, details: Any = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status
        self.details = details


@dataclasses.dataclass
class ActionRequest:
    """A framework-neutral view of one action call."""

    name: str
    data: Any = None
    method: str = "POST"
    path: str = ""
    headers: Mapping[str, str] = dataclasses.field(default_factory=dict)  # lower-case keys
    cookies: Mapping[str, str] = dataclasses.field(default_factory=dict)
    raw: Any = None  # the framework's own request / WSGI environ / ASGI scope, if you need it
    state: dict[str, Any] = dataclasses.field(default_factory=dict)  # scratch space for hooks


# Handlers may ask for this by naming a parameter ``ctx``, ``context`` or ``request``.
ActionContext = ActionRequest


@dataclasses.dataclass
class ActionResponse:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = dataclasses.field(default_factory=dict)

    def to_bytes(self) -> bytes:
        return dumps(self.body).encode("utf-8")


def _json_default(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID, pathlib.PurePath)):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    for method in ("model_dump", "dict"):  # pydantic v2 / v1 and similar
        convert = getattr(value, method, None)
        if callable(convert):
            return convert()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(value: Any) -> str:
    """JSON-encode with the encoders actions and channels share."""
    return json.dumps(value, default=_json_default, separators=(",", ":"), allow_nan=False)


Authorizer = Callable[[ActionRequest], "bool | Awaitable[bool]"]
CsrfCheck = Callable[[ActionRequest], bool]


@dataclasses.dataclass
class _Spec:
    name: str
    func: Callable[..., Any]
    auth: Authorizer | None
    public: bool
    is_async: bool
    plan: tuple[str, ...]  # per positional parameter: "data" or "ctx"


def _plan(func: Callable[..., Any]) -> tuple[str, ...]:
    plan: list[str] = []
    for index, param in enumerate(inspect.signature(func).parameters.values()):
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD, param.KEYWORD_ONLY):
            continue
        if param.name in ("ctx", "context", "request"):
            plan.append("ctx")
        elif param.name == "data":
            plan.append("data")
        else:  # by position: first is the data, second the context
            plan.append("data" if index == 0 else "ctx")
    return tuple(plan)


class ActionRegistry:
    """Register Python functions as browser-callable actions.

    Parameters
    ----------
    prefix:
        URL prefix the actions are served under (must match the browser's ``actionPath``).
    max_body_bytes:
        Larger request bodies are rejected with 413.
    csrf:
        ``"header"`` (default) requires the ``X-Teloce-Action`` header, which browsers cannot
        add to cross-site requests without a CORS preflight, and rejects a mismatching
        ``Origin``. Pass a callable ``(request) -> bool`` to use your framework's own CSRF
        check, or ``False`` to disable (only for non-browser clients).
    allowed_origins:
        Extra origins (``https://app.example.com``) accepted by the origin check.
    authorize:
        ``(request) -> bool`` (sync or async) run before every non-``public`` action. Return
        False for 403, or raise :class:`ActionError` for another status such as 401.
    """

    def __init__(
        self,
        *,
        prefix: str = DEFAULT_PREFIX,
        max_body_bytes: int = 1_000_000,
        csrf: str | bool | CsrfCheck = "header",
        allowed_origins: Iterable[str] = (),
        authorize: Authorizer | None = None,
    ):
        self.prefix = "/" + prefix.strip("/")
        self.max_body_bytes = max_body_bytes
        self.csrf = csrf
        self.allowed_origins = frozenset(origin.rstrip("/").lower() for origin in allowed_origins)
        self.authorize = authorize
        self._actions: dict[str, _Spec] = {}

    # ---- registration -------------------------------------------------------------------
    def register(
        self, name: str, func: Callable[..., Any], *, auth: Authorizer | None = None, public: bool = False
    ) -> Callable[..., Any]:
        if not ACTION_NAME_RE.match(name):
            raise ValueError(f"Invalid action name {name!r}: use letters, digits and _ . : -")
        if name in self._actions:
            raise ValueError(f"Action {name!r} is already registered")
        self._actions[name] = _Spec(name, func, auth, public, inspect.iscoroutinefunction(func), _plan(func))
        return func

    def action(self, name: Any = None, *, auth: Authorizer | None = None, public: bool = False) -> Any:
        """Decorator: ``@registry.action("todos.create")`` (or bare ``@registry.action``)."""
        if callable(name):  # bare decorator
            return self.register(name.__name__, name, auth=auth, public=public)

        def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
            return self.register(name or func.__name__, func, auth=auth, public=public)

        return decorate

    def names(self) -> list[str]:
        return sorted(self._actions)

    # ---- request handling ---------------------------------------------------------------
    def handle(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes = b"",
        *,
        cookies: Mapping[str, str] | None = None,
        raw: Any = None,
        content_length: int | None = None,
    ) -> ActionResponse:
        """Handle one request synchronously. ``path`` may include the prefix or not.

        ``content_length`` is the declared body size; it lets an oversized body be refused
        without having been read.
        """
        return self._run(self._dispatch(method, path, headers, body, cookies, raw, True, content_length))

    async def handle_async(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes = b"",
        *,
        cookies: Mapping[str, str] | None = None,
        raw: Any = None,
        content_length: int | None = None,
    ) -> ActionResponse:
        """Async variant: sync handlers run in a worker thread so the event loop stays free."""
        return await self._dispatch(method, path, headers, body, cookies, raw, False, content_length)

    @staticmethod
    def _run(coro: Awaitable[ActionResponse]) -> ActionResponse:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)  # type: ignore[arg-type]
        result: list[ActionResponse] = []
        thread = threading.Thread(target=lambda: result.append(asyncio.run(coro)))  # type: ignore[arg-type]
        thread.start()
        thread.join()
        return result[0]

    def _name_from_path(self, path: str) -> str:
        path = path.split("?", 1)[0]
        if path == self.prefix or path.startswith(self.prefix + "/"):
            path = path[len(self.prefix):]
        return path.strip("/")

    def _fail(self, status: int, code: str, message: str, details: Any = None, **headers: str) -> ActionResponse:
        body: dict[str, Any] = {"success": False, "error": message, "code": code}
        if details is not None:
            body["details"] = details
        return ActionResponse(status, body, {k.replace("_", "-"): v for k, v in headers.items()})

    def _origin_ok(self, request: ActionRequest) -> bool:
        origin = request.headers.get("origin")
        if not origin:  # non-browser client, or a same-origin request that sends no Origin
            return True
        origin = origin.rstrip("/").lower()  # an opaque "null" origin never matches below
        if origin in self.allowed_origins:
            return True
        host = request.headers.get("host", "").lower()
        return bool(host) and urlsplit(origin).netloc == host

    def _csrf_ok(self, request: ActionRequest) -> bool:
        if self.csrf is False:
            return True
        if callable(self.csrf):
            return bool(self.csrf(request))
        return bool(request.headers.get(ACTION_HEADER)) and self._origin_ok(request)

    async def _dispatch(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
        cookies: Mapping[str, str] | None,
        raw: Any,
        inline: bool,
        content_length: int | None = None,
    ) -> ActionResponse:
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}
        name = self._name_from_path(path)
        request = ActionRequest(
            name=name, method=method.upper(), path=path, headers=lowered, cookies=dict(cookies or {}), raw=raw
        )
        try:
            if request.method != "POST":
                return self._fail(405, "method_not_allowed", "Use POST", allow="POST")
            if not self._csrf_ok(request):
                return self._fail(403, "csrf_failed", "Cross-site or missing action header")
            spec = self._actions.get(name) if ACTION_NAME_RE.match(name) else None
            if spec is None:
                return self._fail(404, "action_not_found", "Unknown action")
            if "application/json" not in lowered.get("content-type", "").lower():
                return self._fail(415, "unsupported_media_type", "Content-Type must be application/json")
            if max(len(body), content_length or 0) > self.max_body_bytes:
                return self._fail(413, "payload_too_large", "Request body is too large")
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, ValueError):
                return self._fail(400, "invalid_json", "Request body is not valid JSON")
            if not isinstance(payload, dict):
                return self._fail(400, "invalid_body", 'Request body must be an object like {"data": ...}')
            request.data = payload.get("data")
            if not spec.public:
                for check in (self.authorize, spec.auth):
                    if check is None:
                        continue
                    allowed = check(request)
                    if inspect.isawaitable(allowed):
                        allowed = await allowed
                    if not allowed:
                        return self._fail(403, "forbidden", "You are not allowed to do this")
            args = [request.data if kind == "data" else request for kind in spec.plan]
            if spec.is_async:
                result = await spec.func(*args)
            elif inline:
                result = spec.func(*args)
            else:
                result = await asyncio.to_thread(spec.func, *args)
                if inspect.isawaitable(result):
                    result = await result
            return ActionResponse(200, {"success": True, "data": result})
        except ActionError as error:
            return self._fail(error.status, error.code, error.message, error.details)
        except Exception:  # noqa: BLE001 - never leak internals to the browser
            log.exception("Teloce action %r failed", name)
            return self._fail(500, "internal_error", "Internal server error")

    def _finish(self, response: ActionResponse) -> tuple[int, list[tuple[str, str]], bytes]:
        try:
            payload = response.to_bytes()
        except (TypeError, ValueError):
            log.exception("Teloce action result is not JSON serializable")
            response = self._fail(500, "internal_error", "Internal server error")
            payload = response.to_bytes()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            **response.headers,
        }
        return response.status, list(headers.items()), payload

    # ---- WSGI ----------------------------------------------------------------------------
    @property
    def wsgi_app(self) -> Callable[..., Any]:
        """A WSGI application. Mount it at the prefix, or at ``/`` if the prefix is in the URL."""

        def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
            headers = {
                key[5:].replace("_", "-").lower(): value
                for key, value in environ.items()
                if key.startswith("HTTP_")
            }
            if environ.get("CONTENT_TYPE"):
                headers["content-type"] = environ["CONTENT_TYPE"]
            try:
                declared = int(environ["CONTENT_LENGTH"]) if environ.get("CONTENT_LENGTH") else None
            except ValueError:
                declared = None
            if not declared or declared < 0 or declared > self.max_body_bytes:
                # PEP 3333: without a Content-Length there is no body, and reading would block
                # on a live socket. An oversized declared body is refused as 413 unread.
                body = b""
            else:
                body = environ["wsgi.input"].read(declared)
            cookies = _parse_cookies(headers.get("cookie", ""))
            response = self.handle(
                environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", ""), headers, body,
                cookies=cookies, raw=environ, content_length=declared,
            )
            status, header_list, payload = self._finish(response)
            start_response(f"{status} {_STATUS_TEXT.get(status, 'Error')}", header_list + [("content-length", str(len(payload)))])
            return [payload]

        return app

    # ---- ASGI ----------------------------------------------------------------------------
    @property
    def asgi_app(self) -> Callable[..., Awaitable[None]]:
        """An ASGI application for HTTP requests (handles lifespan too)."""

        async def app(scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
            if scope["type"] == "lifespan":
                await _lifespan(receive, send)
                return
            if scope["type"] != "http":
                raise RuntimeError("ActionRegistry.asgi_app only serves HTTP requests")
            headers: dict[str, str] = {}
            for key, value in scope.get("headers", []):
                k = key.decode("latin-1").lower()
                v = value.decode("latin-1")
                headers[k] = f"{headers[k]}, {v}" if k in headers else v
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body += message.get("body", b"")
                if len(body) > self.max_body_bytes:
                    break  # stop buffering: the dispatcher answers 413
                if not message.get("more_body"):
                    break
            path = scope.get("path", "")
            root = scope.get("root_path", "")
            if root and path.startswith(root):
                path = path[len(root):]
            response = await self.handle_async(
                scope.get("method", "GET"), path, headers, bytes(body),
                cookies=_parse_cookies(headers.get("cookie", "")), raw=scope,
                content_length=int(headers["content-length"]) if headers.get("content-length", "").isdigit() else None,
            )
            status, header_list, payload = self._finish(response)
            await send({
                "type": "http.response.start", "status": status,
                "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in header_list]
                + [(b"content-length", str(len(payload)).encode())],
            })
            await send({"type": "http.response.body", "body": payload})

        return app


def _parse_cookies(header: str) -> dict[str, str]:
    if not header:
        return {}
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(header)
    except Exception:  # noqa: BLE001 - malformed cookie headers are ignored
        return {}
    return {key: morsel.value for key, morsel in jar.items()}


async def _lifespan(receive: Callable[..., Any], send: Callable[..., Any]) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return

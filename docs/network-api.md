# Network API: `http`, `action` and `socket`

Teloce ships three small browser clients and a framework-agnostic Python backend for them. No
framework adapter is required: the backend is plain functions plus standard **WSGI** and
**ASGI** apps that you mount in whatever framework you already use.

| Browser (`runtime/network.js`) | Talks to | Python (`teloce.bridge`) |
| --- | --- | --- |
| `http` — fetch client | any HTTP API | nothing needed |
| `action` — named server calls | `POST /_teloce/actions/<name>` | `ActionRegistry` |
| `socket` — WebSocket channels | a WebSocket endpoint | `ChannelHub` |

`poll` and `live` remain element directives. These clients are for calls you make from component code.

## Loading the clients

`network.js` is a plain ES module in `teloce/runtime/` (it imports `signals.js` from the same folder).

```js
import { http, action, createSocket, createScope } from "./runtime/network.js";
```

For standalone pages, load the runtime first, then register the plugin. The plugin adds
`teloce.http`, `teloce.action` and `teloce.socket`:

```html
<script src="teloce.js"></script>
<script type="module">
  import { networkPlugin } from "./runtime/network.js";
  teloce.use(networkPlugin);
</script>
```

Generated components can import them from the shared `teloce-runtime.js` barrel, which re-exports
`http`, `action`, `createHttp`, `createActionClient`, `createSocket`, `createScope`, `networkPlugin`,
`NetworkError`, `HttpClient`, `ActionClient` and `SocketClient` (the build emits `network.js` next to
`signals.js`).

## `http`

```js
const res = await http.get("/api/todos", { params: { status: "open", tags: ["a", "b"] } });
if (!res.ok) return console.error(res.status, res.data);

await http.post("/api/todos", { title: "Write docs" });
```

* Methods: `get head options delete post put patch`, plus `request(config)`.
* Responses are `{ data, status, statusText, headers, config, ok }`. **A non-2xx status resolves** (check
  `res.ok`). Only transport failures throw a `NetworkError` with `code` `"timeout"`, `"aborted"` or `"network"`.
* JSON is encoded for plain objects and arrays. `FormData`, `Blob`, `URLSearchParams`, strings and
  buffers are sent as-is. `GET`/`HEAD` never send a body.
* Defaults: `credentials: "same-origin"`, `timeout: 10000` (0 disables), `retry: 0`.

```js
http.setConfig({
  baseURL: "https://api.example.com",
  headers: { Authorization: "Bearer example-token" },
  timeout: 10_000,
  retry: { retries: 2, delay: 300 },   // GET/HEAD/OPTIONS/PUT/DELETE only; 408 425 429 5xx and network errors
  csrf: { enabled: true, cookieName: "csrftoken", headerName: "X-CSRFToken" },
});
```

**Retries** never replay `POST`/`PATCH` unless you list them in `retry.methods`.
**CSRF** tokens are attached to unsafe methods only, and only when the target is the page's origin
(or your `baseURL`), never to a third-party URL.

**Interceptors** (each returns an unsubscribe function):

```js
http.useRequestInterceptor(config => ({ ...config, headers: { ...config.headers, "X-Client": "web" } }));
http.useResponseInterceptor(res => res);
http.useErrorInterceptor(err => err);   // transport errors only; return an Error to replace it, or a response to recover
```

Create isolated clients with `createHttp(config)`.

## `action`

Call named server functions without designing a URL for each:

```js
const result = await action.call("todos.create", { title: "Write docs" });
if (result.success) console.log(result.data);
else console.error(result.status, result.code, result.error, result.details);
```

The client posts `{"data": ...}` to `/_teloce/actions/todos.create` with the header
`X-Teloce-Action: 1`. HTTP and application failures **resolve** as
`{ success: false, status, error, code, details }`. Timeouts, offline and aborts **throw** `NetworkError`.

```js
action.setConfig({ baseURL: "https://api.example.com", actionPath: "/actions", timeout: 15_000 });
```

Actions use `credentials: "same-origin"` by default. Set `credentials: "include"` only for a
cross-origin backend whose CORS and cookie policy you control.

**Caching** is opt-in per call or via config, and only successful results are cached:

```js
const stats = await action.call("dashboard.stats", {}, { cache: { ttl: 30_000 } });
action.invalidate("dashboard.stats");        // every cached call of this action
action.invalidate("dashboard.*");            // by prefix
action.invalidate("dashboard.stats", {});    // one exact call
action.invalidate();                         // everything
```

Concurrent identical cached calls share one request. Mutating actions should not be cached; invalidate
dependent reads after they succeed.

**Retries** are off for actions. `retry` is honored only when you mark a call `idempotent: true`, because
an automatic replay could repeat a payment or a creation:

```js
await action.call("report.generate", {}, { idempotent: true, retry: 2 });
```

**Reactive resources** give you signals for template state:

```js
const todos = action.resource("todos.list", () => ({ status: filter() }));
todos.data();     // last successful data
todos.loading();  // true while a request is running
todos.error();    // null, or the failed result / NetworkError
todos.refresh();  // reload (a stale response never overwrites a newer one)
todos.dispose();  // abort and stop
```

Pass `{ immediate: false }` to load later with `refresh()`.

## `socket`

```js
const socket = createSocket({
  url: "wss://api.example.com/socket",
  reconnect: { maxAttempts: 5, delay: 1000 },
  heartbeat: { enabled: true, interval: 25_000, timeout: 10_000 },
});
socket.on("message", event => console.log(event.data));
await socket.connect();

const unsubscribe = socket.subscribe("orders", data => console.log("order", data));
socket.publish("orders", { type: "refresh" });
unsubscribe();
```

* `send(message)`: objects are JSON-encoded, strings sent as-is. Messages sent before the connection
  opens are **queued** (default 100, then `NetworkError` code `queue_full`) and flushed in order.
* Reconnects use exponential backoff with jitter. Subscriptions are re-sent automatically.
* Events: `open`, `message`, `close`, `error`, `reconnecting`, `reconnect_failed`.
* **Heartbeat** (off by default): sends `{"type":"ping"}` every `interval` and closes the socket if
  nothing at all arrives within `timeout`, which triggers a reconnect.
* `http:`/`https:` URLs are converted to `ws:`/`wss:`; other schemes are rejected.
* `close()` stops for good (no reconnect, queue cleared).

## Cleanup with `createScope`

Tie requests and subscriptions to a component's lifetime and call `dispose()` when it unmounts:

```js
const scope = createScope();
scope.get("/api/todos");                       // aborted on dispose
scope.call("todos.list", {});                  // aborted on dispose
scope.track(socket.subscribe("orders", fn));   // unsubscribed on dispose
// unmounted: scope.dispose()
```

---

## Backend: `teloce.bridge`

No dependencies and no framework imports.

```python
from teloce.bridge import ActionRegistry, ActionError, ChannelHub, Bridge

actions = ActionRegistry(authorize=lambda request: request.cookies.get("sid") == "ok")

@actions.action("todos.create")
def create_todo(data, ctx):
    if not data or not data.get("title"):
        raise ActionError("validation_error", "Title is required", status=422, details={"title": ["required"]})
    return {"id": 1, "title": data["title"]}

@actions.action("site.ping", public=True)   # skips `authorize`
async def ping(data):
    return "pong"
```

Handlers may take `()`, `(data)` or `(data, ctx)`; name the context parameter `ctx`, `context` or `request`.
Sync and async handlers both work. `ctx` exposes `name`, `data`, `headers` (lower-case keys), `cookies`,
`method` and `raw` (your framework's request, WSGI environ or ASGI scope).

### Wire protocol

| Request | Response |
| --- | --- |
| `POST <prefix>/<name>`, `Content-Type: application/json`, `X-Teloce-Action: 1`, body `{"data": ...}` | `200 {"success": true, "data": ...}` |
| failure | `{"success": false, "error": "...", "code": "...", "details": ...}` |

Status codes: `400 invalid_json|invalid_body`, `403 csrf_failed|forbidden`, `404 action_not_found`,
`405 method_not_allowed`, `413 payload_too_large`, `415 unsupported_media_type`, `500 internal_error`
(always generic; the real error is logged on the `teloce.bridge` logger), plus any status you raise
with `ActionError`. Results may contain dataclasses, datetimes, `Decimal`, `UUID`, paths, sets, enums, and objects with a
`model_dump()` or `dict()` method (such as pydantic models).

### Mounting actions: any framework

**Any WSGI framework (verified with Flask):**

```python
from werkzeug.middleware.dispatcher import DispatcherMiddleware

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/_teloce/actions": actions.wsgi_app})
```

**Any ASGI framework (verified with FastAPI):**

```python
app.mount("/_teloce/actions", actions.asgi_app)
```

**A framework that cannot mount apps (for example Django's ASGI handler):** route by path prefix:

```python
async def application(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/_teloce/actions/"):
        await actions.asgi_app(scope, receive, send)
    else:
        await django_asgi_app(scope, receive, send)
```

**Anything else:** call `actions.handle(method, path, headers, body_bytes, cookies=..., raw=...)`
(or `await actions.handle_async(...)`) and send back `response.status`, `response.to_bytes()` and
`response.headers`.

### Channels (WebSockets)

```python
hub = ChannelHub(
    authenticate=lambda scope: user_from_cookie(scope),            # falsy -> socket closed with 4401
    authorize=lambda conn, action, channel: channel == f"user:{conn.user.id}",  # "subscribe" | "publish"
)

await hub.publish("orders", {"type": "refresh"})    # push from your own code (an action, a task)
```

```python
# FastAPI: a websocket route keeps the browser URL clean
@app.websocket("/_teloce/socket")
async def socket(websocket: WebSocket):
    await hub.asgi_app(websocket.scope, websocket.receive, websocket.send)
```

Starlette's `Mount` matches WebSockets only with a sub-path, so `app.mount("/_teloce/socket", hub.asgi_app)`
needs the browser to connect to `/_teloce/socket/` (trailing slash). `Bridge(actions, hub).asgi_app` is a
single ASGI app that serves both HTTP actions and WebSockets.

Protocol (JSON text frames):

```
→ {"type":"subscribe","channel":"orders"}      ← {"type":"subscribed","channel":"orders"}
→ {"type":"unsubscribe","channel":"orders"}    ← {"type":"unsubscribed","channel":"orders"}
→ {"type":"publish","channel":"orders","data":{}}
→ {"type":"ping"}                              ← {"type":"pong"}
                                               ← {"type":"message","channel":"orders","data":{}}
                                               ← {"type":"error","code":"forbidden","channel":"orders"}
```

## Security checklist

* **Authorization is yours.** The registry only runs *registered* names, but it does not know who may call
  them. Set `authorize=` (and per-action `auth=`), and mark genuinely public actions `public=True`.
* **Channels are deny-by-default.** Without an `authorize` hook every subscribe and publish is refused.
  `allow_all` exists for demos only. A channel name never grants access to its data.
* **CSRF/origin.** The default check requires the `X-Teloce-Action` header (a browser can't add it to a
  cross-site request without a CORS preflight) and rejects a mismatching `Origin`. Behind a proxy that
  rewrites `Host`, list your public origin in `allowed_origins=[...]`. To use your framework's CSRF
  instead, pass `csrf=callable`.
* **WebSockets** reject a foreign `Origin` (cross-site WebSocket hijacking) and authenticate through the
  `authenticate` hook, which can read cookies and headers from the scope.
* **Limits:** `max_body_bytes` (default 1 MB) for actions; `max_message_bytes` (64 KB) and
  `max_channels_per_connection` (100) for sockets.
* **Never trust client data.** Validate every payload in your handler.

## Differences from other action clients

* Cookies are sent **same-origin by default** (not `include`).
* Action retries are **opt-in per call** (`idempotent: true`) instead of a blanket setting.
* The socket heartbeat actually sends the ping and enforces the timeout.

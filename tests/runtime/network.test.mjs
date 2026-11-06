// Unit tests for src/teloce/runtime/network.js (run with: node --test tests/runtime)
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  HttpClient, ActionClient, SocketClient, NetworkError, createScope, networkPlugin,
} from '../../src/teloce/runtime/network.js';

const json = (body, init = {}) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' }, ...init });
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

/** A fetch double that records calls and answers from a queue (or a function). */
function fakeFetch(...answers) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, ...init });
    const next = answers.length > 1 ? answers.shift() : answers[0];
    const value = typeof next === 'function' ? await next(url, init) : next;
    if (value instanceof Error) throw value;
    return value.clone ? value.clone() : value;
  };
  fn.calls = calls;
  return fn;
}

// ------------------------------------------------------------------ HTTP
test('http: params, baseURL join, json body and content-type', async () => {
  const f = fakeFetch(json({ ok: 1 }));
  const client = new HttpClient({ baseURL: 'https://api.test/v1/', fetch: f });
  const res = await client.post('/todos', { title: 'a' }, { params: { page: 2, tags: ['x', 'y'], skip: undefined, none: null } });
  assert.equal(f.calls[0].url, 'https://api.test/v1/todos?page=2&tags=x&tags=y');
  assert.equal(f.calls[0].body, '{"title":"a"}');
  assert.equal(f.calls[0].headers['content-type'], 'application/json');
  assert.deepEqual([res.ok, res.status, res.data], [true, 200, { ok: 1 }]);
});

test('http: non-2xx resolves, 204 is null, text is text, headers lower-cased', async () => {
  const f = fakeFetch(
    json({ detail: 'nope' }, { status: 404 }),
    new Response(null, { status: 204 }),
    new Response('plain', { status: 200, headers: { 'Content-Type': 'text/plain', 'X-Thing': 'v' } }),
  );
  const client = new HttpClient({ fetch: f });
  const missing = await client.get('/a');
  assert.deepEqual([missing.ok, missing.status, missing.data], [false, 404, { detail: 'nope' }]);
  assert.equal((await client.delete('/a')).data, null);
  const text = await client.get('/a');
  assert.equal(text.data, 'plain');
  assert.equal(text.headers['x-thing'], 'v');
});

test('http: raw bodies are not JSON-encoded, GET never sends a body', async () => {
  const f = fakeFetch(json({}));
  const client = new HttpClient({ fetch: f });
  const form = new URLSearchParams({ a: '1' });
  await client.post('/x', form);
  assert.equal(f.calls[0].body, form);
  assert.equal(f.calls[0].headers['content-type'], undefined);
  await client.request({ url: '/x', method: 'GET', data: { ignored: true } });
  assert.equal(f.calls[1].body, undefined);
});

test('http: timeout and abort are NetworkErrors', async () => {
  const hang = (url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(Object.assign(new Error('x'), { name: 'AbortError' }))));
  const client = new HttpClient({ fetch: fakeFetch(hang) });
  await assert.rejects(client.get('/slow', { timeout: 20 }), e => e instanceof NetworkError && e.code === 'timeout');
  const controller = new AbortController();
  const pending = client.get('/slow', { timeout: 0, signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, e => e.code === 'aborted');
  await assert.rejects(client.get('/slow', { signal: AbortSignal.abort() }), e => e.code === 'aborted');
  await assert.rejects(new HttpClient({ fetch: fakeFetch(new Error('offline')) }).get('/x'), e => e.code === 'network');
});

test('http: retries only safe methods, only retryable failures', async () => {
  const f = fakeFetch(json({}, { status: 503 }), json({}, { status: 503 }), json({ done: true }));
  const client = new HttpClient({ fetch: f, retry: { retries: 2, delay: 1 } });
  assert.deepEqual((await client.get('/x')).data, { done: true });
  assert.equal(f.calls.length, 3);

  const post = fakeFetch(json({}, { status: 503 }));
  const res = await new HttpClient({ fetch: post, retry: { retries: 3, delay: 1 } }).post('/x', {});
  assert.deepEqual([res.status, post.calls.length], [503, 1]); // POST is not retried by default

  const flaky = fakeFetch(new Error('down'), json({ ok: 1 }));
  assert.equal((await new HttpClient({ fetch: flaky, retry: { retries: 1, delay: 1 } }).get('/x')).data.ok, 1);

  const notFound = fakeFetch(json({}, { status: 404 }));
  await new HttpClient({ fetch: notFound, retry: { retries: 3, delay: 1 } }).get('/x');
  assert.equal(notFound.calls.length, 1);
});

test('http: request/response/error interceptors', async () => {
  const f = fakeFetch(json({ n: 1 }));
  const client = new HttpClient({ fetch: f });
  const off = client.useRequestInterceptor(async c => ({ ...c, headers: { ...c.headers, 'X-Client': 'web' } }));
  client.useResponseInterceptor(r => ({ ...r, data: { ...r.data, seen: true } }));
  const res = await client.get('/x');
  assert.equal(f.calls[0].headers['x-client'], 'web');
  assert.deepEqual(res.data, { n: 1, seen: true });
  off();
  await client.get('/x');
  assert.equal(f.calls[1].headers['x-client'], undefined);

  const bad = new HttpClient({ fetch: fakeFetch(new Error('offline')) });
  const seen = [];
  bad.useErrorInterceptor(e => { seen.push(e.code); return new NetworkError('wrapped', 'network'); });
  await assert.rejects(bad.get('/x'), e => e.message === 'wrapped');
  assert.deepEqual(seen, ['network']);

  const recover = new HttpClient({ fetch: fakeFetch(new Error('offline')) });
  recover.useErrorInterceptor(() => ({ status: 200, ok: true, data: 'cached', headers: {}, statusText: '', config: {} }));
  assert.equal((await recover.get('/x')).data, 'cached');

  const http = fakeFetch(json({}, { status: 500 }));
  const errors = [];
  const plain = new HttpClient({ fetch: http });
  plain.useErrorInterceptor(e => errors.push(e));
  await plain.get('/x'); // an HTTP error status is NOT a thrown transport error
  assert.equal(errors.length, 0);
});

test('http: CSRF token from option or cookie, unsafe methods and trusted targets only', async () => {
  globalThis.document = { cookie: 'a=1; csrftoken=tok%2B1; b=2' };
  try {
    const f = fakeFetch(json({}));
    const client = new HttpClient({ fetch: f, baseURL: 'https://api.test', csrf: { enabled: true } });
    await client.post('/x', {});
    await client.get('/x');
    await client.post('https://evil.test/steal', {});
    await client.post('/x', {}, { csrf: { headerName: 'X-Other', token: () => 'explicit' } });
    assert.equal(f.calls[0].headers['x-csrftoken'], 'tok+1');
    assert.equal(f.calls[1].headers['x-csrftoken'], undefined);       // safe method
    assert.equal(f.calls[2].headers['x-csrftoken'], undefined);       // foreign origin never gets the token
    assert.equal(f.calls[3].headers['x-other'], 'explicit');
  } finally { delete globalThis.document; }
});

// ------------------------------------------------------------------ actions
test('action: request shape and success normalization', async () => {
  const f = fakeFetch(json({ success: true, data: { id: 1 } }), json({ plain: 'value' }));
  const client = new ActionClient({ fetch: f });
  const result = await client.call('todos.create', { title: 'a' });
  assert.deepEqual(result, { success: true, status: 200, data: { id: 1 } });
  assert.equal(f.calls[0].url, '/_teloce/actions/todos.create');
  assert.equal(f.calls[0].method, 'POST');
  assert.equal(f.calls[0].body, '{"data":{"title":"a"}}');
  assert.equal(f.calls[0].headers['x-teloce-action'], '1');
  assert.equal(f.calls[0].credentials, 'same-origin');
  assert.deepEqual((await client.call('raw')).data, { plain: 'value' }); // raw JSON value is also data
});

test('action: failures resolve with status, code and details; transport failures throw', async () => {
  const f = fakeFetch(
    json({ success: false, error: 'Sold out', code: 'out_of_stock', details: { sku: 1 } }, { status: 409 }),
    json({ detail: 'x' }, { status: 502, statusText: 'Bad Gateway' }),
    new Error('offline'),
  );
  const client = new ActionClient({ fetch: f });
  assert.deepEqual(await client.call('a'), { success: false, status: 409, error: 'Sold out', code: 'out_of_stock', details: { sku: 1 } });
  const second = await client.call('a');
  assert.deepEqual([second.success, second.status, second.error], [false, 502, 'Bad Gateway']);
  await assert.rejects(client.call('a'), e => e instanceof NetworkError && e.code === 'network');
});

test('action: names are validated and URL-safe', async () => {
  const client = new ActionClient({ fetch: fakeFetch(json({})) });
  for (const bad of ['', '../x', 'a/b', 'has space', 'x'.repeat(200), null, 5]) await assert.rejects(client.call(bad), TypeError);
  await client.call('ns:thing-1.sub');
});

test('action: setConfig changes baseURL/actionPath and keeps the action header', async () => {
  const f = fakeFetch(json({}));
  const client = new ActionClient({ fetch: f });
  client.setConfig({ baseURL: 'https://api.test', actionPath: '/actions', headers: { Authorization: 'Bearer t' } });
  await client.call('x');
  assert.equal(f.calls[0].url, 'https://api.test/actions/x');
  assert.equal(f.calls[0].headers['x-teloce-action'], '1');
  assert.equal(f.calls[0].headers.authorization, 'Bearer t');
});

test('action: cache ttl, in-flight dedupe, only successes cached, invalidate variants', async () => {
  let n = 0;
  const f = fakeFetch(async () => json({ success: true, data: ++n }));
  const client = new ActionClient({ fetch: f });
  const opts = { cache: { ttl: 1000 } };
  const [a, b] = await Promise.all([client.call('dash.stats', { r: 1 }, opts), client.call('dash.stats', { r: 1 }, opts)]);
  assert.equal(a.data, 1); assert.equal(b.data, 1); assert.equal(f.calls.length, 1);   // deduped
  assert.equal((await client.call('dash.stats', { r: 1 }, opts)).data, 1);               // cache hit
  assert.equal((await client.call('dash.stats', { r: 2 }, opts)).data, 2);               // different args
  assert.equal(f.calls.length, 2);
  client.invalidate('dash.stats', { r: 1 });                                              // exact
  assert.equal((await client.call('dash.stats', { r: 1 }, opts)).data, 3);
  client.invalidate('dash.stats');                                                        // whole action
  assert.equal(f.calls.length, 3);
  await client.call('dash.stats', { r: 2 }, opts);
  assert.equal(f.calls.length, 4);
  await client.call('dash.other', null, opts);
  client.invalidate('dash.*');                                                            // prefix
  await client.call('dash.other', null, opts);
  assert.equal(f.calls.length, 6);
  client.invalidate();
  const failing = fakeFetch(json({ success: false, error: 'no' }, { status: 400 }), json({ success: true, data: 1 }));
  const c2 = new ActionClient({ fetch: failing });
  await c2.call('x', null, opts); await c2.call('x', null, opts);
  assert.equal(failing.calls.length, 2);                                                  // failures are not cached
});

test('action: cache is off by default and can be enabled by config', async () => {
  const f = fakeFetch(async () => json({ success: true, data: 1 }));
  const client = new ActionClient({ fetch: f });
  await client.call('x'); await client.call('x');
  assert.equal(f.calls.length, 2);
  client.setConfig({ cache: true });
  await client.call('y'); await client.call('y');
  assert.equal(f.calls.length, 3);
});

test('action: retries require idempotent: true', async () => {
  const f = fakeFetch(new Error('down'), json({ success: true, data: 'ok' }));
  const client = new ActionClient({ fetch: f, retry: 1 });
  await assert.rejects(client.call('charge', {}), NetworkError);          // a payment-like POST is never replayed
  assert.equal(f.calls.length, 1);
  const g = fakeFetch(new Error('down'), json({ success: true, data: 'ok' }));
  const safe = await new ActionClient({ fetch: g, retry: 1 }).call('read', {}, { idempotent: true });
  assert.equal(safe.data, 'ok'); assert.equal(g.calls.length, 2);
});

test('action: resource exposes reactive data/loading/error', async () => {
  let count = 0;
  const f = fakeFetch(async () => json({ success: true, data: { list: ++count } }));
  const client = new ActionClient({ fetch: f });
  let source = { q: 'a' };
  const res = client.resource('todos.list', () => source);
  assert.equal(res.loading(), true);
  await wait(15);
  assert.deepEqual([res.data(), res.loading(), res.error()], [{ list: 1 }, false, null]);
  source = { q: 'b' };
  await res.refresh();
  assert.equal(JSON.parse(f.calls[1].body).data.q, 'b');
  assert.deepEqual(res.data(), { list: 2 });

  const failing = new ActionClient({ fetch: fakeFetch(json({ success: false, error: 'bad', code: 'c' }, { status: 400 })) });
  const r2 = failing.resource('x');
  await wait(15);
  assert.equal(r2.error().code, 'c');
  const lazy = client.resource('lazy', null, { immediate: false });
  await wait(5);
  assert.equal(lazy.loading(), false);
  res.dispose();
});

test('action: resource ignores a stale response when a newer load started', async () => {
  const gates = [];
  const f = fakeFetch(() => new Promise(resolve => gates.push(resolve)));
  const res = new ActionClient({ fetch: f }).resource('slow', null, { immediate: false });
  const first = res.refresh();
  const second = res.refresh();
  await wait(5);
  gates[1](json({ success: true, data: 'new' }));
  await wait(5);
  gates[0]?.(json({ success: true, data: 'old' }));
  await Promise.allSettled([first, second]);
  assert.equal(res.data(), 'new');
});

// ------------------------------------------------------------------ sockets
class FakeWS extends EventTarget {
  static instances = [];
  constructor(url, protocols) { super(); this.url = url; this.protocols = protocols; this.readyState = 0; this.sent = []; FakeWS.instances.push(this); }
  send(text) { if (this.readyState !== 1) throw new Error('not open'); this.sent.push(text); }
  close(code = 1000, reason = '') { if (this.readyState === 3) return; this.readyState = 3; this.dispatchEvent(Object.assign(new Event('close'), { code, reason, wasClean: code === 1000 })); }
  open() { this.readyState = 1; this.dispatchEvent(new Event('open')); }
  say(data) { this.dispatchEvent(Object.assign(new Event('message'), { data: typeof data === 'string' ? data : JSON.stringify(data) })); }
  fail() { this.readyState = 3; this.dispatchEvent(Object.assign(new Event('close'), { code: 1006, reason: '', wasClean: false })); }
  get frames() { return this.sent.map(text => { try { return JSON.parse(text); } catch { return text; } }); }
}
const socket = (options = {}) => { FakeWS.instances.length = 0; return new SocketClient({ url: 'wss://api.test/events', WebSocket: FakeWS, ...options, reconnect: { delay: 5, jitter: 0, ...options.reconnect } }); };
const last = () => FakeWS.instances.at(-1);

test('socket: queues before open, flushes in order, JSON-encodes objects only', async () => {
  const s = socket();
  assert.equal(s.send({ type: 'ping' }), false);
  s.send('raw text');
  const connected = s.connect();
  last().open();
  await connected;
  assert.deepEqual(last().frames, [{ type: 'ping' }, 'raw text']);
  assert.equal(s.send({ a: 1 }), true);
  assert.equal(last().sent.at(-1), '{"a":1}');
});

test('socket: queue has a limit; invalid urls rejected; http becomes ws', () => {
  const s = socket({ queue: { maxSize: 2 } });
  s.send(1); s.send(2);
  assert.throws(() => s.send(3), e => e.code === 'queue_full');
  assert.throws(() => new SocketClient({ url: 'ftp://x/y' }), TypeError);
  assert.equal(new SocketClient({ url: 'https://api.test/e', WebSocket: FakeWS }).url, 'wss://api.test/e');
  assert.equal(new SocketClient({ url: 'http://api.test/e', WebSocket: FakeWS }).url, 'ws://api.test/e');
});

test('socket: message events and channel routing; pongs are filtered', async () => {
  const s = socket();
  const events = [], orders = [];
  s.on('message', e => events.push(e.data));
  const p = s.connect(); last().open(); await p;
  const off = s.subscribe('orders', (data, msg) => orders.push([data, msg.channel]));
  assert.deepEqual(last().frames.at(-1), { type: 'subscribe', channel: 'orders' });
  last().say({ type: 'message', channel: 'orders', data: { id: 7 } });
  last().say({ type: 'message', channel: 'other', data: 1 });
  last().say({ type: 'pong' });
  last().say('not json');
  assert.deepEqual(orders, [[{ id: 7 }, 'orders']]);
  assert.equal(events.length, 3);                      // two messages + text frame, no pong
  assert.equal(events.at(-1), 'not json');
  s.publish('orders', { type: 'refresh' });
  assert.deepEqual(last().frames.at(-1), { type: 'publish', channel: 'orders', data: { type: 'refresh' } });
  off();
  assert.deepEqual(last().frames.at(-1), { type: 'unsubscribe', channel: 'orders' });
  assert.throws(() => s.subscribe('bad name', () => {}), TypeError);
});

test('socket: unsubscribe is sent only when the last handler leaves; a throwing handler is isolated', async () => {
  const s = socket();
  const p = s.connect(); last().open(); await p;
  const seen = [];
  const quiet = console.error; console.error = () => {};
  try {
    const a = s.subscribe('c', () => { throw new Error('boom'); });
    const b = s.subscribe('c', d => seen.push(d));
    assert.equal(last().frames.filter(f => f.type === 'subscribe').length, 1);
    last().say({ type: 'message', channel: 'c', data: 1 });
    assert.deepEqual(seen, [1]);
    a();
    assert.equal(last().frames.some(f => f.type === 'unsubscribe'), false);
    b();
    assert.equal(last().frames.at(-1).type, 'unsubscribe');
  } finally { console.error = quiet; }
});

test('socket: reconnects with backoff, resubscribes, resets attempts after success', async () => {
  const s = socket({ reconnect: { maxAttempts: 3, delay: 5, factor: 2 } });
  const seen = [];
  s.on('reconnecting', e => seen.push([e.attempt, e.delay]));
  const p = s.connect(); const first = last(); first.open(); await p;
  s.subscribe('news', () => {});
  first.fail();
  await wait(25);
  const second = last();
  assert.notEqual(second, first);
  second.open();
  assert.deepEqual(second.frames, [{ type: 'subscribe', channel: 'news' }]); // resubscribed automatically
  second.fail();
  await wait(25);
  assert.deepEqual(seen, [[1, 5], [1, 5]]); // attempts reset after the successful reconnect
});

test('socket: gives up after maxAttempts and emits reconnect_failed', async () => {
  const s = socket({ reconnect: { maxAttempts: 2, delay: 2, factor: 1 } });
  let failed = null;
  s.on('reconnect_failed', e => { failed = e; });
  const p = s.connect(); last().open(); await p;
  last().fail();
  for (let i = 0; i < 3; i += 1) { await wait(15); if (last().readyState === 0) last().fail(); }
  assert.equal(failed?.attempts, 2);
  assert.equal(FakeWS.instances.length, 3);
});

test('socket: connect() rejects if the first attempt fails; close() never reconnects', async () => {
  const s = socket({ reconnect: { enabled: false } });
  const p = s.connect();
  last().fail();
  await assert.rejects(p, NetworkError);
  const t = socket();
  const ok = t.connect(); last().open(); await ok;
  t.close();
  await wait(30);
  assert.equal(FakeWS.instances.length, 1);
  assert.equal(t.state, 'closed');
});

test('socket: heartbeat pings, accepts any inbound traffic as proof of life, closes when silent', async () => {
  const s = socket({ heartbeat: { enabled: true, interval: 15, timeout: 15 }, reconnect: { enabled: false } });
  const p = s.connect(); const ws = last(); ws.open(); await p;
  await wait(20);
  assert.deepEqual(ws.frames.filter(f => f.type === 'ping').length >= 1, true);
  ws.say({ type: 'pong' });                    // answered: stays open
  await wait(10);
  assert.equal(ws.readyState, 1);
  await wait(60);                              // never answered again: closed by the client
  assert.equal(ws.readyState, 3);
  assert.equal(s.state, 'closed');
});

test('socket: heartbeat is off unless enabled', async () => {
  const s = socket();
  const p = s.connect(); const ws = last(); ws.open(); await p;
  await wait(40);
  assert.equal(ws.frames.some(f => f.type === 'ping'), false);
  s.close();
});

// ------------------------------------------------------------------ scope + plugin
test('scope: dispose aborts in-flight requests and runs tracked cleanups', async () => {
  const hang = (url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(Object.assign(new Error('x'), { name: 'AbortError' }))));
  const http = new HttpClient({ fetch: fakeFetch(hang), timeout: 0 });
  const action = new ActionClient({ fetch: fakeFetch(hang), timeout: 0 });
  const scope = createScope({ http, action });
  const requests = [scope.get('/a'), scope.call('x', {})];
  const cleaned = [];
  scope.track(() => cleaned.push('unsub'));
  scope.dispose();
  for (const request of requests) await assert.rejects(request, e => e.code === 'aborted');
  assert.deepEqual(cleaned, ['unsub']);
  await assert.rejects(scope.get('/again'), e => e.code === 'aborted');
});

test('plugin: installs http/action/socket on a runtime api object', () => {
  const api = {};
  networkPlugin.install(api);
  assert.deepEqual([typeof api.http.get, typeof api.action.call, typeof api.socket], ['function', 'function', 'function']);
  assert.equal(api.SocketClient, SocketClient);
});

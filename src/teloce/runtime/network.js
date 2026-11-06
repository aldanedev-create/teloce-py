/**
 * Framework-agnostic network clients: an HTTP client, a server-action client and a
 * WebSocket channel client. They speak plain JSON over standard HTTP/WebSocket, so any
 * backend that implements the small protocol in docs/network-api.md can serve them.
 * @module
 */
/** @import {DynamicValue, DynamicRecord} from './contracts.js' */
import { createSignal } from './signals.js';

/**
 * @typedef {{retries?: number, delay?: number, factor?: number, maxDelay?: number,
 *   methods?: string[], statuses?: number[]}} RetryOptions
 * @typedef {{enabled?: boolean, cookieName?: string, headerName?: string,
 *   token?: string | (() => string | undefined)}} CsrfOptions
 * @typedef {{baseURL?: string, headers?: Record<string, string>, credentials?: RequestCredentials,
 *   timeout?: number, retry?: number | RetryOptions, csrf?: CsrfOptions,
 *   fetch?: typeof fetch}} HttpConfig
 * @typedef {HttpConfig & {url?: string, method?: string, params?: DynamicRecord, data?: DynamicValue,
 *   signal?: AbortSignal | null, responseType?: 'auto' | 'json' | 'text' | 'blob' | 'arrayBuffer'}} RequestConfig
 * @typedef {{data: DynamicValue, status: number, statusText: string, headers: Record<string, string>,
 *   config: RequestConfig, ok: boolean}} HttpResponse
 * @typedef {(config: RequestConfig) => RequestConfig | void | Promise<RequestConfig | void>} RequestInterceptor
 * @typedef {(response: HttpResponse) => HttpResponse | void | Promise<HttpResponse | void>} ResponseInterceptor
 * @typedef {(error: NetworkError) => DynamicValue} ErrorInterceptor
 */

/** Transport failure: timeout, abort, or a network error. HTTP error statuses are NOT thrown. */
export class NetworkError extends Error {
  /**
   * @param {string} message
   * @param {'timeout' | 'aborted' | 'network' | 'invalid_request' | 'queue_full' | 'closed'} code
   * @param {DynamicRecord} [details]
   */
  constructor(message, code, details = {}) {
    super(message);
    this.name = 'NetworkError';
    this.code = code;
    /** @type {RequestConfig | undefined} */
    this.config = /** @type {RequestConfig | undefined} */ (details.config);
    this.cause = details.cause;
  }
}

const SAFE_RETRY_METHODS = ['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'];
const RETRY_STATUSES = [408, 425, 429, 500, 502, 503, 504];
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** @param {DynamicValue} value @returns {value is DynamicRecord} */
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);

/** @param {Record<string, string> | undefined} headers @returns {Record<string, string>} */
function lowerHeaders(headers) {
  /** @type {Record<string, string>} */
  const out = {};
  for (const [key, value] of Object.entries(headers || {})) if (value != null) out[key.toLowerCase()] = String(value);
  return out;
}

/** @param {string} url @param {DynamicRecord | undefined} params */
function withParams(url, params) {
  if (!params) return url;
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    const values = Array.isArray(raw) ? raw : [raw];
    for (const value of values) {
      if (value === undefined || value === null) continue;
      search.append(key, value instanceof Date ? value.toISOString() : String(value));
    }
  }
  const query = search.toString();
  if (!query) return url;
  const hash = url.indexOf('#');
  const base = hash === -1 ? url : url.slice(0, hash);
  const fragment = hash === -1 ? '' : url.slice(hash);
  return `${base}${base.includes('?') ? '&' : '?'}${query}${fragment}`;
}

/** @param {string | undefined} baseURL @param {string} url */
function joinURL(baseURL, url) {
  if (!baseURL || /^([a-z][a-z\d+.-]*:|\/\/)/i.test(url)) return url;
  return `${baseURL.replace(/\/+$/, '')}/${url.replace(/^\/+/, '')}`;
}

/** @param {string} url @param {string | undefined} baseURL True when a secret header may be sent to `url`. */
function isTrustedTarget(url, baseURL) {
  if (!/^([a-z][a-z\d+.-]*:)?\/\//i.test(url)) return true; // relative: same origin as the page
  const page = /** @type {DynamicValue} */ (globalThis).location;
  try {
    const target = new URL(url, page?.href).origin;
    if (page?.origin && target === page.origin) return true;
    return Boolean(baseURL) && target === new URL(/** @type {string} */ (baseURL), page?.href).origin;
  } catch { return false; }
}

/** @param {string} name @returns {string | undefined} */
function readCookie(name) {
  const doc = /** @type {DynamicValue} */ (globalThis).document;
  if (!doc || typeof doc.cookie !== 'string') return undefined;
  for (const part of doc.cookie.split(';')) {
    const index = part.indexOf('=');
    if (index > -1 && part.slice(0, index).trim() === name) return decodeURIComponent(part.slice(index + 1).trim());
  }
  return undefined;
}

/** @param {number} ms @param {AbortSignal | null | undefined} signal */
function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new NetworkError('Request aborted', 'aborted'));
    const timer = setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(undefined); }, ms);
    const onAbort = () => { clearTimeout(timer); reject(new NetworkError('Request aborted', 'aborted')); };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** @param {...(AbortSignal | null | undefined)} signals @returns {AbortSignal | undefined} */
function anySignal(...signals) {
  const live = signals.filter(/** @param {AbortSignal | null | undefined} s @returns {s is AbortSignal} */ s => Boolean(s));
  if (live.length < 2) return live[0];
  const controller = new AbortController();
  for (const signal of live) {
    if (signal.aborted) { controller.abort(signal.reason); break; }
    signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });
  }
  return controller.signal;
}

/** @param {number | RetryOptions | undefined} retry @returns {Required<RetryOptions>} */
function normalizeRetry(retry) {
  const base = typeof retry === 'number' ? { retries: retry } : retry || {};
  return {
    retries: Math.max(0, Math.floor(base.retries ?? 0)),
    delay: base.delay ?? 300,
    factor: base.factor ?? 2,
    maxDelay: base.maxDelay ?? 5000,
    methods: (base.methods ?? SAFE_RETRY_METHODS).map(method => method.toUpperCase()),
    statuses: base.statuses ?? RETRY_STATUSES,
  };
}

/** @param {DynamicValue} value */
function isRawBody(value) {
  const g = /** @type {DynamicRecord} */ (globalThis);
  if (typeof value === 'string') return true;
  return ['FormData', 'Blob', 'ArrayBuffer', 'URLSearchParams', 'ReadableStream']
    .some(name => typeof g[name] === 'function' && value instanceof g[name]) || ArrayBuffer.isView(value);
}

export class HttpClient {
  /** @param {HttpConfig} [config] */
  constructor(config = {}) {
    /** @type {HttpConfig} */
    this.config = { credentials: 'same-origin', timeout: 10000, retry: 0, csrf: { enabled: false }, ...config, headers: { ...config.headers } };
    /** @type {RequestInterceptor[]} */ this.requestInterceptors = [];
    /** @type {ResponseInterceptor[]} */ this.responseInterceptors = [];
    /** @type {ErrorInterceptor[]} */ this.errorInterceptors = [];
  }

  /** Merge defaults. Headers and csrf options are merged one level deep. @param {HttpConfig} config */
  setConfig(config) {
    this.config = {
      ...this.config, ...config,
      headers: { ...this.config.headers, ...config.headers },
      csrf: { ...this.config.csrf, ...config.csrf },
    };
    return this;
  }

  /** @param {RequestInterceptor} fn @returns {() => void} */
  useRequestInterceptor(fn) { return this.#add(this.requestInterceptors, fn); }
  /** @param {ResponseInterceptor} fn @returns {() => void} */
  useResponseInterceptor(fn) { return this.#add(this.responseInterceptors, fn); }
  /** Runs only for thrown transport errors. Return an Error to replace it, or a response to recover. @param {ErrorInterceptor} fn */
  useErrorInterceptor(fn) { return this.#add(this.errorInterceptors, fn); }

  /** @template T @param {T[]} list @param {T} fn @returns {() => void} */
  #add(list, fn) { list.push(fn); return () => { const i = list.indexOf(fn); if (i > -1) list.splice(i, 1); }; }

  /** @param {RequestConfig} input @returns {Promise<HttpResponse>} */
  async request(input) {
    /** @type {RequestConfig} */
    let config = {
      ...this.config, ...input,
      headers: { ...lowerHeaders(this.config.headers), ...lowerHeaders(input.headers) },
      csrf: { ...this.config.csrf, ...input.csrf },
    };
    for (const intercept of this.requestInterceptors) config = (await intercept(config)) || config;
    config = { ...config, headers: lowerHeaders(config.headers) }; // interceptors may add differently-cased names
    try {
      /** @type {HttpResponse} */
      let response = await this.#send(config);
      for (const intercept of this.responseInterceptors) response = (await intercept(response)) || response;
      return response;
    } catch (raw) {
      let error = /** @type {NetworkError} */ (raw);
      if (!(error instanceof NetworkError)) throw error;
      for (const intercept of this.errorInterceptors) {
        const result = await intercept(error);
        if (result instanceof Error) error = /** @type {NetworkError} */ (result);
        else if (isRecord(result) && typeof result.status === 'number') return /** @type {HttpResponse} */ (result);
      }
      throw error;
    }
  }

  /** @param {string} url @param {RequestConfig} [config] */ get(url, config) { return this.request({ ...config, url, method: 'GET' }); }
  /** @param {string} url @param {RequestConfig} [config] */ head(url, config) { return this.request({ ...config, url, method: 'HEAD' }); }
  /** @param {string} url @param {RequestConfig} [config] */ options(url, config) { return this.request({ ...config, url, method: 'OPTIONS' }); }
  /** @param {string} url @param {RequestConfig} [config] */ delete(url, config) { return this.request({ ...config, url, method: 'DELETE' }); }
  /** @param {string} url @param {DynamicValue} [data] @param {RequestConfig} [config] */ post(url, data, config) { return this.request({ ...config, url, data, method: 'POST' }); }
  /** @param {string} url @param {DynamicValue} [data] @param {RequestConfig} [config] */ put(url, data, config) { return this.request({ ...config, url, data, method: 'PUT' }); }
  /** @param {string} url @param {DynamicValue} [data] @param {RequestConfig} [config] */ patch(url, data, config) { return this.request({ ...config, url, data, method: 'PATCH' }); }

  /** @param {RequestConfig} config @returns {Promise<HttpResponse>} */
  async #send(config) {
    const method = (config.method || 'GET').toUpperCase();
    const retry = normalizeRetry(config.retry);
    for (let attempt = 0; ; attempt += 1) {
      const canRetry = attempt < retry.retries && retry.methods.includes(method);
      try {
        const response = await this.#once(config, method);
        if (canRetry && retry.statuses.includes(response.status)) {
          await sleep(Math.min(retry.maxDelay, retry.delay * retry.factor ** attempt), config.signal);
          continue;
        }
        return response;
      } catch (raw) {
        const error = /** @type {DynamicValue} */ (raw);
        if (canRetry && error instanceof NetworkError && (error.code === 'network' || error.code === 'timeout')) {
          await sleep(Math.min(retry.maxDelay, retry.delay * retry.factor ** attempt), config.signal);
          continue;
        }
        throw raw;
      }
    }
  }

  /** @param {RequestConfig} config @param {string} method @returns {Promise<HttpResponse>} */
  async #once(config, method) {
    if (typeof config.url !== 'string' || !config.url) throw new NetworkError('A request URL is required', 'invalid_request', { config });
    const url = withParams(joinURL(config.baseURL, config.url), config.params);
    /** @type {Record<string, string>} */
    const headers = { accept: 'application/json, text/plain, */*', ...config.headers };
    /** @type {BodyInit | undefined} */
    let body;
    if (config.data !== undefined && config.data !== null && method !== 'GET' && method !== 'HEAD') {
      if (isRawBody(config.data)) body = /** @type {BodyInit} */ (config.data);
      else { body = JSON.stringify(config.data); headers['content-type'] ||= 'application/json'; }
    }
    const csrf = config.csrf;
    if (csrf?.enabled && UNSAFE_METHODS.has(method) && isTrustedTarget(url, config.baseURL)) {
      const supplied = typeof csrf.token === 'function' ? csrf.token() : csrf.token;
      const token = supplied || readCookie(csrf.cookieName || 'csrftoken');
      if (token) headers[(csrf.headerName || 'X-CSRFToken').toLowerCase()] = token;
    }
    if (config.signal?.aborted) throw new NetworkError('Request aborted', 'aborted', { config });

    const controller = new AbortController();
    let timedOut = false;
    const onAbort = () => controller.abort();
    config.signal?.addEventListener('abort', onAbort, { once: true });
    const timer = config.timeout && config.timeout > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, config.timeout) : undefined;
    const impl = config.fetch || globalThis.fetch;
    try {
      const res = await impl(url, { method, headers, body, credentials: config.credentials, signal: controller.signal });
      const data = await this.#parse(res, method, config.responseType);
      /** @type {Record<string, string>} */
      const responseHeaders = {};
      res.headers.forEach((value, key) => { responseHeaders[key.toLowerCase()] = value; });
      return { data, status: res.status, statusText: res.statusText, headers: responseHeaders, config: { ...config, url }, ok: res.ok };
    } catch (raw) {
      const cause = /** @type {DynamicValue} */ (raw);
      if (cause instanceof NetworkError) throw cause;
      if (timedOut) throw new NetworkError(`Request timed out after ${config.timeout}ms`, 'timeout', { config, cause });
      if (config.signal?.aborted || cause?.name === 'AbortError') throw new NetworkError('Request aborted', 'aborted', { config, cause });
      throw new NetworkError('Network request failed', 'network', { config, cause });
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      config.signal?.removeEventListener('abort', onAbort);
    }
  }

  /** @param {Response} res @param {string} method @param {RequestConfig['responseType']} type */
  async #parse(res, method, type = 'auto') {
    if (method === 'HEAD' || res.status === 204 || res.status === 205) return null;
    if (type === 'blob') return res.blob();
    if (type === 'arrayBuffer') return res.arrayBuffer();
    const contentType = res.headers.get('content-type') || '';
    if (type === 'text' || (type === 'auto' && /^text\//i.test(contentType))) return res.text();
    if (type === 'json' || /\bjson\b/i.test(contentType)) {
      const text = await res.text();
      if (!text) return null;
      try { return JSON.parse(text); } catch { return text; }
    }
    return res.text();
  }
}

/** @param {HttpConfig} [config] */
export const createHttp = config => new HttpClient(config);
/** Shared default HTTP client. */
export const http = createHttp();

// ---------------------------------------------------------------------------------------------
// Server actions
// ---------------------------------------------------------------------------------------------

/**
 * @typedef {{success: boolean, data?: DynamicValue, error?: string, code?: string, status: number,
 *   details?: DynamicValue}} ActionResult
 * @typedef {{ttl?: number} | boolean} CacheOption
 * @typedef {HttpConfig & {baseURL?: string, actionPath?: string, cache?: CacheOption}} ActionConfig
 * @typedef {{cache?: CacheOption, idempotent?: boolean, signal?: AbortSignal | null, timeout?: number,
 *   retry?: number}} CallOptions
 */

const ACTION_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$/;
const DEFAULT_CACHE_TTL = 30000;

/** Stable JSON for cache keys. @param {DynamicValue} value @returns {string} */
function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (isRecord(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}

export class ActionClient {
  /** @param {ActionConfig} [config] */
  constructor(config = {}) {
    /** @type {ActionConfig} */
    this.config = { actionPath: '/_teloce/actions', timeout: 15000, retry: 0, cache: false, credentials: 'same-origin', ...config };
    this.http = new HttpClient({ ...this.config, headers: { 'x-teloce-action': '1', ...config.headers } });
    /** @type {Map<string, {expires: number, result: ActionResult}>} */ this.cache = new Map();
    /** @type {Map<string, Promise<ActionResult>>} */ this.inflight = new Map();
  }

  /** @param {ActionConfig} config */
  setConfig(config) {
    this.config = { ...this.config, ...config };
    const { actionPath, cache, ...httpConfig } = config; void actionPath; void cache;
    this.http.setConfig({ ...httpConfig, headers: { 'x-teloce-action': '1', ...httpConfig.headers } });
    return this;
  }

  /**
   * Call a named server action. Resolves with `{success, data, error, code, status}` for HTTP and
   * application failures; transport failures (timeout, offline, abort) throw NetworkError.
   * @param {string} name @param {DynamicValue} [data] @param {CallOptions} [options] @returns {Promise<ActionResult>}
   */
  async call(name, data, options = {}) {
    if (typeof name !== 'string' || !ACTION_NAME.test(name)) throw new TypeError(`Invalid action name: ${String(name)}`);
    const cacheOption = options.cache ?? this.config.cache;
    const ttl = typeof cacheOption === 'object' ? cacheOption.ttl ?? DEFAULT_CACHE_TTL : cacheOption ? DEFAULT_CACHE_TTL : 0;
    const key = `${name}\u0000${stableStringify(data)}`;
    if (ttl > 0) {
      const hit = this.cache.get(key);
      if (hit && hit.expires > Date.now()) return hit.result;
      const pending = this.inflight.get(key);
      if (pending) return pending;
    }
    const run = this.#perform(name, data, options).then(result => {
      if (ttl > 0 && result.success) this.cache.set(key, { expires: Date.now() + ttl, result });
      return result;
    }).finally(() => { this.inflight.delete(key); });
    if (ttl > 0) this.inflight.set(key, run);
    return run;
  }

  /** @param {string} name @param {DynamicValue} data @param {CallOptions} options @returns {Promise<ActionResult>} */
  async #perform(name, data, options) {
    const retries = options.idempotent ? options.retry ?? (typeof this.config.retry === 'number' ? this.config.retry : 0) : 0;
    const path = joinURL(this.config.actionPath, encodeURIComponent(name));
    const response = await this.http.post(path, { data: data ?? null }, {
      signal: options.signal, timeout: options.timeout,
      retry: retries ? { retries, methods: ['POST'] } : 0,
    });
    const body = response.data;
    const failed = !response.ok || (isRecord(body) && body.success === false);
    if (!failed) return { success: true, status: response.status, data: isRecord(body) && 'data' in body ? body.data : body };
    const message = isRecord(body) ? body.error ?? body.message : typeof body === 'string' && body ? body : undefined;
    return {
      success: false, status: response.status,
      error: typeof message === 'string' ? message : response.statusText || 'Action failed',
      code: isRecord(body) && typeof body.code === 'string' ? body.code : undefined,
      details: isRecord(body) ? body.details : undefined,
    };
  }

  /**
   * Drop cached results. No argument clears everything; `name` clears every cached call of that
   * action; a trailing `*` clears by prefix; passing `data` clears one exact call.
   * @param {string} [name] @param {DynamicValue} [data]
   */
  invalidate(name, data) {
    if (name === undefined) { this.cache.clear(); return; }
    if (data !== undefined) { this.cache.delete(`${name}\u0000${stableStringify(data)}`); return; }
    const prefix = name.endsWith('*') ? name.slice(0, -1) : undefined;
    for (const key of [...this.cache.keys()]) {
      const action = key.slice(0, key.indexOf('\u0000'));
      if (prefix !== undefined ? action.startsWith(prefix) : action === name) this.cache.delete(key);
    }
  }

  /**
   * Reactive view of an action: `data()`, `error()` and `loading()` are Teloce signals.
   * `data` may be a function so the request can read other signals when it (re)loads.
   * @param {string} name @param {DynamicValue | (() => DynamicValue)} [data]
   * @param {CallOptions & {immediate?: boolean}} [options]
   */
  resource(name, data, options = {}) {
    const value = createSignal(/** @type {DynamicValue} */ (undefined));
    const error = createSignal(/** @type {DynamicValue} */ (null));
    const loading = createSignal(false);
    let sequence = 0;
    let controller = new AbortController();
    const load = async () => {
      const id = ++sequence;
      controller.abort();
      controller = new AbortController();
      loading.set(true);
      try {
        const input = typeof data === 'function' ? data() : data;
        const result = await this.call(name, input, { ...options, signal: anySignal(options.signal, controller.signal) });
        if (id !== sequence) return;
        if (result.success) { value.set(result.data); error.set(null); } else error.set(result);
      } catch (raw) {
        if (id !== sequence || (raw instanceof NetworkError && raw.code === 'aborted')) return;
        error.set(raw);
      } finally { if (id === sequence) loading.set(false); }
    };
    if (options.immediate !== false) void load();
    return { data: value, error, loading, refresh: load, dispose() { sequence += 1; controller.abort(); } };
  }
}

/** @param {ActionConfig} [config] */
export const createActionClient = config => new ActionClient(config);
/** Shared default action client: `action.call("todos.create", {title})`. */
export const action = createActionClient();

// ---------------------------------------------------------------------------------------------
// WebSocket channels
// ---------------------------------------------------------------------------------------------

/**
 * @typedef {{enabled?: boolean, maxAttempts?: number, delay?: number, factor?: number,
 *   maxDelay?: number, jitter?: number}} ReconnectOptions
 * @typedef {{enabled?: boolean, interval?: number, timeout?: number, message?: DynamicValue}} HeartbeatOptions
 * @typedef {{url: string, protocols?: string | string[], reconnect?: ReconnectOptions,
 *   heartbeat?: HeartbeatOptions, queue?: {maxSize?: number},
 *   WebSocket?: new (url: string, protocols?: string | string[]) => WebSocket}} SocketOptions
 * @typedef {'open' | 'message' | 'close' | 'error' | 'reconnecting' | 'reconnect_failed'} SocketEvent
 */

const CHANNEL_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$/;

/** @param {string} url @returns {string} */
function toSocketURL(url) {
  const page = /** @type {DynamicValue} */ (globalThis).location;
  const resolved = new URL(url, page?.href);
  if (resolved.protocol === 'http:') resolved.protocol = 'ws:';
  else if (resolved.protocol === 'https:') resolved.protocol = 'wss:';
  if (resolved.protocol !== 'ws:' && resolved.protocol !== 'wss:') throw new TypeError('Socket URL must use ws: or wss:');
  return resolved.toString();
}

export class SocketClient {
  /** @param {SocketOptions} options */
  constructor(options) {
    if (!options || typeof options.url !== 'string') throw new TypeError('SocketClient requires a url');
    this.url = toSocketURL(options.url);
    this.options = {
      protocols: options.protocols,
      WebSocket: options.WebSocket,
      reconnect: { enabled: true, maxAttempts: 5, delay: 1000, factor: 2, maxDelay: 30000, jitter: 0.2, ...options.reconnect },
      heartbeat: { enabled: false, interval: 25000, timeout: 10000, message: { type: 'ping' }, ...options.heartbeat },
      queue: { maxSize: 100, ...options.queue },
    };
    /** @type {'idle' | 'connecting' | 'open' | 'closed'} */ this.state = 'idle';
    /** @type {WebSocket | null} */ this.ws = null;
    /** @type {string[]} */ this.queue = [];
    /** @type {Map<SocketEvent, Set<(payload: DynamicValue) => void>>} */ this.listeners = new Map();
    /** @type {Map<string, Set<(data: DynamicValue, message: DynamicRecord) => void>>} */ this.channels = new Map();
    /** @type {Promise<void> | null} */ this.connecting = null;
    this.attempts = 0;
    this.manualClose = false;
    /** @type {ReturnType<typeof setTimeout> | undefined} */ this.reconnectTimer = undefined;
    /** @type {ReturnType<typeof setInterval> | undefined} */ this.pingTimer = undefined;
    /** @type {ReturnType<typeof setTimeout> | undefined} */ this.pongTimer = undefined;
  }

  /** @param {SocketEvent} event @param {(payload: DynamicValue) => void} fn @returns {() => void} */
  on(event, fn) {
    const set = this.listeners.get(event) || new Set();
    set.add(fn); this.listeners.set(event, set);
    return () => { set.delete(fn); };
  }

  /** @param {SocketEvent} event @param {DynamicValue} payload */
  #emit(event, payload) {
    for (const fn of [...(this.listeners.get(event) || [])]) {
      try { fn(payload); } catch (error) { console.error('Teloce socket listener failed', error); }
    }
  }

  /** Open the connection; resolves once open, rejects if the first attempt fails. @returns {Promise<void>} */
  connect() {
    if (this.state === 'open') return Promise.resolve();
    if (this.connecting) return this.connecting;
    this.manualClose = false;
    this.connecting = new Promise((resolve, reject) => { this.#open(resolve, reject); });
    this.connecting.catch(() => {}).finally(() => { this.connecting = null; });
    return this.connecting;
  }

  /** @param {() => void} resolve @param {(error: Error) => void} reject */
  #open(resolve, reject) {
    const Impl = this.options.WebSocket || globalThis.WebSocket;
    if (typeof Impl !== 'function') { reject(new NetworkError('WebSocket is not available', 'network')); return; }
    clearTimeout(this.reconnectTimer);
    this.state = 'connecting';
    let opened = false;
    const ws = new Impl(this.url, this.options.protocols);
    this.ws = ws;
    ws.addEventListener('open', () => {
      if (this.ws !== ws) return;
      opened = true; this.state = 'open'; this.attempts = 0;
      for (const channel of this.channels.keys()) this.#raw(JSON.stringify({ type: 'subscribe', channel }));
      const queued = this.queue.splice(0);
      for (const message of queued) this.#raw(message);
      this.#startHeartbeat();
      this.#emit('open', {});
      resolve();
    });
    ws.addEventListener('message', event => { if (this.ws === ws) this.#onMessage(event.data); });
    ws.addEventListener('error', event => { if (this.ws === ws) this.#emit('error', event); });
    ws.addEventListener('close', event => {
      if (this.ws !== ws) return;
      this.#stopHeartbeat(); this.state = 'closed'; this.ws = null;
      this.#emit('close', { code: event.code, reason: event.reason, wasClean: event.wasClean });
      if (!opened) reject(new NetworkError('WebSocket connection failed', 'network'));
      this.#maybeReconnect();
    });
  }

  #maybeReconnect() {
    const { enabled, maxAttempts, delay, factor, maxDelay, jitter } = /** @type {Required<ReconnectOptions>} */ (this.options.reconnect);
    if (this.manualClose || !enabled) return;
    if (this.attempts >= maxAttempts) { this.#emit('reconnect_failed', { attempts: this.attempts }); return; }
    this.attempts += 1;
    const base = Math.min(maxDelay, delay * factor ** (this.attempts - 1));
    const wait = Math.round(base * (1 + (Math.random() * 2 - 1) * jitter));
    this.#emit('reconnecting', { attempt: this.attempts, delay: wait });
    this.reconnectTimer = setTimeout(() => { this.#open(() => {}, () => {}); }, wait);
  }

  /** @param {DynamicValue} raw */
  #onMessage(raw) {
    this.#heard();
    let data = raw;
    if (typeof raw === 'string') { try { data = JSON.parse(raw); } catch { data = raw; } }
    if (isRecord(data) && data.type === 'pong') return;
    if (isRecord(data) && (data.type === 'message' || data.type === 'publish') && typeof data.channel === 'string') {
      for (const handler of [...(this.channels.get(data.channel) || [])]) {
        try { handler(data.data, data); } catch (error) { console.error('Teloce channel handler failed', error); }
      }
    }
    this.#emit('message', { data, raw });
  }

  /** @param {string} text */
  #raw(text) { this.ws?.send(text); }

  /**
   * Send a message. Objects are JSON-encoded; strings are sent as-is. Messages sent before the
   * connection is open are queued (up to `queue.maxSize`). Returns true when sent immediately.
   * @param {DynamicValue} message @returns {boolean}
   */
  send(message) {
    const text = typeof message === 'string' ? message : JSON.stringify(message);
    if (this.state === 'open' && this.ws) { this.#raw(text); return true; }
    if (this.queue.length >= (this.options.queue.maxSize ?? 100)) throw new NetworkError('Socket send queue is full', 'queue_full');
    this.queue.push(text);
    return false;
  }

  /** Subscribe to a channel; the server must implement the subscribe/publish protocol. @param {string} channel @param {(data: DynamicValue, message: DynamicRecord) => void} handler @returns {() => void} */
  subscribe(channel, handler) {
    if (!CHANNEL_NAME.test(channel)) throw new TypeError(`Invalid channel name: ${String(channel)}`);
    let handlers = this.channels.get(channel);
    const first = !handlers;
    if (!handlers) { handlers = new Set(); this.channels.set(channel, handlers); }
    handlers.add(handler);
    if (first) this.send({ type: 'subscribe', channel });
    return () => {
      const set = this.channels.get(channel);
      if (!set || !set.delete(handler) || set.size) return;
      this.channels.delete(channel);
      if (this.state === 'open') this.send({ type: 'unsubscribe', channel });
    };
  }

  /** @param {string} channel @param {DynamicValue} data */
  publish(channel, data) {
    if (!CHANNEL_NAME.test(channel)) throw new TypeError(`Invalid channel name: ${String(channel)}`);
    return this.send({ type: 'publish', channel, data });
  }

  /** Close for good: no reconnect, queue cleared. @param {number} [code] @param {string} [reason] */
  close(code = 1000, reason = '') {
    this.manualClose = true;
    clearTimeout(this.reconnectTimer); this.#stopHeartbeat();
    this.queue.length = 0;
    const ws = this.ws;
    if (ws && ws.readyState <= 1) ws.close(code, reason);
    else this.state = 'closed';
  }

  #startHeartbeat() {
    const { enabled, interval, timeout, message } = /** @type {Required<HeartbeatOptions>} */ (this.options.heartbeat);
    this.#stopHeartbeat();
    if (!enabled) return;
    this.pingTimer = setInterval(() => {
      if (this.state !== 'open') return;
      this.send(message);
      clearTimeout(this.pongTimer);
      this.pongTimer = setTimeout(() => { this.ws?.close(4000, 'heartbeat timeout'); }, timeout);
    }, interval);
  }

  /** Any inbound message proves the link is alive. */
  #heard() { clearTimeout(this.pongTimer); this.pongTimer = undefined; }

  #stopHeartbeat() { clearInterval(this.pingTimer); clearTimeout(this.pongTimer); this.pingTimer = undefined; this.pongTimer = undefined; }
}

/** @param {SocketOptions} options */
export const createSocket = options => new SocketClient(options);

// ---------------------------------------------------------------------------------------------
// Component-scoped cleanup and the standalone plugin
// ---------------------------------------------------------------------------------------------

/**
 * Tie requests and subscriptions to a component lifetime. Call `scope.dispose()` from the
 * component's `unmounted` hook: in-flight requests are aborted and subscriptions removed.
 * @param {{http?: HttpClient, action?: ActionClient}} [clients]
 */
export function createScope(clients = {}) {
  const controller = new AbortController();
  /** @type {Array<() => void>} */
  const disposers = [];
  const baseHttp = clients.http || http;
  const baseAction = clients.action || action;
  return {
    signal: controller.signal,
    /** @param {string} url @param {RequestConfig} [config] */
    get: (url, config) => baseHttp.get(url, { ...config, signal: anySignal(config?.signal, controller.signal) }),
    /** @param {string} url @param {DynamicValue} [data] @param {RequestConfig} [config] */
    post: (url, data, config) => baseHttp.post(url, data, { ...config, signal: anySignal(config?.signal, controller.signal) }),
    /** @param {RequestConfig} config */
    request: config => baseHttp.request({ ...config, signal: anySignal(config.signal, controller.signal) }),
    /** @param {string} name @param {DynamicValue} [data] @param {CallOptions} [options] */
    call: (name, data, options) => baseAction.call(name, data, { ...options, signal: anySignal(options?.signal, controller.signal) }),
    /** Register any cleanup function, such as an unsubscribe returned by `subscribe`. @param {() => void} fn */
    track(fn) { disposers.push(fn); return fn; },
    dispose() { controller.abort(); for (const fn of disposers.splice(0)) { try { fn(); } catch (error) { console.error(error); } } },
  };
}

/** Standalone plugin: `teloce.use(networkPlugin)` adds `teloce.http`, `teloce.action`, `teloce.socket`. */
export const networkPlugin = {
  name: 'teloce-network',
  /** @param {DynamicRecord} api */
  install(api) {
    api.http = http; api.action = action; api.socket = createSocket;
    api.SocketClient = SocketClient; api.createScope = createScope; api.NetworkError = NetworkError;
  },
};

// Loaded as a module after the standalone runtime? Attach automatically.
{
  const root = /** @type {DynamicRecord} */ (globalThis);
  if (isRecord(root.teloce) && typeof root.teloce.use === 'function' && !root.teloce.http) root.teloce.use(networkPlugin);
}

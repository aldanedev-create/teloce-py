import { queueJob, batch as schedulerBatch } from './scheduler.js';

/**
 * @typedef {{run: () => unknown}} Subscriber
 */
/**
 * @typedef {{dependencies: Set<Set<Subscriber>>, stopped: boolean,
 *   running: boolean, run: () => unknown, stop: () => void}} Effect
 */
/**
 * @template T
 * @typedef {((...args: [] | [T]) => T) & {
 *   value: T, get: () => T, set: (value: T) => T,
 *   update: (updater: (value: T) => T) => T, peek: () => T,
 *   subscribe: (listener: ((value: T) => unknown) | {run: (value: T) => unknown}) => () => void,
 *   __teloce_signal: boolean, __teloce_computed?: boolean, effect?: Effect,
 *   [Symbol.iterator]: () => Generator<Signal<T> | ((value: T) => T), void, unknown>
 * }} Signal
 */

/** @type {Effect | null} */
let activeEffect = null;
/** @type {WeakMap<object, Map<PropertyKey, Set<Subscriber>>>} */
const targetDependencies = new WeakMap();
const iterateKey = Symbol('teloce.iterate');
/** @param {PropertyKey} key @returns {boolean} */
const arrayIndex = key => typeof key === 'string' && /^(0|[1-9]\d*)$/.test(key) && Number(key) < 4294967295;

/** @param {object} target @param {PropertyKey} key @returns {void} */
export function track(target, key) {
  if (!activeEffect || activeEffect.stopped) return;
  let dependencies = targetDependencies.get(target);
  if (!dependencies) targetDependencies.set(target, dependencies = new Map());
  let subscribers = dependencies.get(key);
  if (!subscribers) dependencies.set(key, subscribers = new Set());
  subscribers.add(activeEffect);
  activeEffect.dependencies.add(subscribers);
}

/** @param {object} target @param {PropertyKey} key @returns {void} */
export function trigger(target, key) {
  const subscribers = targetDependencies.get(target)?.get(key);
  if (subscribers) for (const effect of [...subscribers]) queueJob(effect.run);
}

/** @type {WeakMap<object, object>} */
const reactiveCache = new WeakMap();
/** @type {WeakSet<object>} */
const reactiveProxies = new WeakSet();
/** @template T @param {T} value @returns {T} */
export function reactive(value) {
  if (!value || typeof value !== 'object') return value;
  if (reactiveProxies.has(value)) return value;
  const prototype = Object.getPrototypeOf(value);
  if (!Array.isArray(value) && prototype !== Object.prototype && prototype !== null) return value;
  if (reactiveCache.has(value)) return /** @type {T} */ (reactiveCache.get(value));
  const proxy = new Proxy(value, {
    get(target, key, receiver) {
      const result = Reflect.get(target, key, receiver);
      track(target, key);
      return result && typeof result === 'object' ? reactive(result) : result;
    },
    set(target, key, next, receiver) {
      const oldLength = Array.isArray(target) ? target.length : 0;
      const existed = Object.prototype.hasOwnProperty.call(target, key);
      const previous = Reflect.get(target, key, receiver);
      const changed = !Object.is(previous, next);
      const result = Reflect.set(target, key, next, receiver);
      if (result && changed) {
        trigger(target, key);
        if (!existed) trigger(target, iterateKey);
        if (Array.isArray(target)) {
          if (arrayIndex(key) && target.length !== oldLength) trigger(target, 'length');
          if (key === 'length' && target.length < oldLength) {
            trigger(target, iterateKey);
            for (const dependency of targetDependencies.get(target)?.keys() || []) {
              if (arrayIndex(dependency) && Number(dependency) >= target.length) trigger(target, dependency);
            }
          }
        }
      }
      return result;
    },
    deleteProperty(target, key) {
      const existed = Object.prototype.hasOwnProperty.call(target, key);
      const result = Reflect.deleteProperty(target, key);
      if (result && existed) { trigger(target, key); trigger(target, iterateKey); }
      return result;
    },
    ownKeys(target) { track(target, iterateKey); return Reflect.ownKeys(target); },
    has(target, key) { track(target, key); return Reflect.has(target, key); },
  });
  reactiveCache.set(value, proxy);
  reactiveProxies.add(proxy);
  return proxy;
}

/** @param {unknown} value @returns {boolean} */
export const isReactive = value => reactiveProxies.has(/** @type {object} */ (value));

/**
 * Fine-grained signal with the public Teloce reactivity API.
 * @template [T=undefined]
 * @param {T} [initial]
 * @returns {Signal<T>}
 */
export function createSignal(initial) {
  let value = /** @type {T} */ (initial);
  /** @type {Set<Subscriber>} */
  const subscribers = new Set();
  /** @type {Signal<T>} */
  const signal = (...args) => {
    if (args.length) {
      const next = args[0];
      if (Object.is(value, next)) return value;
      value = next;
      for (const effect of [...subscribers]) queueJob(effect.run);
      return value;
    }
    if (activeEffect && !activeEffect.stopped) {
      subscribers.add(activeEffect);
      activeEffect.dependencies.add(subscribers);
    }
    return value;
  };
  // Components may bind `signal.value`; keep it equivalent to the callable API
  // so v-model writes notify subscribers instead of creating an inert property.
  Object.defineProperty(signal, 'value', {
    get: () => signal(),
    set: next => { signal(next); },
  });
  signal.get = () => signal();
  signal.set = next => signal(next);
  signal.update = updater => signal(updater(signal()));
  signal.peek = () => value;
  // npm usage supports both `count()`/`count.set(value)` and
  // `const [count, setCount] = createSignal(value)`.
  signal[Symbol.iterator] = function* () {
    yield signal;
    yield signal.set;
  };
  signal.subscribe = listener => {
    const callback = typeof listener === 'function' ? listener : listener?.run?.bind(listener);
    if (typeof callback !== 'function') throw new TypeError('Signal subscriber must be a function or effect');
    let active = true;
    const subscriber = { run() { if (active) callback(value); } };
    subscribers.add(subscriber);
    return () => { active = false; subscribers.delete(subscriber); };
  };
  signal.__teloce_signal = true;
  return signal;
}

/** @param {() => unknown} fn @returns {Effect} */
export function createEffect(fn) {
  /** @type {Effect} */
  const effect = {
    dependencies: new Set(), stopped: false, running: false,
    run() {
      if (effect.stopped || effect.running) return;
      for (const dependency of effect.dependencies) dependency.delete(effect);
      effect.dependencies.clear();
      const previous = activeEffect;
      activeEffect = effect;
      effect.running = true;
      try { return fn(); }
      finally { effect.running = false; activeEffect = previous; }
    },
    stop() {
      effect.stopped = true;
      for (const dependency of effect.dependencies) dependency.delete(effect);
      effect.dependencies.clear();
    },
  };
  effect.run();
  return effect;
}

/** @template T @param {() => T} fn @returns {Signal<T>} */
export function createComputed(fn) {
  // The synchronous effect seeds this initially empty signal before it escapes.
  const result = /** @type {Signal<T>} */ (/** @type {unknown} */ (createSignal()));
  const effect = createEffect(() => result(fn()));
  result.__teloce_computed = true;
  result.effect = effect;
  return result;
}

export const createMemo = createComputed;
/** @template T @param {() => T} fn @returns {T} */
export function batch(fn) { return schedulerBatch(fn); }
/** @template T @param {() => T} fn @returns {T} */
export function untracked(fn) {
  const previous = activeEffect;
  activeEffect = null;
  try { return fn(); } finally { activeEffect = previous; }
}
/** @template T @param {T | Signal<T>} value @returns {value is Signal<T>} */
export const isSignal = value => Boolean(value && /** @type {Partial<Signal<T>>} */ (value).__teloce_signal);
/** @param {unknown} value @returns {boolean} */
export const isComputed = value => Boolean(value && /** @type {Partial<Signal<unknown>>} */ (value).__teloce_computed);
/** @template T @param {T | Signal<T>} value @returns {Signal<T>} */
export const toSignal = value => isSignal(value) ? value : createSignal(value);
/** @template T @param {T | Signal<T>} value @returns {T} */
export const getValue = value => isSignal(value) ? value() : value;

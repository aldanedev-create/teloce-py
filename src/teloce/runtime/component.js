/** Component creation, mounting, lifecycle cleanup and asynchronous loading. @module */
/** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent, ComponentDefinition, ComponentInstance, AsyncOptions} from './contracts.js' */
import { createEffect, reactive } from './reactivity.js';

/** @param {ComponentDefinition} definition */ export function createComponent(definition, /** @type {DynamicRecord} */ props = {}) {
  const state = reactive({ ...(definition.data ? definition.data() : {}), ...props });
  /** @type {RuntimeElement | undefined} */
  let currentTarget;
  /** @type {import("./signals.js").Effect | undefined} */
  let stopEffect;
  /** @type {ComponentInstance} */
  const instance = /** @type {ComponentInstance} */ ({ definition, props, state, mounted: false });
  instance.mount = /** @param {string | Element | null} target */ (target) => {
    if (typeof target === 'string') target = document.querySelector(target);
    if (!target) throw new Error('Teloce mount target was not found');
    if (instance.mounted) instance.unmount();
    currentTarget = target;
    instance.mounted = true;
    definition.beforeMount?.call(state);
    stopEffect = createEffect(() => {
      if (!instance.mounted || !currentTarget) return;
      const root = definition.render ? definition.render(state, instance.props) : document.createDocumentFragment();
      currentTarget.replaceChildren(root);
      definition.updated?.call(state);
    });
    definition.mounted?.call(state);
    return instance;
  };
  instance.updateProps = (/** @type {DynamicRecord} */ nextProps = {}) => {
    instance.props = nextProps;
    Object.assign(state, nextProps);
    return instance;
  };
  instance.unmount = () => {
    if (!instance.mounted) return instance;
    definition.beforeUnmount?.call(state);
    instance.mounted = false;
    stopEffect?.stop?.();
    stopEffect = undefined;
    definition.unmounted?.call(state);
    currentTarget?.replaceChildren();
    currentTarget = undefined;
    return instance;
  };
  return instance;
}

/** @param {ComponentDefinition} definition */ export function createApp(definition) {
  return { /** @param {string | Element | null} target @param {DynamicRecord} [props] */ mount(/** @type {string | Element | null} */ target, /** @type {DynamicRecord} */ props) { return createComponent(definition, props).mount(target); } };
}

/** @param {DynamicCallback} loader */ export function defineAsyncComponent(loader, /** @type {AsyncOptions} */ options = {}) {
  if (typeof loader !== 'function') throw new TypeError('defineAsyncComponent expects a loader function');
  /** @type {DynamicValue} */
  let loaded;
  /** @type {Promise<DynamicValue> | undefined} */
  let loading;
  /** @type {DynamicRecord | undefined} */
  let current;
  /** @type {Element | null | undefined} */
  let target;
  let /** @type {DynamicRecord} */ props = {};
  let mountGeneration = 0;
  let mounted = false;
  const placeholder = options.loading ?? (() => document.createComment('teloce-async-loading'));
  const failure = options.error ?? (() => document.createComment('teloce-async-error'));
  const resolve = /** @param {DynamicRecord} module */ module => module?.default ?? module;
  const load = async () => {
    if (loaded) return loaded;
    if (!loading) loading = Promise.resolve(loader()).then(resolve).then(component => { loaded = component; return component; });
    return loading;
  };
  const instance = {
    get loaded() { return loaded; },
    /** @param {string | Element | null} nextTarget */ async mount(nextTarget, /** @type {DynamicRecord} */ nextProps = {}) {
      target = typeof nextTarget === 'string' ? document.querySelector(nextTarget) : nextTarget;
      if (!target) throw new Error('Teloce mount target was not found');
      props = nextProps;
      const generation = ++mountGeneration;
      mounted = true;
      target.replaceChildren(typeof placeholder === 'function' ? placeholder() : placeholder);
      try {
        const definition = await load();
        // A lazy import can resolve after its host has been unmounted or
        // remounted. Never attach the stale result to the old target.
        if (!mounted || generation !== mountGeneration) return instance;
        current = definition?.mount ? definition.mount(target, props) : createComponent(definition, props).mount(target);
        return instance;
      } catch (error) {
        if (!mounted || generation !== mountGeneration) return instance;
        target.replaceChildren(typeof failure === 'function' ? failure(error) : failure);
        options.onError?.(error);
        throw error;
      }
    },
    updateProps(/** @type {DynamicRecord} */ nextProps = {}) { props = nextProps; current?.updateProps?.(nextProps); },
    unmount() {
      mounted = false;
      mountGeneration += 1;
      current?.unmount?.();
      current = undefined;
      target?.replaceChildren();
      target = undefined;
      return instance;
    },
  };
  return instance;
}

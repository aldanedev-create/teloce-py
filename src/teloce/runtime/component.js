import { createEffect, reactive } from './reactivity.js';

export function createComponent(definition, props = {}) {
  const state = reactive({ ...(definition.data ? definition.data() : {}), ...props });
  let currentTarget;
  let stopEffect;
  const instance = { definition, props, state, mounted: false };
  instance.mount = (target) => {
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
  instance.updateProps = (nextProps = {}) => {
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

export function createApp(definition) {
  return { mount(target, props) { return createComponent(definition, props).mount(target); } };
}

/** Create a component whose implementation is loaded only when mounted. */
export function defineAsyncComponent(loader, options = {}) {
  if (typeof loader !== 'function') throw new TypeError('defineAsyncComponent expects a loader function');
  let loaded;
  let loading;
  let current;
  let target;
  let props = {};
  let mountGeneration = 0;
  let mounted = false;
  const placeholder = options.loading ?? (() => document.createComment('teloce-async-loading'));
  const failure = options.error ?? (() => document.createComment('teloce-async-error'));
  const resolve = module => module?.default ?? module;
  const load = async () => {
    if (loaded) return loaded;
    if (!loading) loading = Promise.resolve(loader()).then(resolve).then(component => { loaded = component; return component; });
    return loading;
  };
  const instance = {
    get loaded() { return loaded; },
    async mount(nextTarget, nextProps = {}) {
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
    updateProps(nextProps = {}) { props = nextProps; current?.updateProps?.(nextProps); },
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

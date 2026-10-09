export const __lis = values => {
  const tails = [], previous = new Int32Array(values.length).fill(-1);
  for (let i = 0; i < values.length; i++) {
    if (values[i] < 0) continue;
    let low = 0, high = tails.length;
    while (low < high) { const middle = (low + high) >>> 1; if (values[tails[middle]] < values[i]) low = middle + 1; else high = middle; }
    if (low) previous[i] = tails[low - 1];
    tails[low] = i;
  }
  const stable = new Set();
  for (let i = tails.length ? tails[tails.length - 1] : -1; i >= 0; i = previous[i]) stable.add(i);
  return stable;
};
export function createElement(tag, props = {}, children = []) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) setAttribute(element, name, value);
  for (const child of children.flat()) if (child != null) element.append(child);
  return element;
}

export function setAttribute(element, name, value) {
  if (name === 'className') name = 'class';
  if (value === false || value == null) element.removeAttribute(name);
  else if (value === true) element.setAttribute(name, '');
  else element.setAttribute(name, String(value));
}

export function bindEvent(element, name, handler, options) {
  element.addEventListener(name, handler, options);
  return () => element.removeEventListener(name, handler, options);
}

export function bindEvents(element, bindings = []) {
  const unbind = bindings.map(binding => {
    const event = typeof binding === 'function' ? binding.event : binding.event || binding.name || binding.type;
    const handler = typeof binding === 'function' ? binding : binding.handler || binding.listener || binding.fn;
    if (!event || typeof handler !== 'function') return () => {};
    return bindEvent(element, event, handler, typeof binding === 'function' ? binding.options : binding.options);
  });
  return () => unbind.forEach(remove => remove());
}

export function createEventHandlerWithModifiers(element, name, handler) {
  const [eventName, ...modifiers] = String(name).split('.');
  const listener = event => {
    if (modifiers.includes('self') && event.target !== element) return;
    if (modifiers.includes('enter') && event.key !== 'Enter') return;
    if (modifiers.includes('esc') && event.key !== 'Escape') return;
    if (modifiers.includes('ctrl') && !event.ctrlKey) return;
    if (modifiers.includes('shift') && !event.shiftKey) return;
    if (modifiers.includes('alt') && !event.altKey) return;
    if (modifiers.includes('meta') && !event.metaKey) return;
    if (modifiers.includes('right') && event.button !== 2) return;
    if (modifiers.includes('middle') && event.button !== 1) return;
    if (modifiers.includes('left') && event.button !== 0) return;
    if (modifiers.includes('prevent')) event.preventDefault();
    if (modifiers.includes('stop')) event.stopPropagation();
    return handler(event);
  };
  listener.event = eventName;
  listener.options = {
    once: modifiers.includes('once'),
    capture: modifiers.includes('capture'),
    passive: modifiers.includes('passive'),
  };
  return listener;
}

export function createFor(container, source, renderItem, key = (_, index) => index) {
  const records = new Map();
  let order = [];
  const read = value => typeof value === 'function' && value.__teloce_signal ? value() : value;
  const update = value => {
    const focused = container.contains?.(document.activeElement) ? document.activeElement : null;
    const selection = focused && typeof focused.selectionStart === 'number'
      ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
    const next = Array.from(read(value) || []);
    const active = new Set();
    const positions = new Map(order.map((node, index) => [node, index]));
    const nodes = next.map((item, index) => {
      const id = key(item, index);
      if (active.has(id)) throw new Error(`Duplicate keyed loop value: ${String(id)}`);
      const old = records.get(id);
      if (old) {
        if ((item !== null && typeof item === 'object') || !Object.is(old.item, item) || old.index !== index) old.update?.(item, index);
        old.item = item;
        old.index = index;
        active.add(id);
        return old.node;
      }
      const rendered = renderItem(item, index);
      const node = rendered?.nodeType ? rendered : rendered?.node;
      if (!node) throw new TypeError('createFor renderItem must return a DOM node');
      records.set(id, {
        item,
        index,
        node,
        update: rendered?.nodeType ? undefined : rendered?.update,
        unmount: rendered?.nodeType ? undefined : rendered?.unmount,
      });
      active.add(id);
      return node;
    });
    for (const [id, record] of records) {
      if (!active.has(id)) {
        record.unmount?.();
        records.delete(id);
      }
    }
    const retained = new Set(nodes);
    for (const node of Array.from(container.childNodes)) if (!retained.has(node)) node.remove();
    const stable = __lis(nodes.map(node => positions.get(node) ?? -1));
    let anchor = null;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const node = nodes[i];
      if (!positions.has(node) || !stable.has(i)) container.insertBefore(node, anchor);
      anchor = node;
    }
    order = nodes;
    if (focused?.isConnected && document.activeElement !== focused) {
      focused.focus({ preventScroll: true });
      if (selection) focused.setSelectionRange(...selection);
    }
  };
  update(source);
  const unsubscribe = source?.subscribe ? source.subscribe(update) : () => {};
  return { update, unmount() { unsubscribe?.(); for (const record of records.values()) record.unmount?.(); records.clear(); container.replaceChildren(); } };
}

export function createIf(container, source, whenTrue, whenFalse = () => null) {
  let previous;
  let initialized = false;
  const read = value => typeof value === 'function' && value.__teloce_signal ? value() : value;
  const update = value => {
    const condition = Boolean(read(value));
    if (initialized && previous === condition) return;
    initialized = true;
    previous = condition;
    const node = (condition ? whenTrue : whenFalse)();
    container.replaceChildren(...(node == null ? [] : Array.isArray(node) ? node : [node]));
  };
  update(source);
  const unsubscribe = source?.subscribe ? source.subscribe(update) : () => {};
  return { update, unmount() { unsubscribe?.(); container.replaceChildren(); } };
}

export function createModel(element, signal) {
  const read = () => typeof signal === 'function' ? signal() : signal?.get?.();
  const write = value => typeof signal?.set === 'function' ? signal.set(value) : typeof signal === 'function' && signal.set ? signal.set(value) : undefined;
  const update = value => {
    const next = value === undefined ? read() : value;
    if (element.type === 'checkbox') element.checked = Boolean(next);
    else if (element.value !== String(next ?? '')) element.value = next ?? '';
  };
  const eventName = element.type === 'checkbox' || element.tagName === 'SELECT' ? 'change' : 'input';
  const listener = () => write(element.type === 'checkbox' ? element.checked : element.value);
  element.addEventListener(eventName, listener);
  update();
  const unsubscribe = signal?.subscribe ? signal.subscribe(update) : () => {};
  return { update, unmount() { unsubscribe?.(); element.removeEventListener(eventName, listener); } };
}

export function createClass(element, source) {
  const staticClass = element.getAttribute('data-teloce-static-class') ?? element.className ?? '';
  element.setAttribute('data-teloce-static-class', staticClass);
  const update = value => {
    const next = value === undefined ? (typeof source === 'function' ? source() : source?.get?.()) : value;
    let dynamicClass = '';
    if (typeof next === 'string') dynamicClass = next;
    else if (Array.isArray(next)) dynamicClass = next.filter(Boolean).join(' ');
    else if (next && typeof next === 'object') dynamicClass = Object.entries(next).filter(([, enabled]) => enabled).map(([name]) => name).join(' ');
    element.className = [staticClass, dynamicClass].filter(Boolean).join(' ');
  };
  update();
  const unsubscribe = source?.subscribe ? source.subscribe(update) : () => {};
  return { update, unmount() { unsubscribe?.(); } };
}

export function clear(element) { while (element.firstChild) element.firstChild.remove(); }

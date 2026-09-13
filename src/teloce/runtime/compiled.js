/* Shared renderer for compiler-generated Teloce components.
 *
 * Generated modules contain the component definition, template, imports and
 * CSS metadata only.  The lifecycle, event, binding, reconciliation and HMR
 * bridge lives here once per application build.
 */

const __teloceEscapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

const __teloceEscapeAttribute = value => __teloceEscapeHtml(value);
const __teloceDecodeAttribute = value => String(value ?? "")
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/&amp;/g, "&");

const __teloceBuiltInTransitions = {
  fade(node, opts = {}) {
    const { duration = 200, easing = "ease" } = opts;
    return node.animate?.([{ opacity: 0 }, { opacity: 1 }], { duration, easing, fill: "forwards" });
  },
  slide(node, opts = {}) {
    const { axis = "y", distance = 10, duration = 200, easing = "ease-out" } = opts;
    const property = axis === "y" ? "translateY" : "translateX";
    return node.animate?.([
      { transform: `${property}(${distance}px)`, opacity: 0 },
      { transform: `${property}(0)`, opacity: 1 },
    ], { duration, easing, fill: "forwards" });
  },
  scale(node, opts = {}) {
    const { start = 0.9, duration = 150, easing = "ease-out" } = opts;
    return node.animate?.([
      { transform: `scale(${start})`, opacity: 0 },
      { transform: "scale(1)", opacity: 1 },
    ], { duration, easing, fill: "forwards" });
  },
};

const __teloceParseTransition = value => {
  const source = String(value ?? "");
  const separator = source.indexOf(":");
  if (separator < 0) return { name: source, options: undefined };
  const name = source.slice(0, separator);
  const rest = source.slice(separator + 1);
  let options;
  try {
    const jsonish = rest
      .replace(/([{,]\s*)([A-Za-z_$][\w$]*)\s*:/g, '$1"$2":')
      .replace(/'([^']*)'/g, '"$1"');
    options = JSON.parse(jsonish);
  } catch (_) {
    options = undefined;
  }
  return { name, options };
};

const __teloceTransitionHooks = definition => {
  const registry = { ...__teloceBuiltInTransitions, ...(definition?.transitions || {}) };
  const run = (node, attribute) => {
    const raw = node?.getAttribute?.(attribute);
    if (!raw) return null;
    const { name, options } = __teloceParseTransition(raw);
    const transition = registry[name];
    return typeof transition === "function" ? transition(node, options) : null;
  };
  const playEnter = node => {
    if (!node || node.nodeType !== 1) return;
    const attribute = node.hasAttribute("data-teloce-in")
      ? "data-teloce-in"
      : node.hasAttribute("data-teloce-transition") ? "data-teloce-transition" : null;
    if (attribute) run(node, attribute);
    node.querySelectorAll?.("[data-teloce-in], [data-teloce-transition]").forEach(child => {
      run(child, child.hasAttribute("data-teloce-in") ? "data-teloce-in" : "data-teloce-transition");
    });
  };
  const playExit = node => {
    if (!node || node.nodeType !== 1 || !node.isConnected) return;
    const attribute = node.hasAttribute("data-teloce-out")
      ? "data-teloce-out"
      : node.hasAttribute("data-teloce-transition") ? "data-teloce-transition" : null;
    if (!attribute || !node.parentNode) return;
    const ghost = node.cloneNode(true);
    node.parentNode.insertBefore(ghost, node.nextSibling);
    const animation = run(ghost, attribute);
    if (animation?.finished?.then) animation.finished.then(() => ghost.remove()).catch(() => ghost.remove());
    else ghost.remove();
  };
  return { playEnter, playExit };
};

const __teloceLazy = loader => {
  if (typeof loader !== "function") throw new TypeError("Teloce lazy loader must be a function");
  let loading = null;
  let loaded = null;
  let active = null;
  let target = null;
  let props = {};
  let mounted = false;
  let generation = 0;

  const resolve = module => module?.default ?? module;
  const load = () => {
    if (!loading) loading = Promise.resolve().then(loader).then(resolve).then(component => {
      loaded = component;
      return component;
    });
    return loading;
  };

  return {
    mount(nextTarget, nextProps = {}) {
      target = typeof nextTarget === "string" ? document.querySelector(nextTarget) : nextTarget;
      if (!target) throw new Error("Teloce mount target was not found");
      props = nextProps;
      mounted = true;
      const currentGeneration = ++generation;
      target.setAttribute("data-teloce-loading", "true");
      const instance = {
        updateProps(next = {}) {
          props = next;
          active?.updateProps?.(next);
        },
        unmount() {
          mounted = false;
          generation += 1;
          active?.unmount?.();
          active = null;
          if (target) {
            target.removeAttribute("data-teloce-loading");
            target.replaceChildren();
          }
          target = null;
        },
      };
      load().then(component => {
        if (!mounted || currentGeneration !== generation || !target) return;
        target.removeAttribute("data-teloce-loading");
        if (component?.mount) active = component.mount(target, props);
      }).catch(error => {
        if (mounted && currentGeneration === generation && target) {
          target.removeAttribute("data-teloce-loading");
          target.dispatchEvent?.(new CustomEvent("teloce:lazy-error", { detail: error }));
        }
      });
      return instance;
    },
    updateProps(next = {}) {
      props = next;
      active?.updateProps?.(next);
    },
    unmount() {
      mounted = false;
      generation += 1;
      active?.unmount?.();
      active = null;
      target?.replaceChildren();
      target = null;
    },
  };
};

const __teloceCreateCompiledComponent = (definition, options = {}) => {
  const template = String(options.template ?? "");
  const components = options.components || {};
  const filters = options.filters || {};
  const style = String(options.style ?? "");
  const styleId = String(options.styleId ?? definition?.name ?? "component");
  const styleClasses = options.styleClasses || {};
  const dev = Boolean(options.dev);
  const moduleUrl = String(options.moduleUrl ?? "");
  const nativeEvents = new Set([
    "click", "input", "submit", "change", "keyup", "keydown", "focus", "blur",
    "mouseenter", "mouseleave", "mousedown", "mouseup", "pointerdown", "pointerup",
  ]);

  const evaluate = (expression, scope) => {
    try {
      const parts = String(expression ?? "").split(/\s+\|\s+/);
      let value = __safeEvaluate(parts.shift(), scope || {});
      for (const filterExpression of parts) {
        const match = filterExpression.match(/^([\w$]+)(?:\((.*)\)|(?::(.*)))?$/);
        const argumentsSource = match?.[2] ?? match?.[3];
        const filter = match && filters[match[1]];
        if (typeof filter === "function") {
          value = filter(value, ...(argumentsSource
            ? argumentsSource.split(",").map(argument => __safeEvaluate(argument, scope || {}))
            : []));
        }
      }
      return value;
    } catch (error) {
      if (dev) console.error("Teloce expression error:", expression, error);
      return "";
    }
  };

  const mapClass = value => {
    const map = token => styleClasses[token] || token;
    if (Array.isArray(value)) return value.map(map).join(" ");
    if (value && typeof value === "object") return Object.keys(value).filter(key => value[key]).map(map).join(" ");
    if (typeof value === "string") return value.split(/\s+/).filter(Boolean).map(map).join(" ");
    return value;
  };

  const isDangerousUrl = value => /^(?:javascript|vbscript|data|file):/.test(
    String(value ?? "").replace(/[\t\n\r\0]/g, "").trim().toLowerCase()
  );
  const sanitizeHtml = value => {
    const node = document.createElement("template");
    node.innerHTML = String(value ?? "");
    node.content.querySelectorAll("script,iframe,object,embed,link,meta,base").forEach(child => child.remove());
    node.content.querySelectorAll("*").forEach(child => {
      for (const attribute of Array.from(child.attributes)) {
        const name = attribute.name.toLowerCase();
        if (name.startsWith("on") || ((name === "href" || name === "src" || name === "action" || name === "formaction") && isDangerousUrl(attribute.value))) {
          child.removeAttribute(attribute.name);
        }
      }
    });
    return node.innerHTML || node.content?.firstChild?.outerHTML || "";
  };

  const applyBinding = (element, name, value) => {
    if (name === "key") return;
    if (name === "class") {
      const staticClass = element.getAttribute("data-teloce-static-class") ?? element.__teloceStaticClass ?? element.className ?? "";
      element.__teloceStaticClass = staticClass;
      element.className = [staticClass, String(mapClass(value) ?? "").trim()].filter(Boolean).join(" ");
    } else if (name === "style" && value && typeof value === "object") {
      const previous = element.__teloceDynamicStyles || new Set();
      for (const key of previous) if (!(key in value)) element.style[key] = "";
      for (const [key, item] of Object.entries(value)) element.style[key] = item ?? "";
      element.__teloceDynamicStyles = new Set(Object.keys(value));
    } else if (name === "show" || name === "hide") {
      element.hidden = name === "show" ? !Boolean(value) : Boolean(value);
    } else if (name === "html") {
      element.innerHTML = sanitizeHtml(value);
    } else if (name === "text") {
      element.textContent = value == null ? "" : String(value);
    } else if (["disabled", "checked", "selected", "readonly", "required", "multiple"].includes(name)) {
      element.toggleAttribute(name, Boolean(value));
    } else if (["href", "src", "action", "formaction"].includes(name) && isDangerousUrl(value)) {
      element.removeAttribute(name);
    } else if (value === false || value == null) {
      element.removeAttribute(name);
    } else {
      element.setAttribute(name, String(value));
    }
  };

  const resolveIfBlocks = (source, scope) => {
    let result = "";
    let cursor = 0;
    while (cursor < source.length) {
      const match = /<if\s+(?:condition|test)="/.exec(source.slice(cursor));
      if (!match) {
        result += source.slice(cursor);
        break;
      }
      const start = cursor + match.index;
      result += source.slice(cursor, start);
      const conditionStart = start + match[0].length;
      const conditionEnd = source.indexOf('"', conditionStart);
      const openingEnd = conditionEnd < 0 ? -1 : source.indexOf(">", conditionEnd) + 1;
      if (conditionEnd < 0 || openingEnd <= conditionEnd) {
        result += source.slice(start);
        break;
      }
      let depth = 1;
      let position = openingEnd;
      let elseStart = -1;
      let elseEnd = -1;
      let closeStart = -1;
      while (depth > 0) {
        const nextOpen = source.indexOf("<if ", position);
        const nextClose = source.indexOf("</if>", position);
        const nextElse = depth === 1 && elseStart < 0 ? source.indexOf("<else>", position) : -1;
        const candidates = [nextOpen, nextClose, nextElse].filter(value => value >= 0);
        if (!candidates.length) break;
        const next = Math.min(...candidates);
        if (next === nextOpen) {
          depth += 1;
          position = next + 4;
        } else if (next === nextElse) {
          elseStart = next;
          elseEnd = next + 6;
          position = elseEnd;
        } else {
          depth -= 1;
          position = next + 5;
          if (depth === 0) closeStart = next;
        }
      }
      if (depth !== 0 || closeStart < 0) {
        result += source.slice(start);
        break;
      }
      const yesEnd = elseStart >= 0 ? elseStart : closeStart;
      const yes = source.slice(openingEnd, yesEnd);
      const no = elseStart >= 0 ? source.slice(elseEnd, closeStart) : "";
      result += resolveIfBlocks(evaluate(source.slice(conditionStart, conditionEnd), scope) ? yes : no, scope);
      cursor = position;
    }
    return result;
  };

  const renderForBlocks = (source, scope, loopScopes) => {
    let result = source;
    let start = result.indexOf("<for ");
    while (start >= 0) {
      const openingEnd = result.indexOf(">", start);
      if (openingEnd < 0) break;
      let depth = 1;
      let position = openingEnd + 1;
      let closeStart = -1;
      while (depth > 0) {
        const nextOpen = result.indexOf("<for ", position);
        const nextClose = result.indexOf("</for>", position);
        if (nextClose < 0) break;
        if (nextOpen >= 0 && nextOpen < nextClose) {
          depth += 1;
          position = nextOpen + 5;
        } else {
          depth -= 1;
          closeStart = nextClose;
          position = nextClose + 6;
        }
      }
      if (depth !== 0 || closeStart < 0) break;
      const opening = result.slice(start, openingEnd + 1);
      const item = opening.match(/\bitem="([^"]+)"/)?.[1];
      const collection = opening.match(/\b(?:in|collection)="([^"]+)"/)?.[1];
      if (!item || !collection) break;
      const body = result.slice(openingEnd + 1, closeStart);
      const rawValues = evaluate(collection, scope);
      const values = Array.isArray(rawValues) ? rawValues : rawValues && typeof rawValues === "object" ? Object.values(rawValues) : [];
      const rendered = values.map((value, index) => {
        const loopScope = { ...scope, [item]: value, index };
        const scopeId = String(loopScopes.size);
        loopScopes.set(scopeId, loopScope);
        let content = renderTemplate(body, loopScope, loopScopes);
        content = content.replace(/<([A-Za-z][\w:-]*)(?=[\s>])/, match => match.includes("data-teloce-loop-scope")
          ? match
          : `${match} data-teloce-loop-scope="${scopeId}"`);
        return content;
      }).join("");
      result = result.slice(0, start) + rendered + result.slice(position);
      start = result.indexOf("<for ", start + rendered.length);
    }
    return result;
  };

  const renderTemplate = (source, scope, loopScopes = new Map()) => {
    let output = String(source ?? "");
    output = output.replace(/<slot\b([^>]*)>\s*<\/slot>/g, (_, attributes) => {
      const name = attributes.match(/(?:^|\s)name="([^"]*)"/)?.[1] || "default";
      return scope.__slots?.[name] || "";
    });
    output = renderForBlocks(output, scope, loopScopes);
    output = resolveIfBlocks(output, scope);
    output = output.replace(/<([A-Za-z][\w:-]*)([^>]*?)v-if="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>/g,
      (_, tag, before, condition, after, body) => evaluate(condition, scope) ? `<${tag}${before}${after}>${body}</${tag}>` : "");
    output = output.replace(/{{\s*([^{}]+?)\s*}}/g, (_, expression) => __teloceEscapeHtml(evaluate(expression, scope)));
    output = output.replace(/data-teloce-bind-([\w-]+)="([^"]*)"/g, (_, name, expression) => {
      const value = evaluate(__teloceDecodeAttribute(expression), scope);
      const serialized = __teloceEscapeAttribute(JSON.stringify(value === undefined ? null : value));
      return name === "key" ? `data-teloce-key="${serialized}"` : `data-teloce-resolved-${name}="${serialized}"`;
    });
    output = output.replace(/v-model="([^"]*)"/g, (_, expression) => `data-teloce-model="${__teloceEscapeAttribute(expression)}"`);
    output = output.replace(/v-on:([\w.-]+)="([^"]*)"/g, (_, name, expression) => `data-teloce-event-${name}="${__teloceEscapeAttribute(expression)}"`);
    output = output.replace(/@([\w.-]+)="([^"]*)"/g, (_, name, expression) => `data-teloce-event-${name}="${__teloceEscapeAttribute(expression)}"`);
    return output;
  };

  const readProps = (element, parentState) => {
    const slots = { default: "" };
    for (const child of Array.from(element.childNodes || [])) {
      if (child.nodeType === 1 && child.hasAttribute("slot")) {
        const name = child.getAttribute("slot") || "default";
        slots[name] = (slots[name] || "") + child.outerHTML;
      } else {
        slots.default += child.outerHTML ?? child.textContent ?? "";
      }
    }
    const props = { __slots: slots };
    for (const attribute of Array.from(element.attributes || [])) {
      const name = attribute.name;
      if (name.startsWith("data-teloce-event-") || name === "data-teloce-loop-scope" || name === "data-teloce-key") continue;
      if (name === "data-teloce-is") {
        props.__dynamic = evaluate(attribute.value, parentState);
      } else if (name.startsWith("data-teloce-resolved-")) {
        const propName = name.slice("data-teloce-resolved-".length);
        try { props[propName] = JSON.parse(attribute.value); } catch (_) { props[propName] = attribute.value; }
      } else if (name.startsWith("data-teloce-bind-")) {
        const propName = name.slice("data-teloce-bind-".length);
        props[propName] = evaluate(__teloceDecodeAttribute(attribute.value), parentState);
      } else if (!name.startsWith("data-")) {
        props[name] = attribute.value;
      }
    }
    return props;
  };

  const cleanupElement = element => {
    if (element.__teloceHandlers) {
      for (const record of element.__teloceHandlers.values()) element.removeEventListener(record.actualEvent, record.listener, record.options);
      element.__teloceHandlers.clear();
    }
    if (element.__teloceModelListener) {
      element.removeEventListener(element.__teloceModelListener.eventName, element.__teloceModelListener.listener);
      element.__teloceModelListener = null;
    }
    for (const record of element.__teloceDirectives?.values?.() || []) {
      try { record.cleanup?.(); record.directive?.destroy?.(element, record.context); } catch (_) {}
    }
    element.__teloceDirectives?.clear?.();
  };

  let target = null;
  let mounted = false;
  let destroyed = false;
  let rendering = false;
  let suppressUpdates = false;
  let queued = false;
  let loopScopes = new Map();
  let state;
  let previousWatchValues = {};

  const handleError = (error, phase) => {
    if (dev) console.error(`Teloce ${phase} error:`, error);
    try { options.onError?.(error, phase); } catch (_) {}
  };
  const requestUpdate = () => {
    if (destroyed || suppressUpdates || queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      if (!destroyed) update();
    });
  };

  const rawData = typeof definition?.data === "function" ? definition.data() || {} : {};
  const propDefinitions = definition?.props || {};
  const normalizeProps = input => {
    const output = { ...(input || {}) };
    for (const [name, descriptorValue] of Object.entries(propDefinitions)) {
      const descriptor = typeof descriptorValue === "string" ? { type: descriptorValue } : descriptorValue || {};
      if (output[name] === undefined && descriptor.type === "Boolean") output[name] = false;
      if (output[name] === undefined && (descriptor.defaultFactory || descriptor.default !== undefined)) {
        try {
          output[name] = typeof descriptor.defaultFactory === "function"
            ? descriptor.defaultFactory()
            : typeof descriptor.default === "function" ? descriptor.default() : descriptor.default;
        } catch (error) { handleError(error, `prop:${name}`); }
      }
      if (dev && descriptor.required && output[name] === undefined) console.warn(`Missing required prop: ${name}`);
      if (descriptor.validator && output[name] !== undefined) {
        try { if (dev && !descriptor.validator(output[name])) console.warn(`Invalid prop value for ${name}`); }
        catch (error) { handleError(error, `prop:${name}`); }
      }
    }
    return output;
  };

  state = __createReactive({ ...rawData, ...normalizeProps(options.props || {}) }, requestUpdate);
  suppressUpdates = true;
  for (const [name, method] of Object.entries(definition?.methods || {})) {
    if (typeof method === "function") state[name] = (...args) => method.apply(state, args);
  }
  for (const [name, computed] of Object.entries(definition?.computed || {})) {
    if (typeof computed === "function") {
      Object.defineProperty(state, name, { configurable: true, enumerable: true, get: () => computed.call(state) });
    }
  }
  state.$emit = (name, detail) => target?.dispatchEvent?.(new CustomEvent(`teloce:${name}`, { detail, bubbles: true }));
  suppressUpdates = false;

  const initialData = () => ({ ...rawData, ...normalizeProps({}) });
  const watchValue = name => String(name).split(".").reduce((value, key) => value == null ? undefined : value[key], state);
  const callHook = (name, ...args) => {
    const hook = definition?.[name];
    if (typeof hook !== "function") return;
    try {
      const result = hook.apply(state, args);
      if (result?.then) result.catch(error => handleError(error, name));
      return result;
    } catch (error) { handleError(error, name); }
  };

  const bindEventsAndDirectives = element => {
    for (const attribute of Array.from(element.attributes || [])) {
      if (attribute.name.startsWith("data-teloce-event-")) {
        const eventKey = attribute.name.slice("data-teloce-event-".length);
        const [eventName, ...modifiers] = eventKey.split(".");
        const actualEvent = nativeEvents.has(eventName) ? eventName : `teloce:${eventName}`;
        const signature = `${eventKey}=${attribute.value}`;
        if (!element.__teloceHandlers) element.__teloceHandlers = new Map();
        const previous = element.__teloceHandlers.get(attribute.name);
        if (!previous || previous.signature !== signature) {
          if (previous) element.removeEventListener(previous.actualEvent, previous.listener, previous.options);
          const listener = event => {
            if (modifiers.includes("self") && event.target !== element) return;
            if (modifiers.includes("enter") && event.key !== "Enter") return;
            if (modifiers.includes("esc") && event.key !== "Escape") return;
            if (modifiers.includes("ctrl") && !event.ctrlKey) return;
            if (modifiers.includes("shift") && !event.shiftKey) return;
            if (modifiers.includes("alt") && !event.altKey) return;
            if (modifiers.includes("meta") && !event.metaKey) return;
            if (modifiers.includes("right") && event.button !== 2) return;
            if (modifiers.includes("middle") && event.button !== 1) return;
            if (modifiers.includes("left") && event.button !== 0) return;
            if (modifiers.includes("prevent")) event.preventDefault();
            if (modifiers.includes("stop")) event.stopPropagation();
            const scopeElement = element.closest?.("[data-teloce-loop-scope]");
            const loopScope = scopeElement ? loopScopes.get(scopeElement.getAttribute("data-teloce-loop-scope")) : null;
            // Copy state keys into the expression scope because the safe
            // evaluator intentionally checks own properties rather than
            // falling through arbitrary Proxy getters. Writes still forward
            // to the live reactive state through the Proxy below.
            const values = { ...state, ...(loopScope || {}), event, $event: event };
            const eventScope = new Proxy(values, {
              get(object, key, receiver) { return Reflect.has(object, key) ? Reflect.get(object, key, receiver) : state[key]; },
              set(object, key, value, receiver) {
                if (Reflect.has(state, key)) { state[key] = value; return true; }
                return Reflect.set(object, key, value, receiver);
              },
            });
            try {
              const expression = attribute.value;
              const handler = state[expression.trim()];
              const result = typeof handler === "function"
                ? handler(event?.detail ?? event)
                : __runEventExpression(expression, eventScope);
              if (result?.then) result.catch(error => handleError(error, `event:${eventName}`));
            } catch (error) { handleError(error, `event:${eventName}`); }
          };
          const eventOptions = { once: modifiers.includes("once"), capture: modifiers.includes("capture"), passive: modifiers.includes("passive") };
          element.__teloceHandlers.set(attribute.name, { signature, actualEvent, listener, options: eventOptions });
          element.addEventListener(actualEvent, listener, eventOptions);
        }
      }

      if (attribute.name === "data-teloce-model" && !element.__teloceModelListener) {
        const expression = attribute.value;
        const eventName = element.type === "checkbox" || element.tagName === "SELECT" ? "change" : "input";
        const listener = () => {
          const scopeElement = element.closest?.("[data-teloce-loop-scope]");
          const loopScope = scopeElement ? loopScopes.get(scopeElement.getAttribute("data-teloce-loop-scope")) : null;
          const values = new Proxy({ ...state, ...(loopScope || {}) }, {
            get(object, key, receiver) { return Reflect.has(object, key) ? Reflect.get(object, key, receiver) : state[key]; },
            set(object, key, value) { if (Reflect.has(state, key)) state[key] = value; else object[key] = value; return true; },
          });
          __setSafePath(expression, element.type === "checkbox" ? element.checked : element.value, values);
        };
        element.__teloceModelListener = { eventName, listener };
        element.addEventListener(eventName, listener);
      }

      if (attribute.name.startsWith("data-teloce-resolved-")) {
        const name = attribute.name.slice("data-teloce-resolved-".length);
        let value;
        try { value = JSON.parse(attribute.value); } catch (_) { value = attribute.value; }
        applyBinding(element, name, value);
      }

      const directiveMatch = attribute.name.match(/^v-([\w-]+)$/);
      const directive = directiveMatch && globalThis.teloce?.directives?.[directiveMatch[1]];
      if (directive?.render) {
        const name = directiveMatch[1];
        const signature = `${name}=${attribute.value}`;
        if (!element.__teloceDirectives) element.__teloceDirectives = new Map();
        const previous = element.__teloceDirectives.get(name);
        if (!previous || previous.signature !== signature) {
          try { previous?.cleanup?.(); previous?.directive?.destroy?.(element, previous.context); } catch (_) {}
          const context = { name, expression: attribute.value, value: evaluate(attribute.value, state), state, modifiers: [] };
          let cleanup;
          try { cleanup = directive.render(element, context); } catch (error) { handleError(error, `directive:${name}`); }
          element.__teloceDirectives.set(name, { signature, directive, context, cleanup: typeof cleanup === "function" ? cleanup : null });
        }
      }
    }
  };

  const mountChildren = () => {
    const lookup = new Map(Object.entries(components).map(([name, value]) => [name.toLowerCase(), value]));
    const newlyMounted = new Set();
    let found = true;
    while (found) {
      found = false;
      for (const element of Array.from(target.querySelectorAll("*"))) {
        const child = lookup.get(element.tagName.toLowerCase());
        if (!child || element.__teloceMounted || typeof child.mount !== "function") continue;
        element.__teloceMounted = true;
        element.__teloceInstance = child.mount(element, readProps(element, state));
        newlyMounted.add(element);
        found = true;
        break;
      }
    }
    for (const element of Array.from(target.querySelectorAll("*"))) {
      if (lookup.has(element.tagName.toLowerCase()) && !newlyMounted.has(element) && element.__teloceInstance?.updateProps) {
        const source = element.__telocePendingPropsSource || element;
        element.__teloceInstance.updateProps(readProps(source, state));
        element.__telocePendingPropsSource = undefined;
      }
    }
    target.querySelectorAll("teloce-dynamic").forEach(element => {
      const name = evaluate(element.getAttribute("data-teloce-is") || "", state);
      const child = lookup.get(String(name).toLowerCase());
      if (!element.__teloceMounted && child?.mount) {
        element.__teloceMounted = true;
        element.__teloceInstance = child.mount(element, readProps(element, state));
      } else if (element.__teloceInstance?.updateProps) {
        element.__teloceInstance.updateProps(readProps(element, state));
      }
    });
  };

  const update = () => {
    if (destroyed || !target || rendering) return;
    const wasMounted = mounted;
    rendering = true;
    if (wasMounted) callHook("beforeUpdate");
    try {
      loopScopes = new Map();
      const transitions = __teloceTransitionHooks(definition);
      __patch(target, renderTemplate(template, state, loopScopes), {
        ...transitions,
        onDispose: cleanupElement,
      });
      target.querySelectorAll("*").forEach(bindEventsAndDirectives);
      mountChildren();
    } finally {
      rendering = false;
    }
    if (!wasMounted) {
      callHook("beforeMount");
      mounted = true;
      callHook("mounted");
      callHook("activated");
    } else {
      callHook("updated");
    }
    for (const [name, handler] of Object.entries(definition?.watch || {})) {
      const value = watchValue(name);
      if (!Object.is(previousWatchValues[name], value)) {
        try {
          const result = handler.call(state, value, previousWatchValues[name]);
          if (result?.then) result.catch(error => handleError(error, `watch:${name}`));
        } catch (error) { handleError(error, `watch:${name}`); }
        previousWatchValues[name] = value;
      }
    }
  };

  const normalizedProps = normalizeProps(options.props || {});
  suppressUpdates = true;
  for (const [name, value] of Object.entries(normalizedProps)) state[name] = value;
  previousWatchValues = Object.fromEntries(Object.keys(definition?.watch || {}).map(name => [name, watchValue(name)]));
  callHook("beforeCreate");
  callHook("created");
  suppressUpdates = false;

  const hmrRegistry = globalThis.__teloce_hmr_instances ||= new Map();
  const hmrKey = moduleUrl || definition?.name || "component";
  const hmrRecord = {
    target: null,
    state,
    reload: async () => {
      if (!target || destroyed || !moduleUrl) return;
      const oldTarget = target;
      const snapshot = {};
      for (const [key, value] of Object.entries(state)) if (!key.startsWith("$") && typeof value !== "function") snapshot[key] = value;
      instance.unmount();
      const fresh = await import(`${moduleUrl.split("?")[0]}?teloce_hmr=${Date.now()}`);
      return fresh.mount(oldTarget, snapshot);
    },
  };
  if (!hmrRegistry.has(hmrKey)) hmrRegistry.set(hmrKey, new Set());
  hmrRegistry.get(hmrKey).add(hmrRecord);
  if (!globalThis.__teloce_hmr_reload) globalThis.__teloce_hmr_reload = async () => {
    const records = [...hmrRegistry.values()].flatMap(set => [...set]);
    for (const record of records) await record.reload();
  };

  const instance = {
    state,
    update,
    updateProps(nextProps = {}) {
      const normalized = normalizeProps(nextProps);
      suppressUpdates = true;
      let changed = false;
      try {
        for (const [key, value] of Object.entries(normalized)) if (!Object.is(state[key], value)) { state[key] = value; changed = true; }
        for (const key of Object.keys(propDefinitions)) if (!(key in normalized) && state[key] !== undefined) { state[key] = undefined; changed = true; }
      } finally { suppressUpdates = false; }
      if (changed) update();
      return instance;
    },
    mount(nextTarget, props = {}) {
      target = typeof nextTarget === "string" ? document.querySelector(nextTarget) : nextTarget;
      if (!target) throw new Error("Teloce mount target was not found");
      if (mounted) instance.unmount();
      destroyed = false;
      hmrRecord.target = target;
      if (!hmrRegistry.has(hmrKey)) hmrRegistry.set(hmrKey, new Set());
      hmrRegistry.get(hmrKey).add(hmrRecord);
      if (props && Object.keys(props).length) instance.updateProps(props);
      update();
      return instance;
    },
    unmount() {
      if (!target || destroyed) return instance;
      callHook("deactivated");
      callHook("beforeUnmount");
      const nodes = Array.from(target.querySelectorAll("*")).reverse();
      for (const element of nodes) {
        element.__teloceInstance?.unmount?.();
        cleanupElement(element);
        element.__teloceMounted = false;
        element.__teloceInstance = undefined;
      }
      target.replaceChildren();
      mounted = false;
      destroyed = true;
      hmrRegistry.get(hmrKey)?.delete(hmrRecord);
      if (hmrRegistry.get(hmrKey)?.size === 0) hmrRegistry.delete(hmrKey);
      hmrRecord.target = null;
      callHook("unmounted");
      return instance;
    },
  };

  instance.__teloceStyle = style;
  if (style && typeof document !== "undefined" && !document.querySelector(`style[data-teloce-style="${styleId}"]`)) {
    const styleElement = document.createElement("style");
    styleElement.setAttribute("data-teloce-style", styleId);
    styleElement.textContent = style;
    (document.head || document.documentElement).appendChild(styleElement);
  }
  return instance;
};

export { __teloceCreateCompiledComponent, __teloceLazy };

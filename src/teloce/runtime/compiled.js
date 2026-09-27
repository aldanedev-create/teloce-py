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
  .replace(/&#x27;/gi, "'")
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

// Small, dependency-free browser primitives used by generated components.
// They live in the shared runtime so a project does not ship a copy per
// component.
const __teloceSplitArguments = source => {
  const result = [];
  let start = 0;
  let depth = 0;
  let quote = "";
  let escaped = false;
  const text = String(source ?? "");
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === quote) quote = "";
    } else if (["'", '"', "`"] .includes(character)) quote = character;
    else if ("([{".includes(character)) depth += 1;
    else if (")]}`".includes(character)) depth = Math.max(0, depth - 1);
    else if (character === "," && depth === 0) {
      result.push(text.slice(start, index).trim());
      start = index + 1;
    }
  }
  if (text.slice(start).trim()) result.push(text.slice(start).trim());
  return result;
};

const __teloceCreateCompiledComponent = (definition, options = {}) => {
  const template = String(options.template ?? "");
  const camelizeProp = name => String(name).replace(/-([a-z])/g, (_, character) => character.toUpperCase());
  const components = options.components || {};
  const filters = options.filters || {};
  const actions = options.actions || definition?.actions || {};
  const tableFactory = options.table || definition?.table;
  const style = String(options.style ?? "");
  const styleId = String(options.styleId ?? definition?.name ?? "component");
  const styleClasses = options.styleClasses || {};
  const dev = Boolean(options.dev);
  const moduleUrl = String(options.moduleUrl ?? "");
  const directPlan = options.directPlan || {};
  // Structural templates continue through the existing keyed reconciler.
  // Simple templates use the targeted path; both paths share lifecycle and
  // cleanup behavior and are selected from one generated plan.
  const directEnabled = Boolean(options.direct && directPlan.enabled && !directPlan.fallback);
  const directBindings = Array.isArray(directPlan.bindings) ? directPlan.bindings : [];
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
            ? __teloceSplitArguments(argumentsSource).map(argument => __safeEvaluate(argument, scope || {}))
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
    // Bindings can materialize real DOM attributes (for example `disabled`)
    // after reconciliation has cloned the declarative template. Track those
    // mutations as managed too, otherwise a later v-if branch can reuse the
    // node and leave a stale boolean attribute behind.
    element.__teloceManagedAttributes ||= new Set();
    element.__teloceManagedAttributes.add(name);
    if (name === "attrs") {
      const previous = element.__teloceForwardedAttrs || new Set();
      const next = value && typeof value === "object" ? value : {};
      const applied = new Set();
      for (const attribute of previous) if (!(attribute in next)) {
        if (attribute === "class" && element.__teloceStaticClass) element.setAttribute("class", element.__teloceStaticClass);
        else element.removeAttribute(attribute);
      }
      for (const [attribute, nextValue] of Object.entries(next)) {
        // Component internals must not leak Teloce bookkeeping attributes.
        if (attribute.startsWith("data-teloce-") || attribute === "children") continue;
        if (attribute === "class") {
          const staticClass = element.getAttribute("data-teloce-static-class") ?? element.__teloceStaticClass ?? element.className ?? "";
          element.__teloceStaticClass = staticClass;
          const merged = [staticClass, mapClass(nextValue)].filter(Boolean).join(" ");
          element.setAttribute("class", merged);
        } else if (attribute === "style" && nextValue && typeof nextValue === "object") {
          for (const [property, propertyValue] of Object.entries(nextValue)) element.style[property] = propertyValue ?? "";
        } else if (nextValue === false || nextValue == null) element.removeAttribute(attribute);
        else if ((attribute === "href" || attribute === "src" || attribute === "action" || attribute === "formaction") && isDangerousUrl(nextValue)) element.removeAttribute(attribute);
        else element.setAttribute(attribute, String(nextValue));
        if (nextValue !== false && nextValue != null) applied.add(attribute);
      }
      element.__teloceForwardedAttrs = applied;
    } else if (name === "class") {
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

  // Virtual loops are opt-in. Normal ``v-for`` remains the compatibility
  // path; this renderer only materializes the visible window and keeps the
  // full collection out of the DOM.
  const renderVirtualForBlocks = (source, scope) => {
    let result = String(source ?? "");
    let start = result.indexOf("<virtual-for ");
    while (start >= 0) {
      const openingEnd = result.indexOf(">", start);
      if (openingEnd < 0) break;
      const opening = result.slice(start, openingEnd + 1);
      const closeStart = result.indexOf("</virtual-for>", openingEnd + 1);
      if (closeStart < 0) break;
      const body = result.slice(openingEnd + 1, closeStart);
      const attr = name => opening.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? "";
      const item = attr("item") || "item";
      const collection = attr("in") || attr("collection");
      const key = attr("key") || "index";
      const itemHeight = attr("item-height") || "40";
      const overscan = attr("overscan") || "5";
      const minHeight = attr("min-height") || "";
      const bodySource = encodeURIComponent(body);
      const wrapper = `<div class="teloce-virtual-list" data-teloce-virtual-for="true" data-teloce-virtual-item="${__teloceEscapeAttribute(item)}" data-teloce-virtual-collection="${__teloceEscapeAttribute(collection)}" data-teloce-virtual-key="${__teloceEscapeAttribute(key)}" data-teloce-virtual-item-height="${__teloceEscapeAttribute(itemHeight)}" data-teloce-virtual-overscan="${__teloceEscapeAttribute(overscan)}" data-teloce-virtual-min-height="${__teloceEscapeAttribute(minHeight)}" data-teloce-virtual-body="${__teloceEscapeAttribute(bodySource)}"><div class="teloce-virtual-spacer"></div><div class="teloce-virtual-content"></div></div>`;
      result = result.slice(0, start) + wrapper + result.slice(closeStart + 14);
      start = result.indexOf("<virtual-for ", start + wrapper.length);
    }
    return result;
  };

  const renderTemplate = (source, scope, loopScopes = new Map()) => {
    let output = String(source ?? "");
    output = output.replace(/<slot\b([^>]*)>\s*<\/slot>/g, (_, attributes) => {
      const name = attributes.match(/(?:^|\s)name="([^"]*)"/)?.[1] || "default";
      return scope.__slots?.[name] || "";
    });
    output = renderVirtualForBlocks(output, scope);
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
    output = output.replace(/\bv-memo="([^"]*)"/g, (_, expression) => {
      const value = evaluate(__teloceDecodeAttribute(expression), scope);
      return `data-teloce-memo="${__teloceEscapeAttribute(JSON.stringify(value === undefined ? null : value))}"`;
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
      } else if (child.nodeType === 8) {
        // Preserve direct-update comment anchors when a parent passes a slot
        // into a child component. Reading only textContent would turn the
        // marker into visible text and disconnect the parent's text binding.
        slots.default += `<!--${child.nodeValue || ""}-->`;
      } else {
        slots.default += child.outerHTML ?? child.textContent ?? "";
      }
    }
    const props = { __slots: slots };
    const forwarded = {};
    const declaredNames = new Set(Object.keys(definition?.props || {}).map(camelizeProp));
    const attributes = Array.from(element.attributes || []);
    // `applyBinding` mirrors dynamic component props onto a normal HTML
    // attribute for compatibility and inspection. That mirror is a string
    // representation (for example, `[object Object]`) and must never
    // override the typed value carried by data-teloce-resolved-*.
    const resolvedPropNames = new Set(
      attributes
        .filter(attribute => attribute.name.startsWith("data-teloce-resolved-"))
        .map(attribute => camelizeProp(attribute.name.slice("data-teloce-resolved-".length)))
    );
    for (const attribute of attributes) {
      const name = attribute.name;
      if (name.startsWith("data-teloce-event-") || name === "data-teloce-loop-scope" || name === "data-teloce-key") continue;
      if (name === "data-teloce-is") {
        props.__dynamic = evaluate(attribute.value, parentState);
      } else if (name.startsWith("data-teloce-resolved-")) {
        const propName = camelizeProp(name.slice("data-teloce-resolved-".length));
        try { props[propName] = JSON.parse(attribute.value); } catch (_) { props[propName] = attribute.value; }
      } else if (name.startsWith("data-teloce-bind-")) {
        const propName = camelizeProp(name.slice("data-teloce-bind-".length));
        const value = evaluate(__teloceDecodeAttribute(attribute.value), parentState);
        props[propName] = value;
        if (propName !== "attrs") forwarded[propName] = value;
      } else if (!name.startsWith("data-") && !resolvedPropNames.has(name)) {
        props[camelizeProp(name)] = attribute.value;
        if (!declaredNames.has(camelizeProp(name))) forwarded[name] = attribute.value;
      }
    }
    // Preserve semantic parent attributes for an explicit ``$attrs`` bind.
    // Teloce bookkeeping attributes and declared dynamic prop mirrors are
    // excluded from the forwarded set.
    for (const attribute of attributes) {
      const name = attribute.name;
      if (name === "class" || name === "id" || name.startsWith("aria-") || name.startsWith("data-")) {
        if (!name.startsWith("data-teloce-") && !declaredPropNames.has(camelizeProp(name))) forwarded[name] = attribute.value;
      }
    }
    props.$attrs = forwarded;
    props.__attrs = forwarded;
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
    for (const record of element.__teloceActions?.values?.() || []) {
      try { record.destroy?.(); } catch (error) { handleError(error, "action:destroy"); }
    }
    element.__teloceActions?.clear?.();
    try { element.__teloceScrollyCleanup?.(); } catch (_) {}
    element.__teloceScrollyCleanup = null;
    try { element.__teloceLiveCleanup?.(); } catch (_) {}
    element.__teloceLiveCleanup = null;
    try { element.__telocePollCleanup?.(); } catch (_) {}
    element.__telocePollCleanup = null;
    try { element.__teloceAnnotationCleanup?.(); } catch (_) {}
    element.__teloceAnnotationCleanup = null;
    try { element.__teloceVirtualCleanup?.(); } catch (_) {}
    element.__teloceVirtualCleanup = null;
    try { element.__teloceDataTable?.instance?.unmount?.(); } catch (error) { handleError(error, "data-table:destroy"); }
    element.__teloceDataTable = null;
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
  let pendingDependencies = new Set();
  let schedulerVersion = 0;

  const handleError = (error, phase) => {
    if (dev) console.error(`Teloce ${phase} error:`, error);
    try { options.onError?.(error, phase); } catch (_) {}
  };
  const requestUpdate = dependency => {
    if (destroyed || suppressUpdates) return;
    if (dependency != null) pendingDependencies.add(String(dependency).split(".")[0]);
    else pendingDependencies.add("*");
    if (queued) return;
    queued = true;
    const version = schedulerVersion;
    queueMicrotask(() => {
      queued = false;
      if (version !== schedulerVersion) return;
      const changed = pendingDependencies;
      pendingDependencies = new Set();
      if (!destroyed) update(changed);
    });
  };

  const rawData = typeof definition?.data === "function" ? definition.data() || {} : {};
  const propDefinitions = definition?.props || {};
  const queryState = definition?.queryState || {};
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
  const declaredPropNames = new Set(Object.keys(propDefinitions));
  const incomingAttrs = options.props?.$attrs || options.props?.__attrs || {};
  state.$attrs = Object.fromEntries(Object.entries(incomingAttrs).filter(([name]) => !declaredPropNames.has(camelizeProp(name)) && !name.startsWith("data-teloce-")));
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

  const parseQueryValue = (raw, definition) => {
    if (raw == null) return undefined;
    const type = typeof definition === "string" ? definition : definition?.type;
    if (type === "number") { const number = Number(raw); return Number.isFinite(number) ? number : undefined; }
    if (type === "boolean" || type === "Boolean") return raw === "1" || raw === "true";
    if (type === "json" || type === "array") { try { return JSON.parse(raw); } catch (_) { return undefined; } }
    return raw;
  };
  const queryKey = (name, config) => typeof config === "string" ? config : config?.key || name;
  const hydrateQueryState = () => {
    if (typeof window === "undefined" || !window.location?.search) return;
    const params = new URLSearchParams(window.location.search);
    suppressUpdates = true;
    try { for (const [name, config] of Object.entries(queryState)) { const value = parseQueryValue(params.get(queryKey(name, config)), config); if (value !== undefined) state[name] = value; } }
    finally { suppressUpdates = false; }
  };
  const syncQueryState = () => {
    if (typeof window === "undefined" || !window.history?.replaceState || !queryState || !Object.keys(queryState).length) return;
    const url = new URL(window.location.href);
    for (const [name, config] of Object.entries(queryState)) {
      const key = queryKey(name, config);
      const value = state[name];
      if (value == null || value === "" || (Array.isArray(value) && !value.length)) url.searchParams.delete(key);
      else url.searchParams.set(key, typeof value === "object" ? JSON.stringify(value) : String(value));
    }
    window.history.replaceState(window.history.state, "", url);
  };
  hydrateQueryState();
  const onPopState = () => { hydrateQueryState(); requestUpdate(); };
  let queryListenerActive = false;
  const registerQueryListener = () => {
    if (!queryListenerActive && typeof window !== "undefined" && Object.keys(queryState).length) { window.addEventListener("popstate", onPopState); queryListenerActive = true; }
  };

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

  const readActionParams = expression => expression && expression.trim()
    ? evaluate(__teloceDecodeAttribute(expression), state)
    : undefined;

  const renderVirtualList = element => {
    const signature = [
      element.getAttribute("data-teloce-virtual-collection"),
      element.getAttribute("data-teloce-virtual-key"),
      element.getAttribute("data-teloce-virtual-item-height"),
      element.getAttribute("data-teloce-virtual-overscan"),
      element.getAttribute("data-teloce-virtual-min-height"),
      element.getAttribute("data-teloce-virtual-body"),
    ].join("\u0000");
    if (element.__teloceVirtualRender && element.__teloceVirtualSignature === signature) {
      element.__teloceVirtualRender();
      return;
    }
    if (element.__teloceVirtualCleanup) element.__teloceVirtualCleanup();
    const content = element.querySelector(".teloce-virtual-content");
    const spacer = element.querySelector(".teloce-virtual-spacer");
    if (!content || !spacer) return;
    const bodySource = element.getAttribute("data-teloce-virtual-body") || "";
    const body = decodeURIComponent(bodySource);
    const itemName = element.getAttribute("data-teloce-virtual-item") || "item";
    const collectionExpression = element.getAttribute("data-teloce-virtual-collection") || "[]";
    const keyExpression = element.getAttribute("data-teloce-virtual-key") || "index";
    const rowHeightExpression = element.getAttribute("data-teloce-virtual-item-height") || "40";
    const overscanExpression = element.getAttribute("data-teloce-virtual-overscan") || "5";
    const minHeightExpression = element.getAttribute("data-teloce-virtual-min-height") || "";
    let scheduled = false;
    let virtualScopeIds = new Set();
    const renderVisible = () => {
      scheduled = false;
      // Virtual rows are replaced as the viewport moves. Clean their
      // framework listeners/actions before detaching them so document-level
      // integrations do not survive a scroll or reactive refresh.
      for (const scopeId of virtualScopeIds) loopScopes.delete(scopeId);
      virtualScopeIds = new Set();
      content.querySelectorAll("*").forEach(cleanupElement);
      const raw = evaluate(collectionExpression, state);
      const values = Array.isArray(raw) ? raw : raw && typeof raw === "object" ? Object.values(raw) : [];
      const rowHeight = Math.max(1, Number(evaluate(rowHeightExpression, state) || rowHeightExpression) || 40);
      const overscan = Math.max(0, Number(evaluate(overscanExpression, state) || overscanExpression) || 5);
      const minHeight = Number(evaluate(minHeightExpression, state) || minHeightExpression);
      if (Number.isFinite(minHeight) && minHeight >= 0) element.style.minHeight = `${minHeight}px`;
      const viewportHeight = element.clientHeight || 320;
      const first = Math.max(0, Math.floor(element.scrollTop / rowHeight) - overscan);
      const last = Math.min(values.length, Math.ceil((element.scrollTop + viewportHeight) / rowHeight) + overscan);
      spacer.style.height = `${values.length * rowHeight}px`;
      content.style.transform = `translateY(${first * rowHeight}px)`;
      const focusedKey = document.activeElement?.getAttribute?.("data-teloce-key");
      const fragment = document.createDocumentFragment();
      for (let index = first; index < last; index += 1) {
        const value = values[index];
        const loopScope = { ...state, [itemName]: value, index };
        const scopeId = String(loopScopes.size);
        loopScopes.set(scopeId, loopScope);
        virtualScopeIds.add(scopeId);
        let markup = renderTemplate(body, loopScope, loopScopes);
        const key = evaluate(keyExpression, loopScope);
        markup = markup.replace(/^(\s*<[A-Za-z][\w:-]*)(?=[\s>])/, `$1 data-teloce-key="${__teloceEscapeAttribute(String(key ?? index))}" data-teloce-loop-scope="${scopeId}"`);
        const rowTemplate = document.createElement("template");
        rowTemplate.innerHTML = markup;
        fragment.append(...Array.from(rowTemplate.content.childNodes));
      }
      content.replaceChildren(fragment);
      content.querySelectorAll("*").forEach(bindEventsAndDirectives);
      if (focusedKey) Array.from(content.querySelectorAll("[data-teloce-key]")).find(node => node.getAttribute("data-teloce-key") === focusedKey)?.focus?.();
    };
    const onScroll = () => {
      if (scheduled) return;
      scheduled = true;
      if (typeof globalThis.requestAnimationFrame === "function") globalThis.requestAnimationFrame(renderVisible);
      else queueMicrotask(renderVisible);
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    element.__teloceVirtualRender = renderVisible;
    element.__teloceVirtualSignature = signature;
    element.__teloceVirtualCleanup = () => {
      element.removeEventListener("scroll", onScroll);
      for (const scopeId of virtualScopeIds) loopScopes.delete(scopeId);
      virtualScopeIds.clear();
      content.querySelectorAll("*").forEach(cleanupElement);
      element.__teloceVirtualRender = null;
      element.__teloceVirtualSignature = null;
      element.__teloceVirtualCleanup = null;
    };
    renderVisible();
  };

  const bindScrolly = element => {
    const steps = Array.from(element.querySelectorAll("[v-step], [data-v-step]"));
    if (!steps.length) return;
    if (element.__teloceScrollyCleanup && element.__teloceScrollySteps?.length === steps.length &&
        element.__teloceScrollySteps.every((step, index) => step === steps[index])) return;
    if (element.__teloceScrollyCleanup) element.__teloceScrollyCleanup();
    const activate = step => {
      const name = step.getAttribute("v-step") || step.getAttribute("data-v-step") || "";
      steps.forEach(item => item.toggleAttribute("data-teloce-step-active", item === step));
      element.setAttribute("data-teloce-active-step", name);
      element.dispatchEvent?.(new CustomEvent("teloce:step", { detail: { name, element: step }, bubbles: true }));
    };
    let observer;
    if (typeof IntersectionObserver === "function") {
      observer = new IntersectionObserver(entries => {
        const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) activate(visible.target);
      }, { rootMargin: "-35% 0px -35% 0px", threshold: [0.1, 0.5, 0.9] });
      steps.forEach(step => observer.observe(step));
    }
    const focusHandlers = new Map();
    steps.forEach(step => { step.tabIndex ||= 0; const handler = () => activate(step); focusHandlers.set(step, handler); step.addEventListener("focus", handler); });
    activate(steps[0]);
    element.__teloceScrollySteps = steps;
    element.__teloceScrollyCleanup = () => {
      observer?.disconnect?.();
      steps.forEach(step => step.removeEventListener("focus", focusHandlers.get(step)));
      element.__teloceScrollySteps = null;
      element.__teloceScrollyCleanup = null;
    };
  };

  const bindAnnotation = element => {
    const expression = element.getAttribute("data-teloce-chart-annotation") || "";
    if (element.__teloceAnnotationCleanup && element.__teloceAnnotationSignature === expression && element.__teloceAnnotation?.isConnected) return;
    if (element.__teloceAnnotationCleanup) element.__teloceAnnotationCleanup();
    const value = evaluate(__teloceDecodeAttribute(expression), state);
    if (!value || typeof value !== "object") return;
    const annotation = document.createElement("aside");
    annotation.className = "teloce-chart-annotation";
    annotation.textContent = String(value.text ?? "");
    annotation.setAttribute("role", "note");
    annotation.dataset.target = String(value.target ?? "");
    annotation.style.position = "absolute";
    annotation.style.zIndex = "2";
    annotation.style[value.position === "bottom" ? "bottom" : "top"] = "0.75rem";
    annotation.style.left = value.x == null ? "0.75rem" : `${Number(value.x)}%`;
    if (getComputedStyle(element).position === "static") element.style.position = "relative";
    element.append(annotation);
    element.__teloceAnnotation = annotation;
    element.__teloceAnnotationSignature = expression;
    element.__teloceAnnotationCleanup = () => { annotation.remove(); element.__teloceAnnotation = null; element.__teloceAnnotationSignature = null; element.__teloceAnnotationCleanup = null; };
  };

  const bindPoll = element => {
    const url = element.getAttribute("poll");
    if (!url) return;
    const signature = [url, element.getAttribute("interval"), element.getAttribute("poll-target")].join("\u0000");
    if (element.__telocePollCleanup && element.__telocePollSignature === signature) return;
    if (element.__telocePollCleanup) element.__telocePollCleanup();
    let stopped = false;
    let controller = null;
    let timer = null;
    let delay = Math.max(1000, Number(element.getAttribute("interval") || 10000));
    const apply = payload => {
      const targetPath = element.getAttribute("poll-target");
      if (targetPath) __setSafePath(targetPath, payload, state);
      else if (payload && typeof payload === "object" && !Array.isArray(payload)) Object.assign(state, payload);
      element.dispatchEvent?.(new CustomEvent("teloce:poll", { detail: payload, bubbles: true }));
    };
    const fetchData = async () => {
      if (stopped || document.hidden) return;
      controller?.abort?.();
      controller = typeof AbortController === "function" ? new AbortController() : null;
      try {
        const response = await fetch(url, { signal: controller?.signal, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`Polling failed: ${response.status}`);
        apply(await response.json());
        delay = Math.max(1000, Number(element.getAttribute("interval") || 10000));
      } catch (error) {
        if (error?.name !== "AbortError") { delay = Math.min(delay * 2, 120000); handleError(error, "poll"); }
      } finally { if (!stopped) timer = setTimeout(fetchData, delay); }
    };
    const onVisibility = () => { if (!document.hidden) fetchData(); };
    document.addEventListener("visibilitychange", onVisibility);
    fetchData();
    element.__telocePollSignature = signature;
    element.__telocePollCleanup = () => { stopped = true; controller?.abort?.(); clearTimeout(timer); document.removeEventListener("visibilitychange", onVisibility); element.__telocePollSignature = null; element.__telocePollCleanup = null; };
  };

  const bindLive = element => {
    const source = element.getAttribute("live");
    if (!source) return;
    const targetPath = element.getAttribute("live-target");
    let socket = null;
    let stopped = false;
    let retryTimer = null;
    let retryDelay = 1000;
    const signature = [source, targetPath].join("\u0000");
    if (element.__teloceLiveCleanup && element.__teloceLiveSignature === signature) return;
    if (element.__teloceLiveCleanup) element.__teloceLiveCleanup();
    const apply = payload => {
      if (targetPath) __setSafePath(targetPath, payload, state);
      else if (payload && typeof payload === "object" && !Array.isArray(payload)) Object.assign(state, payload);
      element.dispatchEvent?.(new CustomEvent("teloce:live", { detail: payload, bubbles: true }));
    };
    const scheduleReconnect = () => {
      if (stopped || retryTimer || document.hidden) return;
      retryTimer = setTimeout(() => { retryTimer = null; connect(); }, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 120000);
    };
    const connect = () => {
      if (stopped || document.hidden) return;
      try {
        if (/^wss?:/i.test(source) && typeof WebSocket === "function") {
          socket?.close?.();
          socket = new WebSocket(source);
          socket.onopen = () => { retryDelay = 1000; };
          socket.onmessage = event => { try { apply(JSON.parse(event.data)); } catch (_) { apply(event.data); } };
          socket.onerror = error => handleError(error, "live");
          socket.onclose = () => { socket = null; scheduleReconnect(); };
        } else {
          const adapter = globalThis.__teloceLiveAdapters?.[source];
          if (typeof adapter === "function") {
            const result = adapter(apply);
            if (typeof result === "function") element.__teloceLiveAdapterCleanup = result;
            else if (result?.destroy) element.__teloceLiveAdapterCleanup = result.destroy;
          }
        }
      } catch (error) { handleError(error, "live"); scheduleReconnect(); }
    };
    const onVisibility = () => { if (!document.hidden && !socket) connect(); };
    document.addEventListener("visibilitychange", onVisibility);
    element.__teloceLiveSignature = signature;
    element.__teloceLiveCleanup = () => {
      stopped = true;
      clearTimeout(retryTimer);
      retryTimer = null;
      socket?.close?.();
      socket = null;
      element.__teloceLiveAdapterCleanup?.();
      element.__teloceLiveAdapterCleanup = null;
      document.removeEventListener("visibilitychange", onVisibility);
      element.__teloceLiveSignature = null;
      element.__teloceLiveCleanup = null;
    };
    connect();
  };

  const bindDataTable = element => {
    const expression = element.getAttribute("data-teloce-data-table") || "";
    if (!expression || typeof tableFactory !== "function") return;
    const value = evaluate(__teloceDecodeAttribute(expression), state);
    const config = value && typeof value === "object" ? value : {};
    const signature = expression;
    const previous = element.__teloceDataTable;
    if (previous && previous.signature === signature) {
      previous.instance?.update?.(config);
      previous.config = config;
      return;
    }
    previous?.instance?.unmount?.();
    try {
      const instance = tableFactory(element, config);
      element.__teloceDataTable = { signature, config, instance };
    } catch (error) { handleError(error, "data-table"); }
  };

  const bindAdvancedDirectives = element => {
    if (element.hasAttribute("data-teloce-virtual-for")) renderVirtualList(element);
    else element.__teloceVirtualCleanup?.();
    if (element.hasAttribute("data-teloce-scrolly")) bindScrolly(element);
    else element.__teloceScrollyCleanup?.();
    if (element.hasAttribute("data-teloce-chart-annotation")) bindAnnotation(element);
    else element.__teloceAnnotationCleanup?.();
    if (element.hasAttribute("poll")) bindPoll(element);
    else element.__telocePollCleanup?.();
    if (element.hasAttribute("live")) bindLive(element);
    else element.__teloceLiveCleanup?.();
    if (element.hasAttribute("data-teloce-data-table")) bindDataTable(element);
    else {
      element.__teloceDataTable?.instance?.unmount?.();
      element.__teloceDataTable = null;
    }
    const seenActions = new Set();
    const sameActionParams = (left, right) => {
      if (Object.is(left, right)) return true;
      try { return JSON.stringify(left) === JSON.stringify(right); } catch (_) { return false; }
    };
    for (const attribute of Array.from(element.attributes || [])) {
      const match = attribute.name.match(/^use:(.+)$/);
      if (!match) continue;
      const name = match[1];
      // HTML normalizes attribute names to lowercase. Resolve against the
      // case-sensitive JavaScript action map so `use:focusPanel` still finds
      // the declared `focusPanel` function in every browser.
      const actionName = Object.keys(actions).find(key => key.toLowerCase() === name.toLowerCase()) || name;
      seenActions.add(actionName);
      const action = actions[actionName]
        || (typeof globalThis[actionName] === "function" ? globalThis[actionName] : undefined);
      if (typeof action !== "function") { if (dev) console.warn(`Teloce action not found: ${name}`); continue; }
      const params = readActionParams(attribute.value);
      const signature = `${actionName}:${attribute.name}`;
      element.__teloceActions ||= new Map();
      const previous = element.__teloceActions.get(actionName);
      if (previous && previous.signature === signature && sameActionParams(previous.params, params)) continue;
      if (previous && previous.signature === signature && typeof previous.update === "function") {
        try { previous.update(params); previous.params = params; continue; } catch (error) { handleError(error, `action:${actionName}:update`); }
      }
      try { previous?.destroy?.(); } catch (error) { handleError(error, `action:${actionName}`); }
      try {
        const result = action(element, params);
        const record = { signature, params, destroy: typeof result === "function" ? result : result?.destroy, update: result?.update };
        element.__teloceActions.set(actionName, record);
      } catch (error) { handleError(error, `action:${actionName}`); }
    }
    for (const [name, record] of element.__teloceActions || []) {
      if (seenActions.has(name)) continue;
      try { record.destroy?.(); } catch (error) { handleError(error, `action:${name}:destroy`); }
      element.__teloceActions.delete(name);
    }
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
        const initialValue = __safeEvaluate(expression, state);
        if (element.type === "checkbox") element.checked = Boolean(initialValue);
        else if (initialValue !== undefined && initialValue !== null) element.value = String(initialValue);
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
    bindAdvancedDirectives(element);
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

  let directTextNodes = new Map();
  let directBindingNodes = new Map();
  let directBound = false;

  const directNeedsUpdate = (record, changed) => {
    if (!changed || !changed.size || changed.has("*")) return true;
    const dependencies = Array.isArray(record.dependencies) ? record.dependencies : [];
    return !dependencies.length || dependencies.some(dependency => changed.has(String(dependency).split(".")[0]));
  };

  const bindDirectNodes = () => {
    if (!directEnabled || !target) return;
    directTextNodes = new Map();
    directBindingNodes = new Map();
    const walker = document.createTreeWalker(target, 128);
    let current = walker.nextNode();
    while (current) {
      const match = String(current.nodeValue || "").match(/^teloce-text:([\w$-]+)$/);
      // The marker is a stable comment; the following text node carries the
      // rendered value and is the node that direct updates must mutate.
      if (match) directTextNodes.set(match[1], current.nextSibling || current);
      current = walker.nextNode();
    }
    target.querySelectorAll("[data-teloce-direct-bindings]").forEach(element => {
      for (const id of String(element.getAttribute("data-teloce-direct-bindings") || "").split(",").filter(Boolean)) {
        directBindingNodes.set(id, element);
      }
    });
    directBound = true;
  };

  const updateDirectNodes = changed => {
    if (!directEnabled || !directBound) return;
    for (const record of directBindings) {
      if (!directNeedsUpdate(record, changed)) continue;
      try {
        const value = evaluate(record.expression, state);
        if (record.kind === "text") {
          const node = directTextNodes.get(record.id);
          if (node && node.nodeValue !== String(value ?? "")) node.nodeValue = String(value ?? "");
        } else {
          const element = directBindingNodes.get(record.id);
          if (!element) continue;
          if (record.name === "model") {
            if (element.type === "checkbox") element.checked = Boolean(value);
            else if (element.value !== String(value ?? "")) element.value = value ?? "";
          } else {
            applyBinding(element, record.name, value);
          }
        }
      } catch (error) {
        handleError(error, `direct:${record.kind}`);
      }
    }
  };

  const update = (changed = null) => {
    if (destroyed || !target || rendering) return;
    const wasMounted = mounted;
    rendering = true;
    if (wasMounted) callHook("beforeUpdate");
    try {
      if (wasMounted && directEnabled && !directPlan.structural) {
        updateDirectNodes(changed);
        // A component with no child registrations has no reason to walk its
        // static subtree on every state change. This is the key difference
        // between the targeted path and the compatibility renderer.
        if (Object.keys(components).length) mountChildren();
        if (directPlan.refreshIntegrations) target.querySelectorAll("*").forEach(bindEventsAndDirectives);
      } else {
        loopScopes = new Map();
        const transitions = __teloceTransitionHooks(definition);
        __patch(target, renderTemplate(template, state, loopScopes), {
          ...transitions,
          onDispose: cleanupElement,
        });
        target.querySelectorAll("*").forEach(bindEventsAndDirectives);
        mountChildren();
        if (directEnabled && !directBound) bindDirectNodes();
      }
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
    syncQueryState();
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
      const changedKeys = new Set();
      try {
        const nextAttrs = nextProps?.$attrs || nextProps?.__attrs || {};
        const filteredAttrs = Object.fromEntries(Object.entries(nextAttrs).filter(([name]) => !declaredPropNames.has(camelizeProp(name)) && !name.startsWith("data-teloce-")));
        if (JSON.stringify(state.$attrs) !== JSON.stringify(filteredAttrs)) { state.$attrs = filteredAttrs; changed = true; changedKeys.add("$attrs"); }
        for (const [key, value] of Object.entries(normalized)) if (!Object.is(state[key], value)) { state[key] = value; changed = true; changedKeys.add(key); }
        for (const key of Object.keys(propDefinitions)) if (!(key in normalized) && state[key] !== undefined) { state[key] = undefined; changed = true; changedKeys.add(key); }
      } finally { suppressUpdates = false; }
      if (changed) update(changedKeys);
      return instance;
    },
    mount(nextTarget, props = {}) {
      target = typeof nextTarget === "string" ? document.querySelector(nextTarget) : nextTarget;
      if (!target) throw new Error("Teloce mount target was not found");
      if (mounted) instance.unmount();
      destroyed = false;
      schedulerVersion += 1;
      registerQueryListener();
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
      directTextNodes.clear();
      directBindingNodes.clear();
      directBound = false;
      pendingDependencies.clear();
      queued = false;
      schedulerVersion += 1;
      mounted = false;
      destroyed = true;
      hmrRegistry.get(hmrKey)?.delete(hmrRecord);
      if (hmrRegistry.get(hmrKey)?.size === 0) hmrRegistry.delete(hmrKey);
      hmrRecord.target = null;
      if (queryListenerActive && typeof window !== "undefined") { window.removeEventListener("popstate", onPopState); queryListenerActive = false; }
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

/** Compiler-generated component rendering, hydration, bindings and diagnostics. @module */
/** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent, CompiledOptions, MountedChild, RuntimeDiagnostic, DirectBinding, DirectRegion, KeyedRowPlan, CompiledDefinition, QueryDescriptor, RowCache} from './contracts.js' */
// Framework-independent diagnostics. Hosts subscribe without owning Teloce.
/** @type {Set<(report: RuntimeDiagnostic) => void>} */
const __teloceErrorListeners = new Set();
/** Subscribe to isolated runtime diagnostics. @param {(report: RuntimeDiagnostic) => void} listener */ export function onTeloceError(listener) {
  __teloceErrorListeners.add(listener);
  return () => __teloceErrorListeners.delete(listener);
}
/** @param {unknown} error @param {Partial<RuntimeDiagnostic>} [detail] @returns {RuntimeDiagnostic} */
export function reportTeloceError(error, detail = {}) {
  const failure = error && typeof error === 'object' && 'message' in error ? error : null;
  const report = { category: 'runtime', ...detail,
    message: String(failure?.message || error), stack: String(failure && 'stack' in failure ? failure.stack || '' : '') };
  for (const listener of [...__teloceErrorListeners]) {
    try { listener(report); } catch (_) { /* A reporter must not break application updates. */ }
  }
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('teloce:error', { detail: report }));
  return report;
}
const __hydrationShape = /** @returns {string} @param {RuntimeElement} root */ (root, componentTags = new Set()) => [...root.childNodes].filter(node => node.nodeType === 1).map(node => {
  if (/** @type {Element} */ (node).hasAttribute('data-teloce-ssr-boundary') || componentTags.has(/** @type {Element} */ (node).tagName)) return /** @type {Element} */ (node).tagName;
  return /** @type {Element} */ (node).tagName + '(' + __hydrationShape(/** @type {RuntimeElement} */ (node), componentTags) + ')';
}).join(',');

/* Shared renderer for compiler-generated Teloce components.
 *
 * Generated modules contain the component definition, template, imports and
 * CSS metadata only.  The lifecycle, event, binding, reconciliation and HMR
 * bridge lives here once per application build.
 */

const __teloceEscapeHtml = /** @param {DynamicValue} value */ value => String(value ?? "").replace(/[&<>"']/g, character => (/** @type {Record<string, string>} */ ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]));

const __teloceEscapeAttribute = /** @param {DynamicValue} value */ value => __teloceEscapeHtml(value);
const __teloceDecodeAttribute = /** @param {DynamicValue} value */ value => String(value ?? "")
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&#x27;/gi, "'")
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/&amp;/g, "&");

const __teloceBuiltInTransitions = {
  /** @param {RuntimeElement} node */ fade(node, /** @type {DynamicRecord} */ opts = {}) {
    const { duration = 200, easing = "ease" } = opts;
    return node.animate?.([{ opacity: 0 }, { opacity: 1 }], { duration, easing, fill: "forwards" });
  },
  /** @param {RuntimeElement} node */ slide(node, /** @type {DynamicRecord} */ opts = {}) {
    const { axis = "y", distance = 10, duration = 200, easing = "ease-out" } = opts;
    const property = axis === "y" ? "translateY" : "translateX";
    return node.animate?.([
      { transform: `${property}(${distance}px)`, opacity: 0 },
      { transform: `${property}(0)`, opacity: 1 },
    ], { duration, easing, fill: "forwards" });
  },
  /** @param {RuntimeElement} node */ scale(node, /** @type {DynamicRecord} */ opts = {}) {
    const { start = 0.9, duration = 150, easing = "ease-out" } = opts;
    return node.animate?.([
      { transform: `scale(${start})`, opacity: 0 },
      { transform: "scale(1)", opacity: 1 },
    ], { duration, easing, fill: "forwards" });
  },
};

const __teloceParseTransition = /** @param {DynamicValue} value */ value => {
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

const __teloceTransitionHooks = /** @param {DynamicRecord} definition */ definition => {
  const registry = { ...__teloceBuiltInTransitions, ...(definition?.transitions || {}) };
  const run = /** @param {RuntimeElement} node @param {string} attribute */ (node, attribute) => {
    const raw = node?.getAttribute?.(attribute);
    if (!raw) return null;
    const { name, options } = __teloceParseTransition(raw);
    const transition = registry[name];
    return typeof transition === "function" ? transition(node, options) : null;
  };
  const playEnter = /** @param {RuntimeElement} node */ node => {
    if (!node || node.nodeType !== 1) return;
    const attribute = node.hasAttribute("data-teloce-in")
      ? "data-teloce-in"
      : node.hasAttribute("data-teloce-transition") ? "data-teloce-transition" : null;
    if (attribute) run(node, attribute);
    node.querySelectorAll?.("[data-teloce-in], [data-teloce-transition]").forEach(/** @param {RuntimeElement} child */ child => {
      run(child, child.hasAttribute("data-teloce-in") ? "data-teloce-in" : "data-teloce-transition");
    });
  };
  const playExit = /** @param {RuntimeElement} node */ node => {
    if (!node || node.nodeType !== 1 || !node.isConnected) return;
    const attribute = node.hasAttribute("data-teloce-out")
      ? "data-teloce-out"
      : node.hasAttribute("data-teloce-transition") ? "data-teloce-transition" : null;
    if (!attribute || !node.parentNode) return;
    const ghost = /** @type {ChildNode} */ (node.cloneNode(true));
    node.parentNode.insertBefore(ghost, node.nextSibling);
    const animation = run(ghost, attribute);
    if (animation?.finished?.then) animation.finished.then(() => ghost.remove()).catch(() => ghost.remove());
    else ghost.remove();
  };
  return { playEnter, playExit };
};

/**
 * Share a lazy import while keeping each returned handle tied to its mount.
 * Rejected imports may be retried; obsolete handles cannot destroy a new child.
 * @param {() => DynamicValue | Promise<DynamicValue>} loader
 */
const __teloceLazy = loader => {
  if (typeof loader !== "function") throw new TypeError("Teloce lazy loader must be a function");
  /** @type {Promise<DynamicValue> | null} */
  let loading = null;
  /** @type {MountedChild | null} */
  let active = null;
  /** @type {Element | null} */
  let target = null;
  /** @type {DynamicRecord} */
  let props = {};
  let mounted = false;
  let generation = 0;
  const clear = () => {
    mounted = false;
    generation += 1;
    try { active?.unmount?.(); }
    finally {
      active = null;
      target?.removeAttribute("data-teloce-loading");
      target?.replaceChildren();
      target = null;
    }
  };
  const load = () => {
    if (!loading) loading = Promise.resolve().then(loader)
      .then(module => module?.default ?? module)
      .catch(error => { loading = null; throw error; });
    return loading;
  };
  return {
    /** @param {string | Element | null} nextTarget @param {DynamicRecord} [nextProps] */
    mount(nextTarget, nextProps = {}) {
      const next = typeof nextTarget === "string" ? document.querySelector(nextTarget) : nextTarget;
      if (!next) throw new Error("Teloce mount target was not found");
      if (mounted) clear();
      target = next;
      props = nextProps;
      mounted = true;
      const currentGeneration = ++generation;
      target.setAttribute("data-teloce-loading", "true");
      const instance = {
        /** @param {DynamicRecord} [next] */
        updateProps(next = {}) {
          if (currentGeneration !== generation || !mounted) return;
          props = next;
          active?.updateProps?.(next);
        },
        unmount() { if (currentGeneration === generation) clear(); },
      };
      load().then(component => {
        if (!mounted || currentGeneration !== generation || !target) return;
        target.removeAttribute("data-teloce-loading");
        if (typeof component?.mount !== "function") throw new TypeError("Teloce lazy component must provide mount()");
        active = component.mount(target, props);
      }).catch(error => {
        if (mounted && currentGeneration === generation && target) {
          target.removeAttribute("data-teloce-loading");
          reportTeloceError(error, { phase: "lazy", category: "runtime" });
          target.dispatchEvent(new CustomEvent("teloce:lazy-error", { detail: error }));
        }
      });
      return instance;
    },
    /** @param {DynamicRecord} [next] */
    updateProps(next = {}) { props = next; active?.updateProps?.(next); },
    unmount: clear,
  };
};

// Small, dependency-free browser primitives used by generated components.
// They live in the shared runtime so a project does not ship a copy per
// component.
const __teloceSplitArguments = /** @param {DynamicValue} source */ source => {
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

const __teloceCreateCompiledComponent = /** @param {CompiledDefinition} definition */ (definition, /** @type {CompiledOptions} */ options = {}) => {
  const template = String(options.template ?? "");
  const camelizeProp = /** @param {string} name */ name => String(name).replace(/-([a-z])/g, (_, character) => character.toUpperCase());
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
  const directRegions = Array.isArray(directPlan.regions) ? directPlan.regions : [];
  const directRegionIndex = new Map(directRegions.map(/** @param {DirectRegion} record */ record => [record.id, record]));
  /** @type {Map<string, RowCache>} */
  const initialRowCaches = new Map();
  /** @type {Map<string, Set<DirectBinding>>} */
  const bindingIndex = new Map();
  /** @type {Set<DirectBinding>} */
  const alwaysBindings = new Set();
  for (const record of directBindings) {
    const dependencies = record.dependencies || [];
    if (!dependencies.length || dependencies.includes('*')) alwaysBindings.add(record);
    for (const dependency of dependencies) {
      const root = String(dependency).split('.')[0];
      if (!bindingIndex.has(root)) bindingIndex.set(root, new Set());
      bindingIndex.get(root)?.add(record);
    }
  }
  const nativeEvents = new Set([
    "click", "input", "submit", "change", "keyup", "keydown", "focus", "blur",
    "mouseenter", "mouseleave", "mousedown", "mouseup", "pointerdown", "pointerup",
  ]);

  const evaluate = /** @param {string} expression @param {DynamicRecord} scope */ (expression, scope) => {
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
      handleError(error, "expression", String(expression));
      return "";
    }
  };

  const mapClass = /** @param {DynamicValue} value */ value => {
    const map = /** @param {DynamicValue} token */ token => styleClasses[token] || token;
    if (Array.isArray(value)) return value.map(map).join(" ");
    if (value && typeof value === "object") return Object.keys(value).filter(key => value[key]).map(map).join(" ");
    if (typeof value === "string") return value.split(/\s+/).filter(Boolean).map(map).join(" ");
    return value;
  };

  const isDangerousUrl = /** @param {DynamicValue} value */ value => /^(?:javascript|vbscript|data|file):/.test(
    String(value ?? "").replace(/[\t\n\r\0]/g, "").trim().toLowerCase()
  );
  const sanitizeHtml = /** @param {DynamicValue} value */ value => {
    const node = document.createElement("template");
    node.innerHTML = String(value ?? "");
    node.content.querySelectorAll("script,iframe,object,embed,link,meta,base").forEach(child => child.remove());
    node.content.querySelectorAll("*").forEach(child => {
      for (const attribute of Array.from(child.attributes)) {
        const name = attribute.name.toLowerCase();
        if (name.startsWith("on") || (["href", "src", "action", "formaction", "xlink:href"].includes(name) && isDangerousUrl(attribute.value))) {
          child.removeAttribute(attribute.name);
        }
      }
    });
    return node.innerHTML || /** @type {RuntimeElement | undefined} */ (node.content?.firstChild)?.outerHTML || "";
  };

  const applyBinding = /** @param {RuntimeElement} element @param {string} name @param {DynamicValue} value */ (element, name, value) => {
    if (name === "key") return;
    const securityName = name.toLowerCase();
    if (securityName.startsWith("on") || securityName === "srcdoc") { element.removeAttribute(name); return; }
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
        const securityName = attribute.toLowerCase();
        if (securityName.startsWith("data-teloce-") || securityName === "children" || securityName.startsWith("on") || securityName === "srcdoc") { element.removeAttribute(attribute); continue; }
        if (attribute === "class") {
          const staticClass = element.getAttribute("data-teloce-static-class") ?? element.__teloceStaticClass ?? element.className ?? "";
          element.__teloceStaticClass = staticClass;
          const merged = [staticClass, mapClass(nextValue)].filter(Boolean).join(" ");
          element.setAttribute("class", merged);
        } else if (attribute === "style" && nextValue && typeof nextValue === "object") {
          for (const [property, propertyValue] of Object.entries(nextValue)) element.style[property] = propertyValue ?? "";
        } else if (nextValue === false || nextValue == null) element.removeAttribute(attribute);
        else if (["href", "src", "action", "formaction", "xlink:href"].includes(securityName) && isDangerousUrl(nextValue)) element.removeAttribute(attribute);
        else element.setAttribute(attribute, String(nextValue));
        if (nextValue !== false && nextValue != null) applied.add(attribute);
      }
      element.__teloceForwardedAttrs = applied;
    } else if (name === "class") {
      const staticClass = element.getAttribute("data-teloce-static-class") ?? element.__teloceStaticClass ?? element.className ?? "";
      element.__teloceStaticClass = staticClass;
      const nextClass = [staticClass, String(mapClass(value) ?? "").trim()].filter(Boolean).join(" ");
      if (element.getAttribute('class') !== nextClass) element.setAttribute('class', nextClass);
    } else if (name === "style" && value && typeof value === "object") {
      const previous = element.__teloceDynamicStyles || new Set();
      for (const key of previous) if (!(key in value) && element.style[key]) element.style[key] = "";
      for (const [key, item] of Object.entries(value)) if (element.style[key] !== String(item ?? "")) element.style[key] = item ?? "";
      element.__teloceDynamicStyles = new Set(Object.keys(value));
    } else if (name === "show" || name === "hide") {
      const hidden = name === "show" ? !Boolean(value) : Boolean(value);
      if (element.hidden !== hidden) element.hidden = hidden;
    } else if (name === "html") {
      const html = sanitizeHtml(value);
      if (element.innerHTML !== html) element.innerHTML = html;
    } else if (name === "text") {
      const text = value == null ? "" : String(value);
      if (element.textContent !== text) element.textContent = text;
    } else if (name === "value" && "value" in element) {
      if (element.value !== String(value ?? "")) {
        const selection = document.activeElement === element && typeof element.selectionStart === 'number'
          ? [element.selectionStart, element.selectionEnd, element.selectionDirection] : null;
        element.value = String(value ?? "");
        if (selection) element.setSelectionRange(...selection);
      }
      if (element.getAttribute("value") !== String(value ?? "")) element.setAttribute("value", String(value ?? ""));
    } else if (["disabled", "checked", "selected", "readonly", "required", "multiple"].includes(name)) {
      if (element.hasAttribute(name) !== Boolean(value)) element.toggleAttribute(name, Boolean(value));
    } else if (["href", "src", "action", "formaction", "xlink:href"].includes(securityName) && isDangerousUrl(value)) {
      if (element.hasAttribute(name)) element.removeAttribute(name);
    } else if (value === false || value == null) {
      if (element.hasAttribute(name)) element.removeAttribute(name);
    } else {
      if (element.getAttribute(name) !== String(value)) element.setAttribute(name, String(value));
    }
  };

  const resolveIfBlocks = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope) => {
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

  const prepareRowCache = /** @returns {RowCache} @param {KeyedRowPlan} plan */ plan => ({
    rows: new Map(), order: [],
    rowRoots: new Set(plan.paths.map(/** @param {DynamicValue} path */ path => path.split('.')[0])),
    rowReaders: plan.paths.map(/** @param {DynamicValue} path */ path => {
      const parts = path.split('.');
      return /** @param {DynamicRecord} scope */ scope => {
        let value = scope;
        for (const part of parts) {
          if (part === '__proto__' || part === 'prototype' || part === 'constructor') return undefined;
          value = value?.[part];
        }
        return value;
      };
    }),
  });

  const renderForBlocks = /** @param {DynamicValue} source @param {DynamicRecord} scope @param {DynamicValue} loopScopes */ (source, scope, loopScopes) => {
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
      // Capture dependencies while this loop is already being rendered.
      // The DOM binding walk attaches nodes to these records after patching;
      // no second collection evaluation or row-scope setup is needed.
      const regionId = result.slice(0, start).match(/<!--teloce-region:([\w$-]+)-->$/)?.[1];
      const rowPlan = directEnabled && directRegionIndex.get(regionId)?.rows;
      const cache = rowPlan && Array.isArray(rawValues) ? prepareRowCache(rowPlan) : null;
      if (cache) { cache.byScope = new Map(); initialRowCaches.set(regionId, cache); }
      const rendered = values.map((value, index) => {
        const locals = { ...(scope[loopLocals] || {}), [item]: value, index, [opening.match(/index="([^"]+)"/)?.[1] || "index"]: index };
        const loopScope = cache ? { ...locals, [loopLocals]: locals } : { ...scope, ...locals, [loopLocals]: locals };
        if (cache) for (const root of cache.rowRoots) {
          if (!(root in locals) && Object.prototype.hasOwnProperty.call(scope, root)) loopScope[root] = scope[root];
        }
        const scopeId = String(loopScopeSequence++);
        // Retain only row locals. Global state must be read at event time,
        // even when an unrelated state change skips this region's renderer.
        loopScopes.set(scopeId, locals);
        if (cache && rowPlan) {
          const key = String(evaluate(rowPlan.key, loopScope));
          if (cache.rows.has(key)) throw new Error(`Duplicate keyed loop value: ${key}`);
          const row = { scopeId, snapshot: cache.rowReaders.map(/** @param {DynamicValue} read */ read => read(loopScope)), node: null, needsBind: false };
          cache.rows.set(key, row); cache.byScope?.set(scopeId, row); cache.order.push(row);
        }
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
  const renderVirtualForBlocks = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope) => {
    let result = String(source ?? "");
    let start = result.indexOf("<virtual-for ");
    while (start >= 0) {
      const openingEnd = result.indexOf(">", start);
      if (openingEnd < 0) break;
      const opening = result.slice(start, openingEnd + 1);
      const closeStart = result.indexOf("</virtual-for>", openingEnd + 1);
      if (closeStart < 0) break;
      const body = result.slice(openingEnd + 1, closeStart);
      const attr = /** @param {string} name */ name => opening.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? "";
      const item = attr("item") || "item";
      const collection = attr("in") || attr("collection");
      const key = attr("key") || "index";
      const itemHeight = attr("item-height") || "40";
      const overscan = attr("overscan") || "5";
      const minHeight = attr("min-height") || "";
      const bodySource = encodeURIComponent(body);
      const rootTag = body.match(/<[^>]+>/)?.[0] || '';
      const scopeAttributes = (rootTag.match(/\bdata-v-[\w-]+(?:="[^"]*")?/g) || []).join(' ');
      const wrapper = `<div ${scopeAttributes} class="teloce-virtual-list" style="position:relative;overflow:auto" data-teloce-virtual-for="true" data-teloce-virtual-item="${__teloceEscapeAttribute(item)}" data-teloce-virtual-collection="${__teloceEscapeAttribute(collection)}" data-teloce-virtual-key="${__teloceEscapeAttribute(key)}" data-teloce-virtual-item-height="${__teloceEscapeAttribute(itemHeight)}" data-teloce-virtual-overscan="${__teloceEscapeAttribute(overscan)}" data-teloce-virtual-min-height="${__teloceEscapeAttribute(minHeight)}" data-teloce-virtual-body="${__teloceEscapeAttribute(bodySource)}"><div ${scopeAttributes} class="teloce-virtual-spacer"></div><div ${scopeAttributes} class="teloce-virtual-content" style="position:absolute;top:0;left:0;width:100%"></div></div>`;
      result = result.slice(0, start) + wrapper + result.slice(closeStart + 14);
      start = result.indexOf("<virtual-for ", start + wrapper.length);
    }
    return result;
  };

  const renderTemplate = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope, loopScopes = new Map()) => {
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

  const readProps = /** @param {RuntimeElement} element @param {DynamicRecord} parentState */ (element, parentState) => {
    /** @type {Record<string, string>} */
    const slots = { default: "" };
    for (const child of /** @type {RuntimeElement[]} */ (Array.from(element.childNodes || []))) {
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
    /** @type {DynamicRecord} */
    const props = { __slots: slots };
    /** @type {DynamicRecord} */
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

  const destroyDirectiveRecord = /** @param {RuntimeElement} element @param {string} name @param {DynamicRecord} record */ (element, name, record) => {
    if (!record) return;
    try { record.directive?.beforeUnmount?.(element, record.context); }
    catch (error) { handleError(error, `directive:${name}:beforeUnmount`); }
    try { record.cleanup?.(); }
    catch (error) { handleError(error, `directive:${name}:cleanup`); }
    try { record.directive?.destroy?.(element, record.context); }
    catch (error) { handleError(error, `directive:${name}:destroy`); }
    try { record.directive?.unmounted?.(element, record.context); }
    catch (error) { handleError(error, `directive:${name}:unmounted`); }
  };

  const cleanupElement = /** @param {RuntimeElement} element */ element => {
    if (element.__teloceHandlers) {
      for (const record of element.__teloceHandlers.values()) element.removeEventListener(record.actualEvent, record.listener, record.options);
      element.__teloceHandlers.clear();
    }
    if (element.__teloceModelListener) {
      removeModelListener(element);
    }
    for (const [name, record] of element.__teloceDirectives?.entries?.() || []) {
      destroyDirectiveRecord(element, name, record);
    }
    element.__teloceDirectives?.clear?.();
    for (const record of element.__teloceActions?.values?.() || []) {
      try { record.destroy?.(); } catch (error) { handleError(error, "action:destroy"); }
    }
    element.__teloceActions?.clear?.();
    try { element.__teloceScrollyCleanup?.(); } catch (error) { handleError(error, "scrolly:cleanup"); }
    element.__teloceScrollyCleanup = null;
    try { element.__teloceLiveCleanup?.(); } catch (error) { handleError(error, "live:cleanup"); }
    element.__teloceLiveCleanup = null;
    try { element.__telocePollCleanup?.(); } catch (error) { handleError(error, "poll:cleanup"); }
    element.__telocePollCleanup = null;
    try { element.__teloceAnnotationCleanup?.(); } catch (error) { handleError(error, "annotation:cleanup"); }
    element.__teloceAnnotationCleanup = null;
    try { element.__teloceVirtualCleanup?.(); } catch (error) { handleError(error, "virtual:cleanup"); }
    element.__teloceVirtualCleanup = null;
    try { element.__teloceDataTable?.instance?.unmount?.(); } catch (error) { handleError(error, "data-table:destroy"); }
    element.__teloceDataTable = null;
  };

  let target = /** @type {RuntimeElement | null | undefined} */ (null);
  let mounted = false;
  let destroyed = false;
  let rendering = false;
  let suppressUpdates = false;
  let queued = false;
  /** @type {Map<string, DynamicRecord>} */
  let loopScopes = new Map();
  const loopLocals = Symbol('teloce.loopLocals');
  let loopScopeSequence = 0;
  /** @type {DynamicRecord} */
  let state;
  /** @type {DynamicRecord} */
  let previousWatchValues = {};
  /** @type {Set<string>} */
  let pendingDependencies = new Set();
  let schedulerVersion = 0;

  const handleError = /** Report failures without interrupting unrelated cleanup. @param {unknown} error @param {string} phase */ (error, phase, /** @type {string | null} */ expression = null) => {
    if (dev) console.error(`Teloce ${phase} error:`, error);
    const location = options.sourceLocations?.[/** @type {string} */ (expression)] || {};
    reportTeloceError(error, { category: phase === 'hydration' ? 'hydration' : 'runtime',
      phase, expression, component: options.component || definition?.name,
      filename: moduleUrl, ...location });
    try { options.onError?.(error, phase); } catch (_) {}
  };
  const requestUpdate = /** @param {DynamicValue} [dependency] */ dependency => {
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
  const normalizeProps = /** @param {DynamicRecord} input */ input => {
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
    if (typeof method === "function") state[name] = (/** @type {DynamicValue[]} */ ...args) => method.apply(state, args);
  }
  for (const [name, computed] of Object.entries(definition?.computed || {})) {
    if (typeof computed === "function") {
      Object.defineProperty(state, name, { configurable: true, enumerable: true, get: () => computed.call(state) });
    }
  }
  state.$emit = /** @param {string} name @param {DynamicRecord} detail */ (name, detail) => target?.dispatchEvent?.(new CustomEvent(`teloce:${name}`, { detail, bubbles: true }));
  suppressUpdates = false;

  const parseQueryValue = /** @param {DynamicValue} raw @param {string | QueryDescriptor} definition */ (raw, definition) => {
    if (raw == null) return undefined;
    const type = typeof definition === "string" ? definition : definition?.type;
    if (type === "number") { const number = Number(raw); return Number.isFinite(number) ? number : undefined; }
    if (type === "boolean" || type === "Boolean") return raw === "1" || raw === "true";
    if (type === "json" || type === "array") { try { return JSON.parse(raw); } catch (_) { return undefined; } }
    return raw;
  };
  const queryKey = /** @param {string} name @param {string | QueryDescriptor} config */ (name, config) => typeof config === "string" ? config : config?.key || name;
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
  const watchValue = /** @param {string} name */ name => String(name).split(".").reduce((value, key) => value == null ? undefined : value[key], state);
  const callHook = /** @param {string} name */ (name, /** @type {DynamicValue[]} */ ...args) => {
    const hook = definition?.[name];
    if (typeof hook !== "function") return;
    try {
      const result = hook.apply(state, args);
      if (result?.then) result.catch(/** @param {DynamicValue} error */ error => handleError(error, name));
      return result;
    } catch (error) { handleError(error, name); }
  };

  const readActionParams = /** @param {string} expression */ expression => expression && expression.trim()
    ? evaluate(__teloceDecodeAttribute(expression), state)
    : undefined;

  const renderVirtualList = /** @param {RuntimeElement} element */ element => {
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
    let disposed = false;
    let frame = /** @type {DynamicValue} */ (null);
    let virtualScopeIds = new Set();
    const renderVisible = () => {
      scheduled = false;
      if (disposed || destroyed) return;
      const previousScopes = virtualScopeIds;
      virtualScopeIds = new Set();
      const raw = evaluate(collectionExpression, state);
      const values = Array.isArray(raw) ? raw : raw && typeof raw === "object" ? Object.values(raw) : [];
      const rowHeight = Math.max(1, Number(evaluate(rowHeightExpression, state) || rowHeightExpression) || 40);
      const overscan = Math.max(0, Number(evaluate(overscanExpression, state) || overscanExpression) || 5);
      const minHeight = Number(evaluate(minHeightExpression, state) || minHeightExpression);
      // With no authored viewport height, a full-height spacer would expand
      // the container and defeat virtualization on the next update.
      if (!element.clientHeight) element.style.height = `${Number.isFinite(minHeight) && minHeight > 0 ? minHeight : 320}px`;
      if (Number.isFinite(minHeight) && minHeight >= 0) element.style.minHeight = `${minHeight}px`;
      const viewportHeight = element.clientHeight || 320;
      const maxScroll = Math.max(0, values.length * rowHeight - viewportHeight);
      if (element.scrollTop > maxScroll) element.scrollTop = maxScroll;
      const first = Math.max(0, Math.floor(element.scrollTop / rowHeight) - overscan);
      const last = Math.min(values.length, Math.ceil((element.scrollTop + viewportHeight) / rowHeight) + overscan);
      spacer.style.height = `${values.length * rowHeight}px`;
      content.style.transform = `translateY(${first * rowHeight}px)`;
      const markupRows = [];
      for (let index = first; index < last; index += 1) {
        const value = values[index];
        const loopScope = { ...state, [itemName]: value, index };
        const scopeId = String(loopScopeSequence++);
        loopScopes.set(scopeId, { [itemName]: value, index });
        virtualScopeIds.add(scopeId);
        let markup = renderTemplate(body, loopScope, loopScopes);
        const key = evaluate(keyExpression, loopScope);
        markup = markup.replace(/^(\s*<[A-Za-z][\w:-]*)(?=[\s>])/, `$1 data-teloce-key="${__teloceEscapeAttribute(String(key ?? index))}" data-teloce-loop-scope="${scopeId}"`);
        markupRows.push(markup);
      }
      __patch(content, markupRows.join(''), { onDispose: cleanupElement });
      for (const scopeId of previousScopes) loopScopes.delete(scopeId);
      content.querySelectorAll("*").forEach(bindEventsAndDirectives);
    };
    const onScroll = () => {
      if (scheduled || disposed) return;
      scheduled = true;
      if (typeof globalThis.requestAnimationFrame === "function") frame = globalThis.requestAnimationFrame(renderVisible);
      else queueMicrotask(renderVisible);
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    element.__teloceVirtualRender = renderVisible;
    element.__teloceVirtualSignature = signature;
    element.__teloceVirtualCleanup = () => {
      disposed = true;
      if (frame != null) globalThis.cancelAnimationFrame?.(frame);
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

  const bindScrolly = /** @param {RuntimeElement} element */ element => {
    const steps = Array.from(element.querySelectorAll("[v-step], [data-v-step]"));
    if (!steps.length) return;
    if (element.__teloceScrollyCleanup && element.__teloceScrollySteps?.length === steps.length &&
        element.__teloceScrollySteps.every(/** @param {DynamicValue} step @param {number} index */ (step, index) => step === steps[index])) return;
    if (element.__teloceScrollyCleanup) element.__teloceScrollyCleanup();
    const activate = /** @param {DynamicValue} step */ step => {
      const name = step.getAttribute("v-step") || step.getAttribute("data-v-step") || "";
      steps.forEach(item => item.toggleAttribute("data-teloce-step-active", item === step));
      element.setAttribute("data-teloce-active-step", name);
      element.dispatchEvent?.(new CustomEvent("teloce:step", { detail: { name, element: step }, bubbles: true }));
    };
    /** @type {IntersectionObserver | undefined} */
    let observer;
    if (typeof IntersectionObserver === "function") {
      observer = new IntersectionObserver(entries => {
        const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) activate(visible.target);
      }, { rootMargin: "-35% 0px -35% 0px", threshold: [0.1, 0.5, 0.9] });
      steps.forEach(step => /** @type {IntersectionObserver} */ (observer).observe(step));
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

  const bindAnnotation = /** @param {RuntimeElement} element */ element => {
    const expression = element.getAttribute("data-teloce-chart-annotation") || "";
    const value = evaluate(__teloceDecodeAttribute(expression), state);
    if (!value || typeof value !== "object") {
      element.__teloceAnnotationCleanup?.();
      return;
    }
    let valueSignature;
    try { valueSignature = JSON.stringify(value); } catch (_) { valueSignature = String(value); }
    const signature = `${expression}\u0000${valueSignature}`;
    if (element.__teloceAnnotationCleanup && element.__teloceAnnotationSignature === signature && element.__teloceAnnotation?.isConnected) return;
    if (element.__teloceAnnotationCleanup) element.__teloceAnnotationCleanup();
    const annotation = document.createElement("aside");
    annotation.className = "teloce-chart-annotation";
    annotation.textContent = String(value.text ?? "");
    annotation.setAttribute("role", "note");
    annotation.dataset.target = String(value.target ?? "");
    annotation.style.position = "absolute";
    annotation.style.zIndex = "2";
    annotation.style[value.position === "bottom" ? "bottom" : "top"] = "0.75rem";
    annotation.style.left = value.x == null ? "0.75rem" : `${Number(value.x)}%`;
    if (getComputedStyle(/** @type {Element} */ (element)).position === "static") element.style.position = "relative";
    element.append(annotation);
    element.__teloceAnnotation = annotation;
    element.__teloceAnnotationSignature = signature;
    element.__teloceAnnotationCleanup = () => { annotation.remove(); element.__teloceAnnotation = null; element.__teloceAnnotationSignature = null; element.__teloceAnnotationCleanup = null; };
  };

  const bindPoll = /** @param {RuntimeElement} element */ element => {
    const url = element.getAttribute("poll");
    if (!url) return;
    const signature = [url, element.getAttribute("interval"), element.getAttribute("poll-target")].join("\u0000");
    if (element.__telocePollCleanup && element.__telocePollSignature === signature) return;
    if (element.__telocePollCleanup) element.__telocePollCleanup();
    let stopped = false;
    /** @type {AbortController | null} */
    let controller = null;
    /** @type {ReturnType<typeof setTimeout> | null} */
    let timer = null;
    let inFlight = false;
    const interval = () => {
      const value = Number(element.getAttribute("interval") || 10000);
      return Number.isFinite(value) ? Math.max(1000, value) : 10000;
    };
    let delay = interval();
    const apply = /** @param {DynamicValue} payload */ payload => {
      if (stopped || destroyed) return;
      const targetPath = element.getAttribute("poll-target");
      if (targetPath) __setSafePath(targetPath, payload, state);
      else if (payload && typeof payload === "object" && !Array.isArray(payload)) Object.assign(state, payload);
      element.dispatchEvent?.(new CustomEvent("teloce:poll", { detail: payload, bubbles: true }));
    };
    const fetchData = async () => {
      if (stopped || document.hidden || inFlight) return;
      inFlight = true;
      if (timer !== null) clearTimeout(timer);
      timer = null;
      controller?.abort();
      controller = typeof AbortController === "function" ? new AbortController() : null;
      try {
        const response = await fetch(url, { signal: controller?.signal, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`Polling failed: ${response.status}`);
        const payload = await response.json();
        if (!stopped && !controller?.signal.aborted) apply(payload);
        delay = interval();
      } catch (error) {
        if (!stopped && /** @type {Error | null} */ (error)?.name !== "AbortError") { delay = Math.min(delay * 2, 120000); handleError(error, "poll"); }
      } finally { inFlight = false; if (!stopped) timer = setTimeout(fetchData, delay); }
    };
    const onVisibility = () => { if (!document.hidden) fetchData(); };
    document.addEventListener("visibilitychange", onVisibility);
    fetchData();
    element.__telocePollSignature = signature;
    element.__telocePollCleanup = () => { stopped = true; controller?.abort?.(); if (timer !== null) clearTimeout(timer); document.removeEventListener("visibilitychange", onVisibility); element.__telocePollSignature = null; element.__telocePollCleanup = null; };
  };

  const bindLive = /** @param {RuntimeElement} element */ element => {
    const source = element.getAttribute("live");
    if (!source) return;
    const targetPath = element.getAttribute("live-target");
    /** @type {WebSocket | null} */
    let socket = null;
    let adapterConnected = false;
    let stopped = false;
    /** @type {ReturnType<typeof setTimeout> | null} */
    let retryTimer = null;
    let retryDelay = 1000;
    const signature = [source, targetPath].join("\u0000");
    if (element.__teloceLiveCleanup && element.__teloceLiveSignature === signature) return;
    if (element.__teloceLiveCleanup) element.__teloceLiveCleanup();
    const apply = /** @param {DynamicValue} payload */ payload => {
      if (stopped || destroyed) return;
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
      if (stopped || document.hidden || socket || adapterConnected) return;
      if (retryTimer !== null) clearTimeout(retryTimer);
      retryTimer = null;
      try {
        const websocketSource = /^wss?:/i.test(source) || source.startsWith("/");
        if (websocketSource && typeof WebSocket === "function") {
          const socketUrl = /^wss?:/i.test(source)
            ? source
            : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${source}`;
          const connection = new WebSocket(socketUrl);
          socket = connection;
          connection.onopen = () => { if (!stopped && socket === connection) retryDelay = 1000; };
          connection.onmessage = event => {
            if (stopped || socket !== connection) return;
            let payload;
            try { payload = JSON.parse(event.data); } catch (_) { payload = event.data; }
            apply(payload);
          };
          connection.onerror = error => { if (!stopped && socket === connection) handleError(error, "live"); };
          connection.onclose = () => { if (socket !== connection) return; socket = null; scheduleReconnect(); };
        } else {
          const adapter = (/** @type {DynamicRecord} */ (globalThis)).__teloceLiveAdapters?.[source];
          if (typeof adapter === "function") {
            adapterConnected = true;
            const result = adapter(apply);
            if (typeof result === "function") element.__teloceLiveAdapterCleanup = result;
            else if (typeof result?.destroy === "function") element.__teloceLiveAdapterCleanup = () => result.destroy();
          }
        }
      } catch (error) { adapterConnected = false; handleError(error, "live"); scheduleReconnect(); }
    };
    const onVisibility = () => { if (!document.hidden && !socket) connect(); };
    document.addEventListener("visibilitychange", onVisibility);
    element.__teloceLiveSignature = signature;
    element.__teloceLiveCleanup = () => {
      stopped = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      retryTimer = null;
      if (socket) {
        socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
        socket.close();
      }
      socket = null;
      adapterConnected = false;
      document.removeEventListener("visibilitychange", onVisibility);
      const adapterCleanup = element.__teloceLiveAdapterCleanup;
      element.__teloceLiveAdapterCleanup = null;
      element.__teloceLiveSignature = null;
      element.__teloceLiveCleanup = null;
      adapterCleanup?.();
    };
    connect();
  };

  const bindDataTable = /** @param {RuntimeElement} element */ element => {
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

  const bindAdvancedDirectives = /** @param {RuntimeElement} element */ element => {
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
    const sameActionParams = /** @param {DynamicValue} left @param {DynamicValue} right */ (left, right) => {
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
        || (typeof (/** @type {DynamicRecord} */ (globalThis))[actionName] === "function" ? (/** @type {DynamicRecord} */ (globalThis))[actionName] : undefined);
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

  const modelScope = /** @param {RuntimeElement} element */ element => {
    const scopeElement = element.closest?.("[data-teloce-loop-scope]");
    const local = scopeElement ? loopScopes.get(scopeElement.getAttribute("data-teloce-loop-scope")) : null;
    if (!local) return state;
    return new Proxy({ ...state, ...(local || {}) }, {
      get(object, key, receiver) { return Reflect.has(object, key) ? Reflect.get(object, key, receiver) : state[key]; },
      set(object, key, value) { if (Reflect.has(state, key)) state[key] = value; else object[key] = value; return true; },
    });
  };

  const modelModifiers = /** @param {RuntimeElement} element */ element => new Set(String(element.getAttribute("data-teloce-model-modifiers") || "").split(".").filter(Boolean));
  const normalizeModelValue = /** @param {DynamicValue} value @param {DynamicValue} modifiers */ (value, modifiers) => {
    if (modifiers.has("trim") && typeof value === "string") value = value.trim();
    if (modifiers.has("number") && typeof value === "string" && value.trim() !== "") {
      const number = Number(value);
      if (Number.isFinite(number)) value = number;
    }
    return value;
  };

  const syncModelValue = /** @param {RuntimeElement} element @param {DynamicValue} value */ (element, value) => {
    // Unknown expressions must not erase user input. Composition owns the DOM
    // until it commits, and normalized equality preserves spaces/caret position.
    if (value === undefined || element.__teloceModelListener?.composing) return;
    const record = element.__teloceModelListener;
    const modifiers = record?.modifiers || modelModifiers(element);
    const textControl = element.tagName === "TEXTAREA" || (element.tagName === "INPUT" && !["checkbox", "radio"].includes(element.type));
    if (textControl && modifiers.has("lazy") && document.activeElement === element && record && Object.is(record.lastValue, value)) return;
    if (record) record.lastValue = value;
    if (element.type === "checkbox") {
      element.checked = Array.isArray(value)
        ? value.map(String).includes(String(element.value)) : Boolean(value);
    } else if (element.type === "radio") {
      element.checked = String(value ?? "") === String(element.value);
    } else if (element.tagName === "SELECT" && element.multiple) {
      const selected = new Set((Array.isArray(value) ? value : []).map(String));
      Array.from(element.options).forEach(option => { option.selected = selected.has(String(option.value)); });
    } else if (String(normalizeModelValue(element.value, modifiers)) !== String(value ?? "")) {
      element.value = String(value ?? "");
    }
  };

  const removeModelListener = /** @param {RuntimeElement} element */ element => {
    const record = element.__teloceModelListener;
    if (!record) return;
    element.removeEventListener(record.eventName, record.listener);
    element.removeEventListener("compositionstart", record.compositionStart);
    element.removeEventListener("compositionend", record.compositionEnd);
    element.__teloceModelListener = null;
  };

  const bindEventsAndDirectives = /** @param {RuntimeElement} element */ element => {
    if (element.__teloceModelListener && !element.hasAttribute("data-teloce-model")) removeModelListener(element);
    const seenDirectives = new Set();
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
          const listener = /** @param {RuntimeEvent} event */ event => {
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
              if (result?.then) result.catch(/** @param {DynamicValue} error */ error => handleError(error, `event:${eventName}`, attribute.value));
            } catch (error) { handleError(error, `event:${eventName}`, attribute.value); }
          };
          const eventOptions = { once: modifiers.includes("once"), capture: modifiers.includes("capture"), passive: modifiers.includes("passive") };
          element.__teloceHandlers.set(attribute.name, { signature, actualEvent, listener, options: eventOptions });
          element.addEventListener(actualEvent, listener, eventOptions);
        }
      }

      if (attribute.name === "data-teloce-model") {
        const expression = attribute.value;
        const modifiers = modelModifiers(element);
        const eventName = modifiers.has("lazy") || element.type === "checkbox" || element.type === "radio" || element.tagName === "SELECT" ? "change" : "input";
        const signature = `${expression}:${element.type}:${eventName}:${[...modifiers].join(".")}`;
        if (element.__teloceModelListener?.signature !== signature) {
          removeModelListener(element);
          const listener = /** @param {RuntimeEvent} [event] */ event => {
            if (event?.isComposing || element.__teloceModelListener?.composing) return;
            const values = modelScope(element);
            const currentValue = __safeEvaluate(expression, values);
            let next;
            if (element.type === "checkbox" && Array.isArray(currentValue)) {
              next = [...currentValue];
              const index = next.map(String).indexOf(String(element.value));
              if (element.checked && index < 0) next.push(element.value);
              if (!element.checked && index >= 0) next.splice(index, 1);
            } else if (element.type === "checkbox") next = element.checked;
            else if (element.type === "radio") { if (!element.checked) return; next = element.value; }
            else if (element.tagName === "SELECT" && element.multiple) next = Array.from(element.selectedOptions).map(option => option.value);
            else next = element.value;
            __setSafePath(expression, normalizeModelValue(next, modifiers), values);
          };
          const compositionStart = () => { element.__teloceModelListener.composing = true; };
          const compositionEnd = () => {
            element.__teloceModelListener.composing = false;
            if (!modifiers.has("lazy")) listener();
          };
          element.__teloceModelListener = { eventName, listener, signature, modifiers, composing: false, compositionStart, compositionEnd };
          element.addEventListener(eventName, listener);
          element.addEventListener("compositionstart", compositionStart);
          element.addEventListener("compositionend", compositionEnd);
        }
        syncModelValue(element, __safeEvaluate(expression, modelScope(element)));
      }

      if (attribute.name.startsWith("data-teloce-resolved-")) {
        const name = attribute.name.slice("data-teloce-resolved-".length);
        let value;
        try { value = JSON.parse(attribute.value); } catch (_) { value = attribute.value; }
        applyBinding(element, name, value);
      }

      const directiveMatch = attribute.name.match(/^v-([\w-]+)(?:\.(.+))?$/);
      const directive = directiveMatch && (/** @type {DynamicRecord} */ (globalThis)).teloce?.directives?.[directiveMatch[1]];
      if (directive && (directive.render || directive.mounted)) {
        const name = directiveMatch[1];
        seenDirectives.add(name);
        const signature = `${name}=${attribute.value}`;
        if (!element.__teloceDirectives) element.__teloceDirectives = new Map();
        const previous = element.__teloceDirectives.get(name);
        const value = evaluate(attribute.value, state);
        let valueSignature;
        try { valueSignature = JSON.stringify(value); } catch (_) { valueSignature = String(value); }
        const context = {
          name,
          expression: attribute.value,
          value,
          oldValue: previous?.context?.value,
          state,
          modifiers: directiveMatch[2]?.split(".").filter(Boolean) || [],
        };
        if (!previous || previous.signature !== signature || previous.directive !== directive) {
          destroyDirectiveRecord(element, name, previous);
          let result;
          try {
            const mountHook = directive.render || directive.mounted;
            result = mountHook.call(directive, element, context);
          } catch (error) { handleError(error, `directive:${name}:mounted`); }
          element.__teloceDirectives.set(name, {
            signature,
            valueSignature,
            directive,
            context,
            cleanup: typeof result === "function" ? result : result?.destroy,
            update: result?.update,
          });
        } else if (previous.valueSignature !== valueSignature) {
          try {
            if (previous.update) previous.update(context);
            else directive.updated?.call(directive, element, context);
          } catch (error) { handleError(error, `directive:${name}:updated`); }
          previous.valueSignature = valueSignature;
          previous.context = context;
        }
      }
    }
    for (const [name, record] of element.__teloceDirectives || []) {
      if (seenDirectives.has(name)) continue;
      destroyDirectiveRecord(element, name, record);
      element.__teloceDirectives.delete(name);
    }
    bindAdvancedDirectives(element);
  };

  const mountChildren = () => {
    const lookup = new Map(Object.entries(components).map(([name, value]) => [name.toLowerCase(), value]));
    const newlyMounted = new Set();
    let found = true;
    while (found) {
      found = false;
      for (const element of Array.from(/** @type {RuntimeElement} */ (target).querySelectorAll("*"))) {
        const child = lookup.get(element.tagName.toLowerCase());
        if (!child || element.__teloceMounted || typeof child.mount !== "function") continue;
        element.__teloceMounted = true;
        element.__teloceInstance = (element.hasAttribute("data-teloce-ssr-boundary") && child.hydrate ? child.hydrate : child.mount)(element, readProps(element.__telocePendingPropsSource || element, state));
        element.__telocePendingPropsSource = undefined;
        newlyMounted.add(element);
        found = true;
        break;
      }
    }
    for (const element of Array.from(/** @type {RuntimeElement} */ (target).querySelectorAll("*"))) {
      if (lookup.has(element.tagName.toLowerCase()) && !newlyMounted.has(element) && element.__teloceInstance?.updateProps) {
        const source = element.__telocePendingPropsSource || element;
        element.__teloceInstance.updateProps(readProps(source, state));
        element.__telocePendingPropsSource = undefined;
      }
    }
    /** @type {RuntimeElement} */ (target).querySelectorAll("teloce-dynamic").forEach(/** @param {RuntimeElement} element */ element => {
      const name = evaluate(element.getAttribute("data-teloce-is") || "", state);
      const child = lookup.get(String(name).toLowerCase());
      if (!element.__teloceMounted && child?.mount) {
        element.__teloceMounted = true;
        element.__teloceInstance = (element.hasAttribute("data-teloce-ssr-boundary") && child.hydrate ? child.hydrate : child.mount)(element, readProps(element.__telocePendingPropsSource || element, state));
      } else if (element.__teloceInstance?.updateProps) {
        element.__teloceInstance.updateProps(readProps(element, state));
      }
    });
  };

  /** @type {Map<string, Node>} */
  let directTextNodes = new Map();
  /** @type {Map<string, RuntimeElement>} */
  let directBindingNodes = new Map();
  let directBound = false;
  const regionNodes = new Map();

  const directNeedsUpdate = /** @param {{dependencies?: string[]}} record @param {Set<string> | null} changed */ (record, changed) => {
    if (!changed || !changed.size || changed.has("*")) return true;
    const dependencies = Array.isArray(record.dependencies) ? record.dependencies : [];
    return !dependencies.length || dependencies.includes("*") || dependencies.some(/** @param {DynamicValue} dependency */ dependency => changed.has(String(dependency).split(".")[0]));
  };

  const bindDirectNodes = () => {
    if (!directEnabled || !target) return;
    directTextNodes = new Map();
    directBindingNodes = new Map();
    const walker = document.createTreeWalker(target, 0xFFFFFFFF, {
      acceptNode(node) {
        if (node.nodeType === 1 && /** @type {RuntimeElement} */ (node).__teloceInstance) return 2;
        return node.nodeType === 8 ? 1 : 3;
      },
    });
    let current = walker.nextNode();
    while (current) {
      const match = String(current.nodeValue || "").match(/^teloce-text:([\w$-]+)$/);
      // The marker is a stable comment; the following text node carries the
      // rendered value and is the node that direct updates must mutate.
      if (match) {
        let text = current.nextSibling;
        // HTML parsing omits empty text nodes. Never bind the closing
        // comment as the value node: that would keep later text invisible.
        if (text?.nodeType !== 3) {
          text = document.createTextNode('');
          /** @type {Node} */ (current.parentNode).insertBefore(text, current.nextSibling);
        }
        directTextNodes.set(match[1], text);
      }
      const regionStart = String(current.nodeValue || '').match(/^teloce-region:([\w$-]+)$/);
      const regionEnd = String(current.nodeValue || '').match(/^teloce-region-end:([\w$-]+)$/);
      if (regionStart) regionNodes.set(regionStart[1], {
        start: current, scopes: new Set(), ...(initialRowCaches.get(regionStart[1]) || {}),
      });
      if (regionEnd && regionNodes.has(regionEnd[1])) {
        const region = regionNodes.get(regionEnd[1]);
        region.end = current;
        for (let node = region.start.nextSibling; node && node !== current; node = node.nextSibling) {
          if (node.nodeType !== 1) continue;
          const rows = [node, ...node.querySelectorAll('[data-teloce-loop-scope]')];
          for (const row of rows) {
            const id = row.getAttribute('data-teloce-loop-scope');
            if (id != null) {
              region.scopes.add(id);
              const cached = region.byScope?.get(id);
              if (cached) cached.node = row;
            }
          }
        }
        delete region.byScope;
      }
      current = walker.nextNode();
    }
    /** @type {RuntimeElement} */ (target).querySelectorAll("[data-teloce-direct-bindings]").forEach(/** @param {RuntimeElement} element */ element => {
      for (const id of String(element.getAttribute("data-teloce-direct-bindings") || "").split(",").filter(Boolean)) {
        directBindingNodes.set(id, element);
      }
    });
    initialRowCaches.clear();
    directBound = true;
  };

  const updateDirectNodes = /** @param {Set<string> | null} changed */ changed => {
    if (!directEnabled || !directBound) return;
    /** @type {Iterable<DirectBinding>} */
    let records = directBindings;
    if (changed?.size && !changed.has('*')) {
      const affected = new Set(alwaysBindings);
      for (const dependency of changed) for (const record of bindingIndex.get(dependency) || []) affected.add(record);
      records = affected;
    }
    for (const record of records) {
      if (!directNeedsUpdate(record, changed)) continue;
      try {
        const value = record.read ? record.read(state) : evaluate(record.expression, state);
        if (record.kind === "text") {
          const node = directTextNodes.get(record.id);
          if (node && node.nodeValue !== String(value ?? "")) node.nodeValue = String(value ?? "");
        } else {
          const element = directBindingNodes.get(record.id);
          if (!element) continue;
          if (record.name === "model" || record.name.startsWith("model.")) {
            syncModelValue(element, value);
          } else {
            applyBinding(element, record.name, value);
          }
        }
      } catch (error) {
        handleError(error, `direct:${record.kind}`);
      }
    }
  };

  const updateKeyedRows = /** @param {DirectRegion} record @param {DynamicRecord} region */ (record, region) => {
    const plan = record.rows;
    if (!plan) return false;
    const values = evaluate(plan.collection, state);
    if (!Array.isArray(values)) return false;
    // Each row retains its own dependency snapshot and live event scope.
    // Collection notifications can scan snapshots without parsing or patching
    // unchanged rows. Complex expressions use the general region path.
    if (!region.rows) {
      region.rows = new Map();
      for (const id of region.scopes) loopScopes.delete(id);
    }
    if (!region.rowReaders) {
      const prepared = prepareRowCache(plan);
      region.rowRoots = prepared.rowRoots;
      region.rowReaders = prepared.rowReaders;
    }
    const rows = region.rows, active = new Set(), next = [], ordered = /** @type {DynamicValue[]} */ ([]);
    for (let index = 0; index < values.length; index++) {
      const item = values[index];
      const locals = { [plan.item]: item, index };
      /** @type {DynamicRecord} */
      const scope = { ...locals, [loopLocals]: locals };
      for (const root of region.rowRoots) if (!(root in locals) && Object.prototype.hasOwnProperty.call(state, root)) scope[root] = state[root];
      const key = String(evaluate(plan.key, scope));
      if (active.has(key)) throw new Error(`Duplicate keyed loop value: ${key}`);
      active.add(key);
      const snapshot = region.rowReaders.map(/** @param {DynamicValue} read */ read => read(scope));
      let row = rows.get(key);
      if (!row) row = { scopeId: String(loopScopeSequence++), snapshot: null, node: null };
      loopScopes.set(row.scopeId, locals);
      const dirty = !row.snapshot || snapshot.some(/** @param {DynamicValue} value @param {number} i */ (value, i) =>
        (value !== null && typeof value === 'object') || !Object.is(value, row.snapshot[i]));
      row.needsBind = dirty;
      if (dirty) {
        const scopes = new Map();
        let markup = renderTemplate(plan.body, scope, scopes);
        markup = markup.replace(/<([A-Za-z][\w:-]*)(?=[\s>])/, `$& data-teloce-loop-scope="${row.scopeId}"`);
        if (!row.node || markup !== row.markup) {
          const template = document.createElement('template'); template.innerHTML = markup;
          const nodes = Array.from(template.content.childNodes);
          // Compiler restricts this path to one root element. Whitespace is
          // discarded here; multi-root or nested structural loops fall back.
          const element = nodes.find(node => node.nodeType === 1);
          if (!element) return false;
          next.push(element);
        } else next.push(row.node);
        row.markup = markup;
        row.snapshot = snapshot;
      } else next.push(row.node);
      rows.set(key, row); ordered.push(row);
    }
    const sameOrder = region.order?.length === ordered.length && ordered.every((row, index) => row === region.order[index]);
    const changedRoots = sameOrder ? next.reduce((count, node, index) => count + (node !== ordered[index].node ? 1 : 0), 0) : 0;
    if (sameOrder && changedRoots <= 1) {
      // A data edit does not need whole-list reconciliation. Patch only roots
      // whose rendered markup changed, retaining the normal disposal/focus hooks.
      for (let index = 0; index < ordered.length; index++) {
        const row = ordered[index];
        if (next[index] === row.node) continue;
        __patch(region.start.parentNode, null, {
          ...__teloceTransitionHooks(definition), onDispose: cleanupElement,
          start: row.node.previousSibling, end: row.node.nextSibling, nodes: [next[index]],
          /** @param {DynamicValue} nodes */ onNodes(nodes) { row.node = nodes[0]; },
        });
      }
    } else {
      __patch(region.start.parentNode, null, {
        ...__teloceTransitionHooks(definition), onDispose: cleanupElement,
        start: region.start, end: region.end, nodes: next,
        /** @param {DynamicValue} nodes */ onNodes(nodes) { nodes.forEach(/** @param {RuntimeElement} node @param {number} index */ (node, index) => { ordered[index].node = node; }); },
      });
    }
    region.order = ordered;
    for (const [key, row] of rows) if (!active.has(key)) { loopScopes.delete(row.scopeId); rows.delete(key); }
    region.scopes = new Set(ordered.map(row => row.scopeId));
    for (const row of ordered) {
      if (row.needsBind) {
        bindEventsAndDirectives(row.node); row.node.querySelectorAll('*').forEach(bindEventsAndDirectives);
      }
    }
    return true;
  };

  const update = (/** @type {Set<string> | null} */ changed = null) => {
    if (destroyed || !target || rendering) return;
    const wasMounted = mounted;
    rendering = true;
    if (wasMounted) callHook("beforeUpdate");
    else callHook("beforeMount");
    try {
      if (wasMounted && directEnabled && (!directPlan.structural || directPlan.targetedStructural)) {
        updateDirectNodes(changed);
        for (const record of directRegions) {
          if (!directNeedsUpdate(record, changed)) continue;
          const region = regionNodes.get(record.id);
          if (!region?.start?.parentNode || region.start.parentNode !== region.end?.parentNode) continue;
          if (record.rows && updateKeyedRows(record, region)) continue;
          if (region.rows) {
            for (const row of region.rows.values()) loopScopes.delete(row.scopeId);
            region.rows = null;
          }
          const freshScopes = new Map();
          const html = renderTemplate(record.template, state, freshScopes);
          __patch(region.start.parentNode, html, {
            ...__teloceTransitionHooks(definition), onDispose: cleanupElement,
            start: region.start, end: region.end,
          });
          for (const id of region.scopes) loopScopes.delete(id);
          region.scopes = new Set(freshScopes.keys());
          for (const [id, scope] of freshScopes) loopScopes.set(id, scope);
          for (let node = region.start.nextSibling; node && node !== region.end; node = node.nextSibling) {
            if (node.nodeType !== 1) continue;
            bindEventsAndDirectives(node);
            node.querySelectorAll('*').forEach(bindEventsAndDirectives);
          }
        }
        // A component with no child registrations has no reason to walk its
        // static subtree on every state change. This is the key difference
        // between the targeted path and the compatibility renderer.
        if (Object.keys(components).length) mountChildren();
        if (directPlan.refreshIntegrations) /** @type {RuntimeElement} */ (target).querySelectorAll("*").forEach(bindEventsAndDirectives);
      } else {
        loopScopes = new Map();
        loopScopeSequence = 0;
        const transitions = __teloceTransitionHooks(definition);
        __patch(target, renderTemplate(template, state, loopScopes), {
          ...transitions,
          onDispose: cleanupElement,
        });
        /** @type {RuntimeElement} */ (target).querySelectorAll("*").forEach(bindEventsAndDirectives);
        mountChildren();
        if (directEnabled && !directBound) {
          bindDirectNodes();
        }
      }
    } finally {
      rendering = false;
    }
    if (!wasMounted) {
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
          if (result?.then) result.catch(/** @param {DynamicValue} error */ error => handleError(error, `watch:${name}`));
        } catch (error) { handleError(error, `watch:${name}`); }
        previousWatchValues[name] = value;
      }
    }
    syncQueryState();
  };

  const signalCleanups = /** @type {Array<() => void>} */ ([]);
  const seedProp = /** @param {string} name @param {DynamicValue} value */ (name, value) => {
    const current = state[name];
    if (typeof current === 'function' && typeof current.subscribe === 'function' && value && typeof value === 'object' && Object.keys(value).length === 1 && 'value' in value) current.value = value.value;
    else state[name] = value;
  };
  const subscribeSignals = () => {
    if (signalCleanups.length) return;
    for (const [name, descriptor] of Object.entries(Object.getOwnPropertyDescriptors(state))) {
      const value = descriptor.value;
      if (typeof value === 'function' && typeof value.subscribe === 'function') signalCleanups.push(value.subscribe(() => requestUpdate(name)));
    }
  };
  const normalizedProps = normalizeProps(options.props || {});
  suppressUpdates = true;
  for (const [name, value] of Object.entries(normalizedProps)) seedProp(name, value);
  previousWatchValues = Object.fromEntries(Object.keys(definition?.watch || {}).map(name => [name, watchValue(name)]));
  callHook("beforeCreate");
  callHook("created");
  suppressUpdates = false;

  const hmrRegistry = (/** @type {DynamicRecord} */ (globalThis)).__teloce_hmr_instances ||= new Map();
  const hmrKey = moduleUrl || definition?.name || "component";
  const hmrRecord = {
    target: /** @type {RuntimeElement | null} */ (null),
    state,
    reload: async () => {
      if (!target || destroyed || !moduleUrl) return;
      const oldTarget = target;
      /** @type {DynamicRecord} */
      const snapshot = {};
      for (const [key, value] of Object.entries(state)) if (!key.startsWith("$") && typeof value !== "function") snapshot[key] = value;
      instance.unmount();
      const fresh = await import(`${moduleUrl.split("?")[0]}?teloce_hmr=${Date.now()}`);
      return fresh.mount(oldTarget, snapshot);
    },
  };
  if (!(/** @type {DynamicRecord} */ (globalThis)).__teloce_hmr_reload) (/** @type {DynamicRecord} */ (globalThis)).__teloce_hmr_reload = async () => {
    const records = [...hmrRegistry.values()].flatMap(set => [...set]);
    for (const record of records) await record.reload();
  };

  const instance = {
    state,
    update,
    updateProps(/** @type {DynamicRecord} */ nextProps = {}) {
      const normalized = normalizeProps(nextProps);
      suppressUpdates = true;
      let changed = false;
      const changedKeys = new Set();
      try {
        const nextAttrs = nextProps?.$attrs || nextProps?.__attrs || {};
        const filteredAttrs = Object.fromEntries(Object.entries(nextAttrs).filter(([name]) => !declaredPropNames.has(camelizeProp(name)) && !name.startsWith("data-teloce-")));
        if (JSON.stringify(state.$attrs) !== JSON.stringify(filteredAttrs)) { state.$attrs = filteredAttrs; changed = true; changedKeys.add("$attrs"); }
        for (const [key, value] of Object.entries(normalized)) if (!Object.is(state[key], value)) { seedProp(key, value); changed = true; changedKeys.add(key); }
        for (const key of Object.keys(propDefinitions)) if (!(key in normalized) && state[key] !== undefined) { state[key] = undefined; changed = true; changedKeys.add(key); }
      } finally { suppressUpdates = false; }
      if (changed) update(changedKeys);
      return instance;
    },
    /** @param {string | Element | null} nextTarget */ mount(nextTarget, /** @type {DynamicRecord} */ props = {}) {
      const nextMountTarget = typeof nextTarget === "string" ? document.querySelector(nextTarget) : nextTarget;
      if (!nextMountTarget) throw new Error("Teloce mount target was not found");
      if (mounted) instance.unmount();
      target = nextMountTarget;
      destroyed = false;
      schedulerVersion += 1;
      registerQueryListener();
      subscribeSignals();
      hmrRecord.target = target;
      if (!hmrRegistry.has(hmrKey)) hmrRegistry.set(hmrKey, new Set());
      hmrRegistry.get(hmrKey).add(hmrRecord);
      if (props && props !== options.props && Object.keys(props).length) {
        const mountingTarget = target; target = null;
        try { instance.updateProps(props); } finally { target = mountingTarget; }
      }
      const hydrating = Boolean(options.hydrate || target.getAttribute('data-teloce-ssr') === '1');
      const controls = hydrating ? [.../** @type {RuntimeElement} */ (target).querySelectorAll('input,textarea,select')].map(element => ({
        element, value: element.value, checked: element.checked,
        start: element.selectionStart, end: element.selectionEnd,
        active: document.activeElement === element,
      })) : [];
      if (hydrating) {
        const expected = document.createElement('template');
        expected.innerHTML = renderTemplate(template, state, new Map());
        const componentTags = new Set(Object.keys(components).map(name => name.toUpperCase()));
        const marker = target.getAttribute('data-teloce-ssr');
        if ((marker && marker !== '1') || __hydrationShape(target, componentTags) !== __hydrationShape(expected.content, componentTags)) {
          const error = new Error('Server and client component structures differ; reconciling this component');
          if (dev) handleError(error, 'hydration');
          else reportTeloceError(error, { category: 'hydration', component: options.component });
        }
      }
      update();
      for (const control of controls) {
        if (!control.element.isConnected) continue;
        control.element.value = control.value; control.element.checked = control.checked;
        if (control.active) {
          control.element.focus();
          if (control.start != null) control.element.setSelectionRange?.(control.start, control.end);
        }
      }
      target.removeAttribute('data-teloce-ssr');
      target.removeAttribute('data-teloce-ssr-boundary');
      return instance;
    },
    unmount() {
      if (!target || destroyed) return instance;
      callHook("deactivated");
      callHook("beforeUnmount");
      const nodes = Array.from(/** @type {RuntimeElement} */ (target).querySelectorAll("*")).reverse();
      for (const element of nodes) {
        try { element.__teloceInstance?.unmount?.(); } catch (error) { handleError(error, "child:unmount"); }
        cleanupElement(element);
        element.__teloceMounted = false;
        element.__teloceInstance = undefined;
      }
      target.replaceChildren();
      for (const cleanup of signalCleanups.splice(0)) {
        try { cleanup(); } catch (error) { handleError(error, "signal:cleanup"); }
      }
      directTextNodes.clear();
      directBindingNodes.clear();
      regionNodes.clear();
      initialRowCaches.clear();
      loopScopes.clear();
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

  /** @type {DynamicRecord} */ (instance).__teloceStyle = style;
  if (style && typeof document !== "undefined" && !document.querySelector(`style[data-teloce-style="${styleId}"]`)) {
    const styleElement = document.createElement("style");
    styleElement.setAttribute("data-teloce-style", styleId);
    styleElement.textContent = style;
    (document.head || document.documentElement).appendChild(styleElement);
  }
  return instance;
};

export { __teloceCreateCompiledComponent, __teloceLazy };

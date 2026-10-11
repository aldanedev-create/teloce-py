/** Standalone browser mounting, plugin registration and directive evaluation. @module */
/* Teloce standalone runtime for Jinja/static HTML and CDN-style usage. */
(/** @param {DynamicRecord} root */ function (root) {
  "use strict";
  /** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent} from './contracts.js' */

  /** @type {Record<string, DynamicCallback>} */ const filters = {
    uppercase: /** @param {DynamicValue} value */ value => String(value ?? "").toUpperCase(),
    lowercase: /** @param {DynamicValue} value */ value => String(value ?? "").toLowerCase(),
    trim: /** @param {DynamicValue} value */ value => String(value ?? "").trim(),
    capitalize: /** @param {DynamicValue} value */ value => { const text = String(value ?? ""); return text ? text[0].toUpperCase() + text.slice(1) : text; },
    slugify: /** @param {DynamicValue} value */ value => String(value ?? "").trim().toLowerCase().replace(/[^\w\s-]/g, "").replace(/[\s_-]+/g, "-").replace(/^-+|-+$/g, ""),
    truncate: /** @param {DynamicValue} value */ (value, length = 30, suffix = "...") => { const text = String(value ?? ""); const size = Number(length); return text.length > size ? text.slice(0, Math.max(0, size - String(suffix).length)) + suffix : text; },
    currency: /** @param {DynamicValue} value */ (value, currency = "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency: String(currency).toUpperCase() }).format(Number(value) || 0),
    percent: /** @param {DynamicValue} value */ (value, digits = 0) => `${(Number(value) * 100).toFixed(Number(digits))}%`,
    number: /** @param {DynamicValue} value @param {DynamicValue} locale */ (value, locale) => new Intl.NumberFormat(locale || undefined).format(Number(value) || 0),
    first: /** @param {DynamicValue} value */ value => Array.isArray(value) ? value[0] : value,
    last: /** @param {DynamicValue} value */ value => Array.isArray(value) ? value[value.length - 1] : value,
    pluck: /** @param {DynamicValue} value @param {DynamicValue} key */ (value, key) => Array.isArray(value) ? value.map(item => item == null ? undefined : item[key]) : value,
    orderBy: /** @param {DynamicValue} value @param {DynamicValue} key */ (value, key, direction = "asc") => Array.isArray(value) ? [...value].sort((a, b) => { const left = key == null ? a : a?.[key]; const right = key == null ? b : b?.[key]; const result = left < right ? -1 : left > right ? 1 : 0; return String(direction).toLowerCase() === "desc" ? -result : result; }) : value,
    json: /** @param {DynamicValue} value */ value => JSON.stringify(value),
    join: /** @param {DynamicValue} value */ (value, separator = ", ") => Array.isArray(value) ? value.join(separator) : value,
  };
  const plugins = /** @type {DynamicRecord[]} */ ([]);
  const directives = Object.create(null);
  const components = Object.create(null);
  const helpers = Object.create(null);
  const escapeHtml = /** @param {DynamicValue} value */ value => String(value ?? "").replace(/[&<>\"']/g, c => (/** @type {Record<string, string>} */ ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]));
  const sanitizeHtml = /** @param {DynamicValue} value */ value => {
    if (runtimeConfig.allowRawHtml) return String(value ?? "");
    const template = document.createElement("template");
    template.innerHTML = String(value ?? "");
    template.content.querySelectorAll("script,iframe,object,embed,link,meta,base").forEach(node => node.remove());
    template.content.querySelectorAll("*").forEach(node => {
      for (const attribute of Array.from(node.attributes)) {
        const name = attribute.name.toLowerCase();
        const text = attribute.value.trim().toLowerCase();
        if (name.startsWith("on") || ((name === "href" || name === "src" || name === "action" || name === "formaction") && /^(?:javascript|vbscript|data):/.test(text))) node.removeAttribute(attribute.name);
      }
    });
    return template.innerHTML;
  };
  const splitArguments = /** @param {DynamicValue} source */ source => { const result = []; let start = 0; let depth = 0; let quote = ""; for (let index = 0; index < String(source).length; index += 1) { const character = String(source)[index]; if (quote) { if (character === quote && source[index - 1] !== "\\") quote = ""; continue; } if (character === "'" || character === '"') { quote = character; continue; } if ("([{".includes(character)) depth += 1; else if (")] }".replace(/\s/g, "").includes(character)) depth -= 1; else if (character === "," && depth === 0) { result.push(String(source).slice(start, index).trim()); start = index + 1; } } if (String(source).slice(start).trim()) result.push(String(source).slice(start).trim()); return result; };
  const splitStatements = /** @param {DynamicValue} source */ source => { const result = []; let start = 0; let depth = 0; let quote = ""; const text = String(source); for (let index = 0; index < text.length; index += 1) { const character = text[index]; if (quote) { if (character === quote && text[index - 1] !== "\\") quote = ""; continue; } if (character === "'" || character === '"') { quote = character; continue; } if ("([{".includes(character)) depth += 1; else if (")] }".replace(/\s/g, "").includes(character)) depth -= 1; else if ((character === ";" || character === ",") && depth === 0) { result.push(text.slice(start, index).trim()); start = index + 1; } } if (text.slice(start).trim()) result.push(text.slice(start).trim()); return result; };
  const readPath = /** @param {string} expression @param {DynamicRecord} scope */ (expression, scope) => {
    const path = String(expression).trim().match(/^[\w$]+(?:\.[\w$]+|\[[^\]]+\])*$/);
    if (!path) return undefined;
    const parts = path[0].replace(/\[\s*["']?([^\]"']+)["']?\s*\]/g, ".$1").split(".");
    const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]);
    if (parts.some(part => blocked.has(part))) return undefined;
    let value = scope?.[parts[0]] ?? helpers[parts[0]];
    for (const part of parts.slice(1)) value = value?.[part];
    return value;
  };
  const safeEvaluate = /** @returns {DynamicValue} @param {string | undefined} expression @param {DynamicRecord} scope */ (expression, scope) => {
    let source = String(expression ?? "").trim();
    while (source.startsWith("(") && source.endsWith(")")) source = source.slice(1, -1).trim();
    if (source.startsWith("!") && !source.startsWith("!==")) return !safeEvaluate(source.slice(1), scope);
    const ternary = source.match(/^(.+?)\?(.+?):(.+)$/);
    if (ternary) return safeEvaluate(ternary[1], scope) ? safeEvaluate(ternary[2], scope) : safeEvaluate(ternary[3], scope);
    const binary = source.match(/^(.+?)\s*(===|!==|==|!=|>=|<=|>|<|&&|\|\||\+|-|\*|\/)\s*(.+)$/);
    if (binary) { const left = /** @type {DynamicValue} */ (safeEvaluate(binary[1], scope)); const right = /** @type {DynamicValue} */ (safeEvaluate(binary[3], scope)); switch (binary[2]) { case "===": return left === right; case "!==": return left !== right; case "==": return left == right; case "!=": return left != right; case ">=": return left >= right; case "<=": return left <= right; case ">": return left > right; case "<": return left < right; case "&&": return left && right; case "||": return left || right; case "+": return left + right; case "-": return left - right; case "*": return left * right; case "/": return left / right; } }
    if (source === "true") return true; if (source === "false") return false; if (source === "null") return null; if (source === "undefined") return undefined;
    if (/^-?(?:\d+\.?\d*|\.\d+)$/.test(source)) return Number(source);
    if ((source.startsWith('"') && source.endsWith('"')) || (source.startsWith("'") && source.endsWith("'"))) return source.slice(1, -1);
    if (source.startsWith("[") && source.endsWith("]")) return splitArguments(source.slice(1, -1)).map(item => safeEvaluate(item, scope));
    const call = source.match(/^([\w$]+(?:\.[\w$]+)*)\((.*)\)$/s);
    if (call) { const pathParts = call[1].split("."); const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]); if (pathParts.some(part => blocked.has(part))) return undefined; const owner = pathParts.length > 1 ? readPath(pathParts.slice(0, -1).join("."), scope) : scope; const fn = pathParts.length > 1 ? owner?.[pathParts[pathParts.length - 1]] : (scope?.[call[1]] ?? helpers[call[1]]); return typeof fn === "function" ? fn.apply(owner, splitArguments(call[2]).map(item => safeEvaluate(item, scope))) : undefined; }
    return readPath(source, scope);
  };
  // Expressions are intentionally interpreted by the constrained evaluator.
  // Standalone/Jinja pages must remain safe even when their HTML is untrusted;
  // there is no runtime switch that enables dynamic JavaScript construction.
  const runtimeConfig = { unsafeEval: false, allowRawHtml: false };
  const evaluate = /** @param {string | undefined} expression @param {DynamicRecord} scope */ (expression, scope) => {
    try {
      const parts = String(expression).split(/\s+\|\s+/);
      let value = safeEvaluate(parts.shift(), scope);
      for (const part of parts) {
        const match = part.match(/^([\w$]+)(?:\((.*)\)|(?::(.*)))?$/);
        const argumentsSource = match?.[2] ?? match?.[3];
        if (match && filters[match[1]]) value = filters[match[1]](value, ...(argumentsSource ? splitArguments(argumentsSource).map(item => safeEvaluate(item, scope)) : []));
      }
      return value;
    } catch (_) { return ""; }
  };
  const assign = /** @param {string} expression @param {DynamicValue} value @param {DynamicRecord} scope */ (expression, value, scope) => {
    try { const parts = String(expression).trim().split(".").filter(Boolean); const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]); if (!parts.length || parts.some(part => blocked.has(part))) return; let target = scope; for (const part of parts.slice(0, -1)) target = target?.[part]; if (target != null) target[parts[parts.length - 1]] = value; } catch (_) {}
  };
  const runEventExpression = /** @param {string} expression @param {DynamicRecord} state @param {RuntimeEvent} event */ (expression, state, event) => {
    const source = String(expression).trim();
    const method = source.match(/^([\w$]+)\s*$/);
    if (method && typeof state[method[1]] === "function") return state[method[1]].call(state, event);
    const call = source.match(/^([\w$]+)\s*\(\s*\)$/);
    if (call && typeof state[call[1]] === "function") return state[call[1]].call(state, event);
    let result;
    let statementsSource = source.replace(/;\s*$/, "").trim();
    if (statementsSource.startsWith("(") && statementsSource.endsWith(")")) statementsSource = statementsSource.slice(1, -1);
    for (const statement of splitStatements(statementsSource)) {
      const part = statement.trim();
      if (!part) continue;
      const change = part.match(/^(.+?)(\+\+|--)$/);
      if (change) { const current = safeEvaluate(change[1], state); assign(change[1], Number(current || 0) + (change[2] === "++" ? 1 : -1), state); result = current; continue; }
      const assignment = part.match(/^(.+?)\s*(\+=|-=|\*=|\/=|=)\s*(.+)$/);
      if (assignment) { const current = safeEvaluate(assignment[1], state); const right = safeEvaluate(assignment[3], state); const value = assignment[2] === "=" ? right : assignment[2] === "+=" ? current + right : assignment[2] === "-=" ? current - right : assignment[2] === "*=" ? current * right : current / right; assign(assignment[1], value, state); result = value; continue; }
      result = evaluate(part, state);
    }
    return result;
  };
  const registerPluginDirectives = /** @param {DynamicRecord} plugin */ plugin => {
    if (Array.isArray(plugin?.directives)) {
      for (const directive of plugin.directives) if (directive?.name) directives[directive.name] = directive;
    } else if (plugin?.directives && typeof plugin.directives === "object") {
      Object.assign(directives, plugin.directives);
    }
  };
  const registerComponent = /** @param {string | DynamicRecord} name @param {DynamicValue} component */ (name, component) => {
    if (name && typeof name === "object") {
      component = name.component || name;
      name = name.name;
    }
    if (name && component) components[String(name).toLowerCase()] = component;
  };
  const registerHelper = /** @param {string} name @param {DynamicValue} helper */ (name, helper) => {
    if (name && helper !== undefined) helpers[name] = helper;
  };
  const registerPluginComponents = /** @param {DynamicRecord} plugin */ plugin => {
    if (Array.isArray(plugin?.components)) {
      for (const entry of plugin.components) registerComponent(entry?.name, entry?.component || entry);
    } else if (plugin?.components && typeof plugin.components === "object") {
      for (const [name, component] of Object.entries(plugin.components)) registerComponent(name, component?.component || component);
    }
  };
  const renderLoops = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope) => source.replace(/<for\s+[^>]*item="([^"]*)"[^>]*in="([^"]*)"[^>]*>([\s\S]*?)<\/for>/g, /** @param {DynamicValue} _ @param {DynamicValue} item @param {DynamicValue} collection @param {DynamicValue} body */ (_, item, collection, body) => {
    const values = evaluate(collection, scope) || [];
    return Array.from(values).map((value, index) => render(body, { ...scope, [item]: value, index })).join("");
  });
  const renderLongFormLoops = /** @param {DynamicValue} source @param {DynamicRecord} scope @param {DynamicValue} loopScopes */ (source, scope, loopScopes) => source.replace(/<([A-Za-z][\w:-]*)([^>]*?)v-for="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>/g, /** @param {DynamicValue} _ @param {string} tag @param {DynamicValue} before @param {string} expression @param {DynamicValue} after @param {DynamicValue} body */ (_, tag, before, expression, after, body) => {
    const match = expression.match(/^\s*(?:\(([^)]+)\)|([^\s]+))\s+(?:in|of)\s+(.+?)\s*$/);
    if (!match) return _;
    const variables = (match[1] || match[2]).split(",").map(/** @param {DynamicValue} value */ value => value.trim());
    const values = evaluate(match[3], scope) || [];
    return Array.from(values).map((value, index) => {
      const itemScope = { ...scope, [variables[0]]: value, [variables[1] || "index"]: index, index };
      const token = `loop-${loopScopes.size}`;
      loopScopes.set(token, itemScope);
      const content = render(body, itemScope, loopScopes);
      return `<${tag}${before.replace(/:key="[^"]*"|v-bind:key="[^"]*"/g, "")}${after} data-teloce-loop-scope="${token}">${content}</${tag}>`;
    }).join("");
  });
  const renderLongFormConditionals = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope) => {
    const stripBranch = /** @param {DynamicValue} attributes */ attributes => attributes.replace(/\s+v-(?:if|else-if|else)(?:="[^"]*")?/g, "");
    let output = source;
    const branchPattern = /<([A-Za-z][\w:-]*)([^>]*?)v-if="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>\s*<\1([^>]*?)v-(else-if|else)(?:="([^"]*)")?([^>]*)>([\s\S]*?)<\/\1>/g;
    let previous;
    do {
      previous = output;
      output = output.replace(branchPattern, /** @param {DynamicValue} _ @param {string} tag @param {DynamicValue} firstBefore @param {DynamicValue} condition @param {DynamicValue} firstAfter @param {DynamicValue} yes @param {DynamicValue} secondBefore @param {DynamicValue} branch @param {DynamicValue} branchCondition @param {DynamicValue} secondAfter @param {DynamicValue} no */ (_, tag, firstBefore, condition, firstAfter, yes, secondBefore, branch, branchCondition, secondAfter, no) => {
        const firstAttributes = stripBranch(`${firstBefore}${firstAfter}`);
        if (evaluate(condition, scope)) return `<${tag}${firstAttributes}>${yes}</${tag}>`;
        if (branch === "else") return `<${tag}${stripBranch(`${secondBefore}${secondAfter}`)}>${no}</${tag}>`;
        const nextAttributes = stripBranch(`${secondBefore}${secondAfter}`);
        return `<${tag}${nextAttributes} v-if="${String(branchCondition || "").replace(/"/g, "&quot;")}">${no}</${tag}>`;
      });
    } while (output !== previous && /v-(?:if|else-if|else)=?/.test(output));
    return output;
  };
  const renderLongFormIfs = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope) => source.replace(/<([A-Za-z][\w:-]*)([^>]*?)v-if="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>/g, /** @param {DynamicValue} _ @param {string} tag @param {DynamicValue} before @param {DynamicValue} condition @param {DynamicValue} after @param {DynamicValue} body */ (_, tag, before, condition, after, body) => evaluate(condition, scope) ? `<${tag}${before}${after}>${body}</${tag}>` : "");
  const render = /** @param {DynamicValue} source @param {DynamicRecord} scope */ (source, scope, loopScopes = new Map()) => {
    let output = renderLongFormLoops(source, scope, loopScopes);
    output = renderLongFormConditionals(output, scope);
    output = renderLongFormIfs(output, scope);
    output = renderLoops(output, scope);
    output = output.replace(/<if\s+(?:condition|test)="([^"]*)">([\s\S]*?)(?:<else>([\s\S]*?))?<\/if>/g, /** @param {DynamicValue} _ @param {DynamicValue} test @param {DynamicValue} yes @param {DynamicValue} no */ (_, test, yes, no) => evaluate(test, scope) ? yes : (no || ""));
    output = output.replace(/{{\s*([^{}]+?)\s*}}/g, /** @param {DynamicValue} _ @param {string} expression */ (_, expression) => escapeHtml(evaluate(expression, scope)));
    output = output.replace(/@([\w.-]+)="([^"]*)"/g, 'data-teloce-event-$1="$2"');
    output = output.replace(/v-on:([\w.-]+)="([^"]*)"/g, 'data-teloce-event-$1="$2"');
    output = output.replace(/v-model="([^"]*)"/g, 'data-teloce-model="$1"');
    output = output.replace(/:([\w-]+)="([^"]*)"/g, /** @param {DynamicValue} _ @param {string} name @param {string} expression */ (_, name, expression) => name === "model" ? `data-teloce-model="${expression}"` : `${name}="${String(evaluate(expression, scope) ?? "").replace(/\"/g, "&quot;")}"`);
    output = output.replace(/v-bind:([\w-]+)="([^"]*)"/g, /** @param {DynamicValue} _ @param {string} name @param {string} expression */ (_, name, expression) => `data-teloce-bind-${name}="${String(evaluate(expression, scope) ?? "").replace(/\"/g, "&quot;")}"`);
    output = output.replace(/v-show="([^"]*)"/g, /** @param {DynamicValue} _ @param {string} expression */ (_, expression) => `data-teloce-bind-show="${String(evaluate(expression, scope) ?? "").replace(/\"/g, "&quot;")}"`);
    output = output.replace(/v-text="([^"]*)"/g, /** @param {DynamicValue} _ @param {string} expression */ (_, expression) => `data-teloce-bind-text="${String(evaluate(expression, scope) ?? "").replace(/\"/g, "&quot;")}"`);
    output = output.replace(/v-html="([^"]*)"/g, /** @param {DynamicValue} _ @param {string} expression */ (_, expression) => `data-teloce-bind-html="${String(evaluate(expression, scope) ?? "").replace(/\"/g, "&quot;")}"`);
    return output;
  };
  const componentProps = /** @param {RuntimeElement} element @param {DynamicRecord} state */ (element, state) => {
    const /** @type {DynamicRecord} */ props = {};
    for (const attribute of Array.from(element.attributes)) {
      if (attribute.name.startsWith("data-teloce-") || attribute.name.startsWith("v-") || attribute.name.startsWith("@")) continue;
      props[attribute.name] = attribute.value;
    }
    return props;
  };
  const renderPluginComponents = /** @param {RuntimeElement} target @param {DynamicRecord} state @param {DynamicValue} mountedComponents */ (target, state, mountedComponents) => {
    for (const element of Array.from(target.querySelectorAll("*"))) {
      const component = components[element.tagName.toLowerCase()];
      if (!component || element.__teloceComponentRendered) continue;
      const props = componentProps(element, state);
      const renderComponent = typeof component === "function" ? component : component.render;
      if (typeof renderComponent !== "function") continue;
      const result = renderComponent(element, props, { state, target });
      if (result instanceof Node) element.replaceChildren(result);
      else if (typeof result === "string") element.innerHTML = result;
      element.__teloceComponentRendered = true;
      const context = { state, target };
      component.mounted?.(element, props, context);
      mountedComponents.push({ component, element, props, context });
    }
  };
  /** @param {string | RuntimeElement | null} target */ function createApp(target, initial = {}) {
    if (typeof target === "string") target = document.querySelector(target);
    if (!target) throw new Error("Teloce mount target was not found");
    const source = target.innerHTML;
    let update = () => {};
    let destroyed = false;
    let mountedComponents = /** @type {DynamicRecord[]} */ ([]);
    let loopScopes = new Map();
    const proxyCache = new WeakMap();
    const makeReactive = /** @param {DynamicValue} value */ value => {
      if (!value || typeof value !== "object") return value;
      if (proxyCache.has(value)) return proxyCache.get(value);
      const proxy = new Proxy(value, {
        get(object, key) { return makeReactive(Reflect.get(object, key)); },
        set(object, key, next) { const changed = object[key] !== next; const result = Reflect.set(object, key, next); if (changed) update(); return result; },
        deleteProperty(object, key) { const existed = Object.prototype.hasOwnProperty.call(object, key); const result = Reflect.deleteProperty(object, key); if (existed) update(); return result; },
      });
      proxyCache.set(value, proxy);
      return proxy;
    };
    const state = makeReactive({ ...initial });
    const cleanupComponents = () => {
      for (const entry of mountedComponents.splice(0)) {
        try { entry.component?.unmount?.(entry.element, entry.props, entry.context); } catch (_) {}
      }
    };
    const instance = {
      target,
      state,
      mount: () => { destroyed = false; update(); return instance; },
      unmount: () => {
        if (destroyed) return instance;
        cleanupComponents();
        for (const plugin of plugins) {
          try { plugin.unmounted?.(target, state); plugin.hooks?.unmount?.(target, { state }); } catch (_) {}
        }
        target.replaceChildren();
        destroyed = true;
        return instance;
      },
    };
    update = () => {
      if (destroyed) return;
      for (const plugin of plugins) plugin.hooks?.beforeRender?.(state, { target });
      cleanupComponents();
      loopScopes = new Map();
      target.innerHTML = render(source, state, loopScopes);
      renderPluginComponents(target, state, mountedComponents);
      target.querySelectorAll("*").forEach(/** @param {RuntimeElement} element */ element => {
        for (const attribute of Array.from(element.attributes)) {
          if (attribute.name.startsWith("data-teloce-event-")) {
            const eventKey = attribute.name.slice("data-teloce-event-".length); const [eventName, ...modifiers] = eventKey.split(".");
            const options = { once: modifiers.includes("once"), capture: modifiers.includes("capture"), passive: modifiers.includes("passive") };
            element.addEventListener(eventName, /** @param {RuntimeEvent} event */ event => { if (modifiers.includes("self") && event.target !== element) return; if (modifiers.includes("enter") && event.key !== "Enter") return; if (modifiers.includes("esc") && event.key !== "Escape") return; if (modifiers.includes("ctrl") && !event.ctrlKey) return; if (modifiers.includes("shift") && !event.shiftKey) return; if (modifiers.includes("alt") && !event.altKey) return; if (modifiers.includes("meta") && !event.metaKey) return; if (modifiers.includes("right") && event.button !== 2) return; if (modifiers.includes("middle") && event.button !== 1) return; if (modifiers.includes("left") && event.button !== 0) return; if (modifiers.includes("prevent")) event.preventDefault(); if (modifiers.includes("stop")) event.stopPropagation(); state.event = event; state.$event = event; const loopScope = loopScopes.get(element.closest("[data-teloce-loop-scope]")?.getAttribute("data-teloce-loop-scope")); runEventExpression(attribute.value, loopScope ? { ...state, ...loopScope } : state, event); }, options);
          }
          if (attribute.name === "data-teloce-model") {
            const expression = attribute.value; const eventName = element.type === "checkbox" || element.tagName === "SELECT" ? "change" : "input";
            element.addEventListener(eventName, () => assign(expression, element.type === "checkbox" ? element.checked : element.value, state));
          }
          if (attribute.name.startsWith("data-teloce-bind-")) {
            const name = attribute.name.slice("data-teloce-bind-".length);
            const value = attribute.value;
            if (name === "show") element.hidden = !Boolean(value && value !== "false");
            else if (name === "text") element.textContent = value;
            else if (name === "html") element.innerHTML = sanitizeHtml(value);
            else if (value === "false" || value === "null" || value === "undefined") element.removeAttribute(name);
            else element.setAttribute(name, value);
          }
          const directiveMatch = attribute.name.match(/^v-([\w-]+)$/);
          const directive = directiveMatch && directives[directiveMatch[1]];
          if (directive?.render) {
            const expression = attribute.value;
            directive.render(element, {
              name: directiveMatch[1],
              expression,
              value: evaluate(expression, state),
              state,
              modifiers: [],
            });
          }
        }
      });
      for (const plugin of plugins) {
        plugin.updated?.(target, state);
        plugin.hooks?.afterRender?.(target, { state });
      }
    };
    update();
    for (const plugin of plugins) plugin.mounted?.(target, state);
    return instance;
  }
  const api = { createApp, create: createApp, mount: createApp, directives, components, helpers, registerComponent, registerHelper, /** @param {DynamicRecord} plugin */ use(/** @type {DynamicRecord} */ plugin) {
    plugins.push(plugin);
    registerPluginDirectives(plugin);
    registerPluginComponents(plugin);
    if (plugin?.helpers && typeof plugin.helpers === "object") Object.assign(helpers, plugin.helpers);
    if (Array.isArray(plugin?.filters)) for (const filter of plugin.filters) if (filter?.name && filter.transform) filters[filter.name] = filter.transform;
    if (plugin?.filters && !Array.isArray(plugin.filters) && typeof plugin.filters === "object") Object.assign(filters, plugin.filters);
    plugin?.install?.(api);
    plugin?.hooks?.init?.(api);
    return api;
  }, filters, config: runtimeConfig, version: "0.2.3" };
  root.teloce = root.teloce || api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof globalThis !== "undefined") (/** @type {DynamicRecord} */ (globalThis)).teloce = root.teloce;
})(typeof globalThis !== "undefined" ? globalThis : window);

"""
JavaScript generator.

Generates JavaScript code from the AST.
"""

from __future__ import annotations

from typing import List, Optional, Any
import json
import html
import re
from teloce.ast.elements import ElementFactory
from teloce.css.hashing import HashGenerator
from teloce.css.modules import CSSModules
from teloce.compiler.minifier import minify_js
from teloce.project.extensions import normalize_source_extensions, source_extension_pattern

from teloce.ast.nodes import ASTNode, ElementNode, TextNode, InterpolationNode, ForNode, IfNode, ComponentNode, SlotNode, FragmentNode
from teloce.sfc.component import Component


SAFE_EXPRESSION_RUNTIME = r'''
const __tokenize = source => {
  const tokens = []; let index = 0; const text = String(source || "");
  const operators = ["===", "!==", ">=", "<=", "&&", "||", "??", "==", "!=", "=>", "?."];
  while (index < text.length) {
    const current = text[index];
    if (/\s/.test(current)) { index += 1; continue; }
    if (current === "'" || current === '"') {
      const quote = current; index += 1; let value = "";
      while (index < text.length && text[index] !== quote) {
        if (text[index] === "\\" && index + 1 < text.length) { const next = text[index + 1]; value += ({ n: "\n", r: "\r", t: "\t" }[next] ?? next); index += 2; }
        else { value += text[index]; index += 1; }
      }
      index += 1; tokens.push({ type: "literal", value }); continue;
    }
    const number = text.slice(index).match(/^(?:\d+(?:\.\d*)?|\.\d+)/);
    if (number) { tokens.push({ type: "literal", value: Number(number[0]) }); index += number[0].length; continue; }
    const identifier = text.slice(index).match(/^[A-Za-z_$][\w$]*/);
    if (identifier) { tokens.push({ type: "identifier", value: identifier[0] }); index += identifier[0].length; continue; }
    const operator = operators.find(value => text.startsWith(value, index));
    if (operator) { tokens.push({ type: "operator", value: operator }); index += operator.length; continue; }
    tokens.push({ type: "operator", value: current }); index += 1;
  }
  tokens.push({ type: "eof", value: "" }); return tokens;
};
const __safeEvaluate = (expression, scope) => {
  const tokens = __tokenize(expression); let cursor = 0;
  const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]);
  const safeProperty = property => property != null && !blocked.has(String(property));
  const peek = () => tokens[cursor]; const take = value => { if (!value || peek().value === value) return tokens[cursor++]; return null; };
  const lookup = name => {
    if (name === "true") return true; if (name === "false") return false; if (name === "null") return null; if (name === "undefined") return undefined;
    const builtins = { Math, Number, String, Boolean, Array, Object, JSON, Date, parseInt, parseFloat, isNaN };
    if (Object.prototype.hasOwnProperty.call(scope || {}, name)) return scope[name];
    return builtins[name];
  };
  const precedence = { "||": 1, "??": 1, "&&": 2, "==": 3, "!=": 3, "===": 3, "!==": 3, "<": 4, ">": 4, "<=": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6 };
  const primary = () => {
    const token = take();
    if (token.type === "literal") return token.value;
    if (token.type === "identifier") return lookup(token.value);
    if (token.value === "(") { const value = expressionParser(0); take(")"); return value; }
    if (token.value === "[") { const values = []; while (peek().value !== "]" && peek().type !== "eof") { values.push(expressionParser(0)); if (!take(",")) break; } take("]"); return values; }
    if (token.value === "{") { const result = {}; while (peek().value !== "}" && peek().type !== "eof") { const key = take(); const name = key.value; if (take(":")) result[name] = expressionParser(0); else result[name] = lookup(name); if (!take(",")) break; } take("}"); return result; }
    return undefined;
  };
  const postfix = () => {
    let value = primary(); let owner = null;
    while (true) {
      if (take(".") || take("?.")) { owner = value; const property = take(); value = value == null || !safeProperty(property?.value) ? undefined : value[property.value]; continue; }
      if (take("[")) { owner = value; const property = expressionParser(0); take("]"); value = value == null || !safeProperty(property) ? undefined : value[property]; continue; }
      if (take("(")) { const args = []; while (peek().value !== ")" && peek().type !== "eof") { args.push(expressionParser(0)); if (!take(",")) break; } take(")"); if (typeof value === "function") value = value.apply(owner || scope, args); owner = null; continue; }
      break;
    }
    return value;
  };
  const unary = () => { if (take("!")) return !unary(); if (take("-")) return -unary(); if (take("+")) return +unary(); if (peek().value === "typeof") { take(); return typeof unary(); } return postfix(); };
  const apply = (operator, left, right) => { if (operator === "||") return left || right; if (operator === "&&") return left && right; if (operator === "??") return left ?? right; if (operator === "===") return left === right; if (operator === "!==") return left !== right; if (operator === "==") return left == right; if (operator === "!=") return left != right; if (operator === "<") return left < right; if (operator === ">") return left > right; if (operator === "<=") return left <= right; if (operator === ">=") return left >= right; if (operator === "+") return left + right; if (operator === "-") return left - right; if (operator === "*") return left * right; if (operator === "/") return left / right; if (operator === "%") return left % right; return left; };
  const expressionParser = minimum => { let left = unary(); while (precedence[peek().value] >= minimum) { const operator = take().value; const right = expressionParser(precedence[operator] + 1); left = apply(operator, left, right); } if (minimum === 0 && take("?")) { const yes = expressionParser(0); take(":"); const no = expressionParser(0); left = left ? yes : no; } return left; };
  return expressionParser(0);
};
const __splitEventStatements = source => { const result = []; let start = 0; let depth = 0; let quote = ""; let escaped = false; const text = String(source).trim(); for (let index = 0; index < text.length; index += 1) { const character = text[index]; if (quote) { if (escaped) escaped = false; else if (character === "\\") escaped = true; else if (character === quote) quote = ""; continue; } if (character === "\"" || character === "'") { quote = character; continue; } if ("([{".includes(character)) depth += 1; else if (")]}".includes(character)) depth -= 1; else if ((character === "," || character === ";") && depth === 0) { result.push(text.slice(start, index).trim()); start = index + 1; } } result.push(text.slice(start).replace(/^\(|\)$/g, "").trim()); return result.filter(Boolean); };
const __setSafePath = (expression, value, scope) => { const path = String(expression).trim().split(".").filter(Boolean); const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]); if (!path.length || path.some(part => blocked.has(part))) return undefined; if (path.length === 1) scope[path[0]] = value; else { let target = scope[path[0]]; for (const part of path.slice(1, -1)) target = target?.[part]; if (target != null) target[path[path.length - 1]] = value; } return value; };
const __runEventExpression = (expression, scope) => { let result; for (const statement of __splitEventStatements(expression)) { const update = statement.match(/^(.+?)\s*(\+\+|--)$/); if (update) { const current = __safeEvaluate(update[1], scope); result = __setSafePath(update[1], Number(current || 0) + (update[2] === "++" ? 1 : -1), scope); continue; } const assignment = statement.match(/^(.+?)\s*(\+=|-=|\*=|\/=|=)\s*(.+)$/); if (assignment) { const current = __safeEvaluate(assignment[1], scope); const next = __safeEvaluate(assignment[3], scope); const value = assignment[2] === "=" ? next : assignment[2] === "+=" ? current + next : assignment[2] === "-=" ? current - next : assignment[2] === "*=" ? current * next : current / next; result = __setSafePath(assignment[1], value, scope); continue; } result = __safeEvaluate(statement, scope); } return result; };
'''

SHARED_DOM_RUNTIME = r'''
export const __createReactive = (initial, notify) => {
  const cache = new WeakMap();
  const canObserve = value => {
    if (!value || typeof value !== "object") return false;
    if (Array.isArray(value)) return true;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  };
  const wrap = (value, rootKey = null) => {
    // Browser host objects (WebSocket, URL, EventTarget, File, etc.) and
    // class instances require their real receiver. Proxying them causes
    // native getters and methods to throw "Illegal invocation".
    if (!canObserve(value)) return value;
    if (cache.has(value)) return cache.get(value);
    const proxy = new Proxy(value, {
      get(object, key, receiver) {
        const result = Reflect.get(object, key, receiver);
        return result && typeof result === "object" ? wrap(result, rootKey ?? String(key)) : result;
      },
      set(object, key, next, receiver) {
        const changed = !Object.is(object[key], next);
        const result = Reflect.set(object, key, next, receiver);
        if (changed) notify(rootKey ?? String(key));
        return result;
      },
      deleteProperty(object, key) {
        const existed = Object.prototype.hasOwnProperty.call(object, key);
        const result = Reflect.deleteProperty(object, key);
        if (existed) notify(rootKey ?? String(key));
        return result;
      },
    });
    cache.set(value, proxy);
    cache.set(proxy, proxy); // Reordered arrays already contain observable rows.
    return proxy;
  };
  return wrap(initial);
};

const __lis = values => {
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
export const __patch = (target, html, options = {}) => {
  const focused = target.contains?.(document.activeElement) ? document.activeElement : null;
  const selection = focused && typeof focused.selectionStart === "number"
    ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
  const template = options.nodes ? { content: { childNodes: options.nodes } } : document.createElement("template");
  if (!options.nodes) template.innerHTML = html;
  const playEnter = typeof options.playEnter === "function" ? options.playEnter : () => {};
  const playExit = typeof options.playExit === "function" ? options.playExit : () => {};
  const onDispose = typeof options.onDispose === "function" ? options.onDispose : () => {};
  const markManaged = node => {
    if (!node) return node;
    node.__teloceManaged = true;
    if (node.nodeType === 1) {
      node.__teloceManagedAttributes = new Set(Array.from(node.attributes).map(attribute => attribute.name));
      for (const child of Array.from(node.childNodes)) markManaged(child);
    }
    return node;
  };
  const cloneManaged = node => {
    const clone = markManaged(node.cloneNode(true));
    playEnter(clone);
    return clone;
  };
  const disposeNode = node => {
    if (!node) return;
    onDispose(node);
    playExit(node);
    node.__teloceInstance?.unmount?.();
    if (node.__teloceHandlers) for (const record of node.__teloceHandlers.values()) node.removeEventListener(record.actualEvent, record.listener, record.options);
    if (node.__teloceModelListener) node.removeEventListener(node.__teloceModelListener.eventName, node.__teloceModelListener.listener);
    for (const child of Array.from(node.childNodes || [])) disposeNode(child);
  };
  const patchNode = (oldNode, newNode) => {
    if (oldNode === newNode) return oldNode;
    if (!oldNode || oldNode.nodeType !== newNode.nodeType || (oldNode.nodeType === 1 && oldNode.tagName !== newNode.tagName)) return cloneManaged(newNode);
    if (oldNode.nodeType === 3 || oldNode.nodeType === 8) {
      if (oldNode.nodeValue !== newNode.nodeValue) oldNode.nodeValue = newNode.nodeValue;
      return oldNode;
    }
            if (oldNode.hasAttribute("data-teloce-memo") && newNode.hasAttribute("data-teloce-memo") && oldNode.getAttribute("data-teloce-memo") === newNode.getAttribute("data-teloce-memo")) return oldNode;
    const ssrBoundary = oldNode.hasAttribute("data-teloce-ssr-boundary");
    const managedAttributes = oldNode.__teloceManagedAttributes || new Set();
    for (const attr of Array.from(oldNode.attributes)) if (managedAttributes.has(attr.name) && !newNode.hasAttribute(attr.name) && !newNode.hasAttribute("data-teloce-resolved-" + attr.name)) oldNode.removeAttribute(attr.name);
    for (const attr of Array.from(newNode.attributes)) if (oldNode.getAttribute(attr.name) !== attr.value) oldNode.setAttribute(attr.name, attr.value);
    oldNode.__teloceManagedAttributes = new Set(Array.from(newNode.attributes).map(attribute => attribute.name));
    if (oldNode.__teloceInstance || ssrBoundary) {
      // A mounted component owns its rendered subtree. Preserve that subtree
      // and retain the new declarative host as the next props/slots source.
      if (ssrBoundary) oldNode.setAttribute("data-teloce-ssr-boundary", "1");
      oldNode.__telocePendingPropsSource = newNode.cloneNode(true);
      return oldNode;
    }
    if (oldNode.hasAttribute("data-teloce-data-table")) {
      // The table helper owns the host's generated table/controls. Its
      // reactive configuration is refreshed by the directive binder below.
      return oldNode;
    }
    if (oldNode.hasAttribute("data-teloce-preserve")) {
      // Imperative integrations such as Monaco, CodeMirror, maps, and canvas
      // widgets own their child DOM. Reconciliation must update the host
      // attributes but never replace the integration's internal nodes.
      return oldNode;
    }
    patchChildren(oldNode, newNode);
    return oldNode;
  };
  const patchChildren = (parent, templateParent, region = false) => {
    const children = Array.from(parent.childNodes);
    const old = region && options.start && options.end
      ? children.slice(children.indexOf(options.start) + 1, children.indexOf(options.end))
      : children;
    // Mark server-rendered/pre-existing nodes on first hydration so they are
    // reconciled and disposed exactly like client-created nodes. Without
    // this, an SSR host containing HTML before mount would receive a second
    // copy of the component tree.
    for (const node of old) if (!node.__teloceManaged) markManaged(node);
    const next = Array.from(templateParent.childNodes);
    const managed = old.filter(node => node.__teloceManaged);
    const keyed = new Map();
    const unkeyed = [];
    const positions = new Map(managed.map((node, index) => [node, index]));
    for (const node of managed) {
      const key = node.nodeType === 1 ? node.getAttribute('data-teloce-key') : null;
      if (key != null) {
        if (keyed.has(key)) throw new Error(`Duplicate keyed loop value: ${key}`);
        keyed.set(key, node);
      } else unkeyed.push(node);
    }
    const used = new Set(), nextKeys = new Set(), nodes = [], indices = [];
    let cursor = 0;
    for (const newNode of next) {
      const key = newNode.nodeType === 1 ? newNode.getAttribute('data-teloce-key') : null;
      if (key != null && nextKeys.has(key)) throw new Error(`Duplicate keyed loop value: ${key}`);
      if (key != null) nextKeys.add(key);
      const oldNode = key != null ? keyed.get(key) : unkeyed[cursor++];
      if (oldNode) used.add(oldNode);
      const result = oldNode ? patchNode(oldNode, newNode) : cloneManaged(newNode);
      if (oldNode && result !== oldNode) { disposeNode(oldNode); oldNode.remove(); }
      nodes.push(result);
      indices.push(result === oldNode ? positions.get(oldNode) : -1);
    }
    for (const oldNode of managed) if (!used.has(oldNode) && oldNode.parentNode === parent) { disposeNode(oldNode); oldNode.remove(); }
    const stable = __lis(indices);
    let anchor = region ? options.end : null;
    for (let i = nodes.length - 1; i >= 0; i--) {
      if (indices[i] < 0 || !stable.has(i)) parent.insertBefore(nodes[i], anchor);
      anchor = nodes[i];
    }
    if (region && options.onNodes) options.onNodes(nodes);
  };
  patchChildren(target, template.content, Boolean(options.start && options.end));
  if (focused?.isConnected && document.activeElement !== focused) {
    focused.focus({ preventScroll: true });
    if (selection) focused.setSelectionRange(...selection);
  }
};
'''

BUILTIN_FILTERS_JS = {
    "uppercase": 'value => String(value ?? "").toUpperCase()',
    "lowercase": 'value => String(value ?? "").toLowerCase()',
    "trim": 'value => String(value ?? "").trim()',
    "capitalize": 'value => { const text = String(value ?? ""); return text ? text[0].toUpperCase() + text.slice(1) : text; }',
    "slugify": 'value => String(value ?? "").trim().toLowerCase().replace(/[^\\w\\s-]/g, "").replace(/[\\s_-]+/g, "-").replace(/^-+|-+$/g, "")',
    "truncate": '(value, length = 30, suffix = "...") => { const text = String(value ?? ""); const size = Number(length); return text.length > size ? text.slice(0, Math.max(0, size - String(suffix).length)) + suffix : text; }',
    "currency": '(value, currency = "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency: String(currency).toUpperCase() }).format(Number(value) || 0)',
    "percent": '(value, digits = 0) => `${(Number(value) * 100).toFixed(Number(digits))}%`',
    "number": '(value, options) => { const config = options && typeof options === "object" ? { ...options } : {}; const locale = typeof options === "string" ? options : config.locale; if (config.locale) delete config.locale; return new Intl.NumberFormat(locale || undefined, config).format(Number(value) || 0); }',
    "date": '(value, formatOrOptions, locale) => { const date = value instanceof Date ? value : new Date(value); if (Number.isNaN(date.getTime())) return ""; let options = formatOrOptions && typeof formatOrOptions === "object" ? { ...formatOrOptions } : {}; const resolvedLocale = locale || options.locale; if (options.locale) delete options.locale; if (typeof formatOrOptions === "string") { const pattern = formatOrOptions; options = { year: /y{2,4}/i.test(pattern) ? "numeric" : undefined, month: /MMMM/.test(pattern) ? "long" : /MMM/.test(pattern) ? "short" : /M/.test(pattern) ? "numeric" : undefined, day: /dd/.test(pattern) ? "2-digit" : /d/.test(pattern) ? "numeric" : undefined }; } return new Intl.DateTimeFormat(resolvedLocale || undefined, options).format(date); }',
    "first": 'value => Array.isArray(value) ? value[0] : value',
    "last": 'value => Array.isArray(value) ? value[value.length - 1] : value',
    "pluck": '(value, key) => Array.isArray(value) ? value.map(item => item == null ? undefined : item[key]) : value',
    "orderBy": '(value, key, direction = "asc") => Array.isArray(value) ? [...value].sort((a, b) => { const left = key == null ? a : a?.[key]; const right = key == null ? b : b?.[key]; const result = left < right ? -1 : left > right ? 1 : 0; return String(direction).toLowerCase() === "desc" ? -result : result; }) : value',
    "json": 'value => JSON.stringify(value)',
    "join": '(value, separator = ", ") => Array.isArray(value) ? value.join(separator) : value',
}


class Generator:
    """
    Generates JavaScript code from the AST.
    """
    
    def __init__(self, options: Optional[dict] = None):
        self.options = options or {}
        self.source_extensions = normalize_source_extensions(
            self.options.get("source_extensions"),
            html_mode=bool(self.options.get("html_mode", False)),
        )
        self.dev = self.options.get("dev", True)
        self.minify = self.options.get("minify", False)
        self.indent_level = 0
        self.scope_id = None
        self.module_mapping = {}
        self._used_components = set()
        self._used_filters = set()
        self._direct_plan = {"enabled": False, "structural": False, "bindings": []}
        self._direct_cursor = 0
    
    def generate(self, nodes: List[ASTNode], component: Component) -> str:
        """Generate JavaScript code."""
        self.indent_level = 0
        self.scope_id = HashGenerator().generate_scope_id(component.name) if component.style.scoped else None
        self._used_components = self._collect_component_tags(nodes)
        self._used_filters = self._collect_filter_names(nodes)
        self._direct_plan = dict(self.options.get("direct_plan") or {})
        # Child-owned DOM and projected slots need the compatibility renderer
        # until binding ownership can be represented explicitly in the plan.
        if self._used_components or self._direct_plan.get("components") or self._has_unsupported_regions(nodes):
            self._direct_plan["fallback"] = True
        self._direct_cursor = 0
        self._direct_regions = []
        self._direct_region_depth = 0
        self._emitted_direct_ids = set()
        self._computed_bodies = dict(getattr(component, "script_computed", {}) or {})
        self._targeted_structural = bool(not self._direct_plan.get("fallback") and self._direct_plan.get("structural") and not self._direct_plan.get("components") and not self._direct_plan.get("refreshIntegrations") and not self._has_unsupported_regions(nodes))
        if self._direct_plan.get("structural") and not self._targeted_structural:
            self._direct_plan["fallback"] = True
        all_style_css = "\n".join(style.css for style in getattr(component, "styles", []) or [component.style])
        self.module_mapping = CSSModules.mapping(all_style_css, component.name) if component.style.module else {}
        
        lines = []
        
        # Add import statements
        lines.append('// Generated by Teloce-Py')
        lines.extend(self._generate_component_imports(component))
        lines.extend(self._generate_signal_imports(component))
        module_code = getattr(component.script, "module_code", "")
        if module_code:
            cleaned_module_code = self._strip_component_imports(module_code)
            if cleaned_module_code:
                lines.append(cleaned_module_code)
        lines.append('')
        
        # Generate component code
        lines.append('const __component = {')
        self.indent_level += 1
        
        # Name
        lines.append(f'{self._indent()}name: "{component.name}",')
        lines.append('')
        
        # Data
        if component.script_data:
            lines.append(f'{self._indent()}data() {{')
            self.indent_level += 1
            data_body = getattr(component.script, "data_body", None)
            if data_body:
                for line in data_body.split('\n'):
                    if line.strip():
                        lines.append(f'{self._indent()}{line}')
            else:
                lines.append(f'{self._indent()}return {component.script_data};')
            self.indent_level -= 1
            lines.append(f'{self._indent()}}},')
            lines.append('')
        
        # Methods
        if component.script_methods:
            lines.append(f'{self._indent()}methods: {{')
            self.indent_level += 1
            for method_name, method_code in component.script_methods.items():
                params = getattr(component.script, "method_params", {}).get(method_name, "")
                prefix = "async " if getattr(component.script, "method_async", {}).get(method_name, False) else ""
                lines.append(f'{self._indent()}{prefix}{method_name}({params}) {{')
                self.indent_level += 1
                for line in method_code.split('\n'):
                    if line.strip():
                        lines.append(f'{self._indent()}{line}')
                self.indent_level -= 1
                lines.append(f'{self._indent()}}},')
            self.indent_level -= 1
            lines.append(f'{self._indent()}}},')
            lines.append('')

        if component.script.props:
            lines.append(f'{self._indent()}props: {self._generate_props(component.script.props)},')
            lines.append('')

        query_state = getattr(component.script, "query_state", None)
        if query_state:
            lines.append(f'{self._indent()}queryState: {query_state},')
            lines.append('')

        actions = self._collect_actions(nodes)
        if actions:
            lines.append(f'{self._indent()}actions: {self._generate_actions(actions)},')
            lines.append('')
        
        # Computed
        if component.script_computed:
            lines.append(f'{self._indent()}computed: {{')
            self.indent_level += 1
            for comp_name, comp_code in component.script_computed.items():
                lines.append(f'{self._indent()}{comp_name}() {{')
                self.indent_level += 1
                for line in comp_code.split('\n'):
                    if line.strip():
                        lines.append(f'{self._indent()}{line}')
                self.indent_level -= 1
                lines.append(f'{self._indent()}}},')
            self.indent_level -= 1
            lines.append(f'{self._indent()}}},')
            lines.append('')

        if getattr(component.script, "lifecycle", {}):
            for hook_name, hook_code in component.script.lifecycle.items():
                params = getattr(component.script, "lifecycle_params", {}).get(hook_name, "")
                prefix = "async " if getattr(component.script, "lifecycle_async", {}).get(hook_name, False) else ""
                lines.append(f'{self._indent()}{prefix}{hook_name}({params}) {{')
                self.indent_level += 1
                for line in hook_code.split('\n'):
                    if line.strip():
                        lines.append(f'{self._indent()}{line}')
                self.indent_level -= 1
                lines.append(f'{self._indent()}}},')
            lines.append('')

        if getattr(component.script, "watch", {}):
            lines.append(f'{self._indent()}watch: {{')
            self.indent_level += 1
            for watch_name, watch_code in component.script.watch.items():
                params = getattr(component.script, "watch_params", {}).get(watch_name, "newValue, oldValue")
                prefix = "async " if getattr(component.script, "watch_async", {}).get(watch_name, False) else ""
                lines.append(f'{self._indent()}{prefix}{json.dumps(watch_name)}({params}) {{')
                self.indent_level += 1
                for line in watch_code.split('\n'):
                    if line.strip():
                        lines.append(f'{self._indent()}{line}')
                self.indent_level -= 1
                lines.append(f'{self._indent()}}},')
            self.indent_level -= 1
            lines.append(f'{self._indent()}}},')
            lines.append('')
        
        # Template
        template_code = self._generate_template(nodes)
        self._direct_plan.update({"version": 2, "regions": self._direct_regions, "targetedStructural": self._targeted_structural})
        # The generated component is intentionally runnable as a plain browser
        # ES module.  Keep the CSS/template contract together by embedding the
        # compiled stylesheet in the component runtime and installing it once
        # when the component mounts.  The standalone .css file is still emitted
        # by the build pipeline for deployments that prefer external CSS.
        style_code = self._generate_component_css(component)
        # Templates are data. A JavaScript template literal is unsafe here:
        # ordinary UI copy may contain backticks or `${...}`, which would
        # terminate/interpolate generated code. JSON encoding produces a
        # valid string literal for every template character.
        lines.append(f'{self._indent()}template: {json.dumps(template_code, ensure_ascii=False)},')
        
        self.indent_level -= 1
        lines.append('};')
        lines.append('')
        lines.extend(self._generate_runtime(component, template_code, style_code))
        lines.append('export default __component;')
        
        code = '\n'.join(lines)
        if self.minify:
            code = self._minify_generated_js(code)
        return code

    def _minify_generated_js(self, code: str) -> str:
        """Safely compact generated output without rewriting template strings."""
        return minify_js(code)

    def _generate_component_css(self, component: Component) -> str:
        """Compile this component's CSS using the same scope identity as markup."""
        if not self.options.get("inline_css", True):
            return ""
        styles = getattr(component, "styles", None) or [component.style]
        if not any(style.css.strip() for style in styles):
            return ""
        from teloce.css.generator import CSSGenerator

        generated = []
        for style in styles:
            generated.append(CSSGenerator({
                **self.options,
                "scoped": style.scoped,
                "module": style.module,
            }).generate(style.css, component.name))
        return "\n".join(css for css in generated if css)

    @staticmethod
    def _generate_props(props: dict) -> str:
        """Emit prop metadata without turning validator/factory code into text."""
        entries = []
        for name, definition in props.items():
            definition = definition or {}
            default_source = definition.get("default")
            validator_source = definition.get("validator")
            fields = [
                f'type: {json.dumps(definition.get("type"))}',
                f'required: {str(bool(definition.get("required"))).lower()}',
                f'default: {json.dumps(default_source)}',
            ]
            if default_source and re.match(r'^\s*(?:async\s+)?(?:function\b|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)', default_source):
                fields.append(f'defaultFactory: ({default_source})')
            if validator_source:
                fields.append(f'validator: ({validator_source})')
            else:
                fields.append('validator: null')
            entries.append(f'{json.dumps(name)}: {{ {", ".join(fields)} }}')
        return '{ ' + ', '.join(entries) + ' }'

    def _generate_js_filters(self) -> str:
        """Serialize explicitly supplied browser filter implementations."""
        filters = self.options.get("filter_js", {}) or {}
        parts = []
        for name, source in filters.items():
            if self.options.get("tree_shake", False) and name not in self._used_filters:
                continue
            if isinstance(source, str):
                parts.append(f'{json.dumps(name)}: ({source})')
        return ", ".join(parts)

    def _generate_builtin_filters(self, component: Component) -> str:
        """Emit only built-in filters referenced by this component."""
        return ", ".join(
            f'{json.dumps(name)}: {implementation}'
            for name, implementation in BUILTIN_FILTERS_JS.items()
            if name in self._used_filters
        )

    @staticmethod
    def _filter_names_from_expression(expression: Any) -> set:
        """Find template filter names without scanning script/style text.

        A pipe inside a quoted string or nested expression is data, not a
        filter separator. This deliberately handles the template expression
        grammar rather than JavaScript source; full JavaScript parsing belongs
        to the module parser and is not needed to decide template helpers.
        """
        text = str(expression or "")
        names = set()
        quote = None
        escaped = False
        depth = 0
        index = 0
        while index < len(text):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char in "'\"`":
                quote = char
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == "|" and depth == 0 and (index + 1 >= len(text) or text[index + 1] != "|"):
                match = re.match(r"\s*([A-Za-z_$][\w$]*)", text[index + 1:])
                if match:
                    names.add(match.group(1))
                    index += len(match.group(0))
            index += 1
        return names

    def _collect_filter_names(self, nodes: List[ASTNode]) -> set:
        """Collect filters used by template AST nodes only."""
        used = set()

        def visit(items):
            for node in items or []:
                if isinstance(node, InterpolationNode):
                    used.update(self._filter_names_from_expression(node.expression))
                elif isinstance(node, ElementNode):
                    for value in (node.attributes or {}).values():
                        used.update(self._filter_names_from_expression(value))
                    for binding in node.bindings or []:
                        used.update(self._filter_names_from_expression(binding.value))
                    for event in node.events or []:
                        used.update(self._filter_names_from_expression(event.handler))
                    visit(node.children)
                elif isinstance(node, ForNode):
                    used.update(self._filter_names_from_expression(node.collection))
                    used.update(self._filter_names_from_expression(node.key))
                    visit(node.children)
                elif isinstance(node, IfNode):
                    used.update(self._filter_names_from_expression(node.condition))
                    visit(node.children)
                    visit(node.else_children)
                elif isinstance(node, ComponentNode):
                    for value in (node.props or {}).values():
                        used.update(self._filter_names_from_expression(value))
                    visit(node.children)
                    for slot_nodes in (node.slots or {}).values():
                        visit(slot_nodes)
                elif isinstance(node, (SlotNode, FragmentNode)):
                    visit(node.children)
                elif hasattr(node, "children"):
                    visit(node.children)

        visit(nodes)
        return used

    _TRANSITION_HELPER_SOURCE = {
        'fade': 'function fade(node, opts = {}) { const { duration = 200, easing = "ease" } = opts; return node.animate([{ opacity: 0 }, { opacity: 1 }], { duration, easing, fill: "forwards" }); }',
        'slide': 'function slide(node, opts = {}) { const { axis = "y", distance = 10, duration = 200, easing = "ease-out" } = opts; const prop = axis === "y" ? "translateY" : "translateX"; return node.animate([{ transform: `${prop}(${distance}px)`, opacity: 0 }, { transform: `${prop}(0)`, opacity: 1 }], { duration, easing, fill: "forwards" }); }',
        'scale': 'function scale(node, opts = {}) { const { start = 0.9, duration = 150, easing = "ease-out" } = opts; return node.animate([{ transform: `scale(${start})`, opacity: 0 }, { transform: "scale(1)", opacity: 1 }], { duration, easing, fill: "forwards" }); }',
    }

    def _generate_transition_helpers(self, used_helpers: set, uses_flip: bool) -> List[str]:
        """Return JS source lines for transition/animation directives.

        Only the built-in helpers (fade/slide/scale) actually named by a
        transition:/in:/out: directive in this component are inlined, so a
        component that never animates ships none of this code.
        """
        lines: List[str] = []
        for name in sorted(used_helpers):
            source = self._TRANSITION_HELPER_SOURCE.get(name)
            if source:
                lines.append(source)

        builtin_names = [name for name in sorted(used_helpers) if name in self._TRANSITION_HELPER_SOURCE]
        builtin_list = (', '.join(builtin_names) + ', ') if builtin_names else ''
        lines.append(
            f'const __transitionRegistry = {{ {builtin_list}'
            '...((typeof __component !== "undefined" && __component.transitions) || {}) };'
        )
        lines.append(
            'const __parseTransitionAttr = value => { '
            'const sep = String(value).indexOf(":"); '
            'if (sep === -1) return { name: value, opts: undefined }; '
            'const name = value.slice(0, sep); const rest = value.slice(sep + 1); '
            'let opts; '
            'try { '
            'const jsonish = rest.replace(/([{,]\\s*)([A-Za-z_$][\\w$]*)\\s*:/g, \'$1"$2":\').replace(/\'([^\']*)\'/g, \'"$1"\'); '
            'opts = JSON.parse(jsonish); '
            '} catch (_) { opts = undefined; } '
            'return { name, opts }; };'
        )
        lines.append(
            'const __runDirective = (node, attrName) => { const raw = node.getAttribute?.(attrName); if (!raw) return null; const { name, opts } = __parseTransitionAttr(raw); const fn = __transitionRegistry[name]; return fn ? fn(node, opts) : null; };'
        )
        lines.append(
            '  const __playEnter = node => { if (!node || node.nodeType !== 1) return; '
            'if (node.hasAttribute("data-teloce-in") || node.hasAttribute("data-teloce-transition")) '
            '__runDirective(node, node.hasAttribute("data-teloce-in") ? "data-teloce-in" : "data-teloce-transition"); '
            'node.querySelectorAll?.("[data-teloce-in], [data-teloce-transition]").forEach(child => '
            '__runDirective(child, child.hasAttribute("data-teloce-in") ? "data-teloce-in" : "data-teloce-transition")); };'
        )
        lines.append(
            '  const __playExit = node => { if (!node || node.nodeType !== 1 || !node.isConnected) return; '
            'const attrName = node.hasAttribute("data-teloce-out") ? "data-teloce-out" : node.hasAttribute("data-teloce-transition") ? "data-teloce-transition" : null; '
            'if (!attrName) return; '
            'const parent = node.parentNode; const nextSibling = node.nextSibling; '
            'const ghost = node.cloneNode(true); parent?.insertBefore(ghost, nextSibling); '
            'const anim = __runDirective(ghost, attrName); '
            'if (anim) anim.finished.then(() => ghost.remove()).catch(() => ghost.remove()); else ghost.remove(); };'
        )
        return lines

    def _generate_signal_imports(self, component: Component) -> List[str]:
        """Add zero-configuration signal imports for project builds.

        A normal ``teloce build`` emits a shared runtime and passes its relative
        URL as ``shared_runtime_import``.  In that mode developers can write
        ``signal(0)``/``effect(...)`` (or the explicit ``createSignal`` names)
        directly in a ``.vel`` script without repeating a browser URL import in
        every component.  Explicit imports and local declarations always win.

        Direct ``Compiler`` users still get their existing behavior: without a
        shared runtime URL, no implicit browser import is emitted, so standalone
        builds remain deterministic and can continue to provide their own
        runtime module.
        """
        runtime_import = self.options.get("shared_runtime_import")
        if not runtime_import:
            return []

        source = getattr(component.script, "raw", "") or ""
        imported_locals = set()
        for item in getattr(component.script, "imports", []) or []:
            if getattr(item, "is_namespace", False):
                if item.alias:
                    imported_locals.add(item.alias)
                continue
            if getattr(item, "is_default", False):
                imported_locals.add(item.alias or (item.names[0] if item.names else ""))
            elif item.names:
                imported_locals.add(item.alias or item.names[0])

        declared_locals = set(re.findall(
            r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", source
        ))
        # Friendly names are intentionally aliases, while the create* names
        # remain available for users who prefer the explicit API.
        candidates = (
            ("signal", "createSignal"),
            ("effect", "createEffect"),
            ("computed", "createComputed"),
            ("createSignal", "createSignal"),
            ("createEffect", "createEffect"),
            ("createComputed", "createComputed"),
            ("createMemo", "createMemo"),
            ("batch", "batch"),
            ("untracked", "untracked"),
            ("isSignal", "isSignal"),
            ("isComputed", "isComputed"),
            ("toSignal", "toSignal"),
            ("getValue", "getValue"),
        )
        needed = []
        for local, imported in candidates:
            if local in imported_locals or local in declared_locals:
                continue
            if re.search(rf"(?<![.\w$]){re.escape(local)}\s*\(", source):
                needed.append(imported if local == imported else f"{imported} as {local}")
        if not needed:
            return []
        return [f'import {{ {", ".join(needed)} }} from {json.dumps(runtime_import)};']

    def _source_locations(self, component):
        locations = {}
        source = component.raw_source
        def visit(node):
            expressions = [getattr(node, 'expression', ''), getattr(node, 'condition', '')]
            expressions += [binding.value for binding in getattr(node, 'bindings', [])]
            expressions += [event.handler for event in getattr(node, 'events', [])]
            for expression in expressions:
                if not expression or expression in locations: continue
                offset = source.find(expression)
                if offset >= 0:
                    locations[expression] = {'line': source[:offset].count('\n') + 1,
                        'column': offset - source.rfind('\n', 0, offset)}
            for child in [*getattr(node, 'children', []), *getattr(node, 'else_children', [])]: visit(child)
        for node in component.template: visit(node)
        return locations

    def _generate_runtime(
        self,
        component: Component,
        template_code: str,
        style_code: str = "",
    ) -> List[str]:
        """Generate a dependency-free browser mount function.

        The compiler intentionally emits a small runtime per component for
        now. This keeps generated files usable without npm while the shared
        runtime API evolves.
        """
        uses_transitions = bool(re.search(r'data-teloce-(?:in|out|transition|animate)=', template_code))
        used_transition_helpers = set(re.findall(
            r'data-teloce-(?:in|out|transition)="([\w$]+)', template_code
        ))
        uses_flip = 'data-teloce-animate="flip' in template_code

        template_literal = json.dumps(template_code, ensure_ascii=False)
        style_literal = json.dumps(style_code, ensure_ascii=False)
        style_classes_literal = json.dumps(self.module_mapping, ensure_ascii=False)
        imports = self._component_imports(component)
        if self.options.get("tree_shake", False) and "<component" not in template_code.lower():
            component_tag_names = set(re.findall(r"<([A-Z][\w-]*)(?:\s|/?>)", template_code))
            imports = {name: path for name, path in imports.items() if name in component_tag_names}
        component_map = ', '.join(f'{json.dumps(name)}: {name}' for name in imports)
        custom_filters = self._generate_js_filters()
        shared_runtime_import = self.options.get("shared_runtime_import")
        if shared_runtime_import:
            # A project build emits one shared compiled-component renderer.
            # Keep each component module limited to its definition, template,
            # CSS metadata and imports; lifecycle/event/binding/reconciliation
            # glue belongs in the shared runtime barrel.
            style_id = HashGenerator().generate(component.name, length=9)
            runtime_imports = ["__teloceCreateCompiledComponent"]
            if "data-teloce-data-table" in template_code:
                runtime_imports.append("createDataTable")
            return [
                f'import {{ {", ".join(runtime_imports)} }} from {json.dumps(shared_runtime_import)};',
                f'const __components = {{{component_map}}};',
                f'const __template = {template_literal};',
                f'const __style = {style_literal};',
                f'const __styleClasses = {style_classes_literal};',
                f'const __filters = {{ {self._generate_builtin_filters(component)}{", " if self._generate_builtin_filters(component) and custom_filters else ""}{custom_filters} }};',
                f'const __actions = {self._generate_actions(self._collect_actions_from_template(template_code))};',
                f'const __directPlan = {self._direct_plan_literal()};',
                f'const __runtimeOptions = {{ components: __components, template: __template, style: __style, styleId: "teloce-style-{style_id}", styleClasses: __styleClasses, filters: __filters, actions: __actions, table: typeof createDataTable === "function" ? createDataTable : undefined, direct: __directPlan.enabled, directPlan: __directPlan, dev: {str(bool(self.dev)).lower()}, moduleUrl: import.meta.url }};',
                f'__runtimeOptions.component = {json.dumps(self.options.get("source_filename", component.filename))};',
                f'__runtimeOptions.sourceLocations = {json.dumps(self._source_locations(component))};',
                'export const mount = (target, props = {}, options = {}) => __teloceCreateCompiledComponent(__component, { ...__runtimeOptions, ...options, props }).mount(target, props);',
                'export const hydrate = (target, props = {}) => mount(target, props, { hydrate: true });',
                '__component.hydrate = hydrate',
                'export const createApp = mount;',
                '__component.mount = mount;',
            ]
        runtime = [
            SAFE_EXPRESSION_RUNTIME,
            f'const __components = {{{component_map}}};',
            f'const __actions = {self._generate_actions(self._collect_actions_from_template(template_code))};',
            'const __readProps = (element, parentState) => {',
            '  const slots = { default: "" }; for (const child of Array.from(element.childNodes)) { if (child.nodeType === 1 && child.hasAttribute("slot")) { const name = child.getAttribute("slot") || "default"; slots[name] = (slots[name] || "") + child.outerHTML; } else { slots.default += child.outerHTML ?? child.textContent ?? ""; } }',
            '  const props = { __slots: slots };',
            '  for (const attribute of Array.from(element.attributes)) {',
            '    if (attribute.name === "data-v-" || attribute.name.startsWith("data-v-") || attribute.name.startsWith("data-teloce-event-")) continue;',
            '    if (attribute.name === "data-teloce-is") { props.__dynamic = __evaluate(attribute.value, parentState); continue; }',
            '    if (attribute.name.startsWith(":")) props[attribute.name.slice(1)] = __evaluate(attribute.value, parentState);',
            '    else if (attribute.name.startsWith("data-teloce-bind-")) { const name = attribute.name.slice("data-teloce-bind-".length); try { props[name] = JSON.parse(attribute.value); } catch (_) { props[name] = __evaluate(attribute.value, parentState); } }',
            '    else if (!attribute.name.startsWith("data-")) props[attribute.name] = attribute.value;',
            '  }',
            '  return props;',
            '};',
            f'const __template = {template_literal};',
            f'const __style = {style_literal};',
            f'const __styleClasses = {style_classes_literal};',
            'const __moduleUrl = typeof import.meta !== "undefined" ? import.meta.url.split("?")[0] : "";',
            'const __hmrRegistry = typeof globalThis !== "undefined" ? (globalThis.__teloce_hmr_instances ||= new Map()) : new Map();',
            'const __registerHmr = record => { if (!__moduleUrl) return; if (!__hmrRegistry.has(__moduleUrl)) __hmrRegistry.set(__moduleUrl, new Set()); __hmrRegistry.get(__moduleUrl).add(record); };',
            'const __unregisterHmr = record => { const records = __hmrRegistry.get(__moduleUrl); records?.delete(record); if (records?.size === 0) __hmrRegistry.delete(__moduleUrl); };',
            'if (typeof globalThis !== "undefined" && !globalThis.__teloce_hmr_reload) globalThis.__teloce_hmr_reload = async () => { const records = [...__hmrRegistry.values()].flatMap(set => [...set]); for (const record of records) await record.reload(); };',
            'const __createInitialData = () => (__component.data ? __component.data() : {});',
            'const __normalizeProps = (input) => { const output = { ...input }; for (const [name, definition] of Object.entries(__component.props || {})) { if (output[name] === undefined && definition?.type === "Boolean") output[name] = false; if (output[name] === undefined && definition) { if (typeof definition.defaultFactory === "function") { try { output[name] = definition.defaultFactory(); } catch (error) { if (__dev) console.warn(`Prop default factory failed for ${name}`, error); } } else if (definition.default !== null && definition.default !== undefined) { try { output[name] = __safeEvaluate(String(definition.default), {}); } catch (_) {} } } if (__dev && definition?.required && output[name] === undefined) console.warn(`Missing required prop: ${name}`); if (__dev && definition?.type && output[name] !== undefined) { const expected = String(definition.type).split("|"); const actual = output[name]?.constructor?.name; if (!expected.includes(actual)) console.warn(`Invalid prop type for ${name}: expected ${definition.type}, got ${actual}`); } if (definition?.validator && typeof definition.validator === "function" && output[name] !== undefined) { try { const valid = definition.validator(output[name]); if (__dev && !valid) console.warn(`Invalid prop value for ${name}`); } catch (error) { if (__dev) console.warn(`Prop validator failed for ${name}`, error); } } } return output; };',
            'const __installStyle = () => {',
            '  if (!__style || typeof document === "undefined") return;',
            f'  const styleId = "teloce-style-{HashGenerator().generate(component.name, length=9)}";',
            '  if (document.querySelector(`style[data-teloce-style="${styleId}"]`)) return;',
            '  const style = document.createElement("style");',
            '  style.dataset.teloceStyle = styleId;',
            '  style.setAttribute("data-teloce-style", styleId);',
            '  style.textContent = __style;',
            '  (document.head || document.documentElement).appendChild(style);',
            '};',
            f'const __filters = {{ {self._generate_builtin_filters(component)}{", " if self._generate_builtin_filters(component) and custom_filters else ""}{custom_filters} }};',
            f'const __dev = {str(bool(self.dev)).lower()};',
            'const __evaluate = (expression, scope) => { try { const parts = String(expression).split(/\\s+\\|\\s+/); let value = __safeEvaluate(parts.shift(), scope || {}); for (const filter of parts) { const match = filter.match(/^([\\w$]+)(?:\\((.*)\\)|(?::(.*)))?$/); const argumentsSource = match?.[2] ?? match?.[3]; if (match && __filters[match[1]]) value = __filters[match[1]](value, ...(argumentsSource ? argumentsSource.split(",").map(argument => __safeEvaluate(argument, scope || {})) : [])); } return value; } catch (error) { if (__dev) console.error("Teloce expression error:", expression, error); return ""; } };',
            "const __escapeHtml = (value) => String(value).replace(/[&<>\"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[character]));",
            'const __assign = (expression, value, scope) => { try { const blocked = new Set(["__proto__", "prototype", "constructor", "caller", "callee", "arguments"]); const path = String(expression).trim().split(".").filter(Boolean); if (!path.length || path.some(part => blocked.has(part))) return; if (path.length === 1) scope[path[0]] = value; else { let target = scope[path[0]]; for (const part of path.slice(1, -1)) target = target?.[part]; if (target != null) target[path[path.length - 1]] = value; } } catch (_) {} };',
            'const __mapClass = value => { const map = token => __styleClasses[token] || token; return Array.isArray(value) ? value.map(map).join(" ") : value && typeof value === "object" ? Object.keys(value).filter(key => value[key]).map(map).join(" ") : typeof value === "string" ? value.split(/\\s+/).filter(Boolean).map(map).join(" ") : value; };',
            'const __pluginDirectives = typeof globalThis !== "undefined" ? (globalThis.teloce?.directives || {}) : {};',
            'const __isDangerousUrl = value => /^(?:javascript|vbscript|data|file):/.test(String(value ?? "").replace(/[\\t\\n\\r\\0]/g, "").trim().toLowerCase());',
            'const __sanitizeHtml = value => { const template = document.createElement("template"); template.innerHTML = String(value ?? ""); template.content.querySelectorAll("script,iframe,object,embed,link,meta,base").forEach(node => node.remove()); template.content.querySelectorAll("*").forEach(node => { for (const attribute of Array.from(node.attributes)) { const name = attribute.name.toLowerCase(); if (name.startsWith("on") || ((name === "href" || name === "src" || name === "action" || name === "formaction") && __isDangerousUrl(attribute.value))) node.removeAttribute(attribute.name); } }); return template.innerHTML; };',
            'const __applyBinding = (element, name, value) => { if (name === "class") { const staticClass = element.getAttribute("data-teloce-static-class") ?? element.__teloceStaticClass ?? element.className ?? ""; element.__teloceStaticClass = staticClass; const dynamicClass = String(__mapClass(value) ?? "").trim(); element.__teloceDynamicClass = dynamicClass; element.className = [staticClass, dynamicClass].filter(Boolean).join(" "); } else if (name === "style" && value && typeof value === "object") { for (const [key, item] of Object.entries(value)) element.style[key] = item ?? ""; } else if (name === "show" || name === "hide") { element.hidden = name === "show" ? !Boolean(value) : Boolean(value); } else if (name === "html") { element.innerHTML = __sanitizeHtml(value); } else if (name === "text") { element.textContent = value == null ? "" : String(value); } else if (["disabled", "checked", "selected", "readonly", "required", "multiple"].includes(name)) { element.toggleAttribute(name, Boolean(value)); } else if (["href", "src", "action", "formaction"].includes(name) && __isDangerousUrl(value)) { element.removeAttribute(name); } else if (value === false || value == null) element.removeAttribute(name); else element.setAttribute(name, String(value)); };',
            *(self._generate_transition_helpers(used_transition_helpers, uses_flip) if uses_transitions else []),
            'const __patch = (target, html) => {',
            '  const template = document.createElement("template"); template.innerHTML = html;',
            '  const markManaged = node => { if (!node) return node; node.__teloceManaged = true; if (node.nodeType === 1) { node.__teloceManagedAttributes = new Set(Array.from(node.attributes).map(attribute => attribute.name)); for (const child of Array.from(node.childNodes)) markManaged(child); } return node; };',
            (
                '  const cloneManaged = node => { const clone = markManaged(node.cloneNode(true)); __playEnter(clone); return clone; };'
                if uses_transitions else
                '  const cloneManaged = node => markManaged(node.cloneNode(true));'
            ),
            (
                '  const disposeNode = node => { if (!node) return; __playExit(node); if (node.__teloceInstance?.unmount) node.__teloceInstance.unmount(); if (node.__teloceHandlers) for (const record of node.__teloceHandlers.values()) node.removeEventListener(record.actualEvent, record.listener, record.options); for (const child of Array.from(node.childNodes || [])) disposeNode(child); };'
                if uses_transitions else
                '  const disposeNode = node => { if (!node) return; if (node.__teloceInstance?.unmount) node.__teloceInstance.unmount(); if (node.__teloceHandlers) for (const record of node.__teloceHandlers.values()) node.removeEventListener(record.actualEvent, record.listener, record.options); for (const child of Array.from(node.childNodes || [])) disposeNode(child); };'
            ),
            *(['  const __flipSnapshot = root => { if (!root) return []; return Array.from(root.children || []).filter(node => node.dataset && node.dataset.teloceAnimate === "flip").map(node => [node, node.getBoundingClientRect()]); };'] if uses_flip else []),
            '  const patchNode = (oldNode, newNode) => {',
            '    if (!oldNode || oldNode.nodeType !== newNode.nodeType || (oldNode.nodeType === 1 && oldNode.tagName !== newNode.tagName)) return cloneManaged(newNode);',
            '    if (oldNode.nodeType === 3 || oldNode.nodeType === 8) { if (oldNode.nodeValue !== newNode.nodeValue) oldNode.nodeValue = newNode.nodeValue; return oldNode; }',
            '    const managedAttributes = oldNode.__teloceManagedAttributes || new Set(); for (const attr of Array.from(oldNode.attributes)) if (managedAttributes.has(attr.name) && !newNode.hasAttribute(attr.name) && !newNode.hasAttribute("data-teloce-resolved-" + attr.name)) oldNode.removeAttribute(attr.name);',
            '    for (const attr of Array.from(newNode.attributes)) if (oldNode.getAttribute(attr.name) !== attr.value) oldNode.setAttribute(attr.name, attr.value);',
            '    oldNode.__teloceManagedAttributes = new Set(Array.from(newNode.attributes).map(attribute => attribute.name));',
            '    if (oldNode.__teloceInstance || oldNode.hasAttribute?.("data-teloce-ssr-boundary")) { oldNode.__telocePendingPropsSource = newNode.cloneNode(true); return oldNode; }',
            '    if (oldNode.hasAttribute("data-teloce-preserve")) { return oldNode; }',
            '    patchChildren(oldNode, newNode); return oldNode;',
            '  };',
            '  const patchChildren = (parent, templateParent) => {',
            '    const old = Array.from(parent.childNodes); for (const node of old) if (!node.__teloceManaged) markManaged(node); const next = Array.from(templateParent.childNodes); const managed = old.filter(node => node.__teloceManaged); const keyed = new Map(managed.filter(node => node.nodeType === 1 && node.dataset.teloceKey).map(node => [node.dataset.teloceKey, node])); const used = new Set(); let cursor = 0; let anchor = parent.firstChild;',
            (
                '    const __flipNextKeys = next.filter(node => node.nodeType === 1 && node.dataset && node.dataset.teloceKey).map(node => node.dataset.teloceKey);'
                ' const __flipPrevKeys = parent.__teloceFlipKeys || null;'
                ' const __flipOrderChanged = !__flipPrevKeys || __flipPrevKeys.length !== __flipNextKeys.length || __flipPrevKeys.some((key, index) => key !== __flipNextKeys[index]);'
                ' const __flipBefore = __flipOrderChanged ? __flipSnapshot(parent) : [];'
                ' parent.__teloceFlipKeys = __flipNextKeys;'
                if uses_flip else ''
            ),
            '    next.forEach(newNode => { const key = newNode.nodeType === 1 ? newNode.dataset.teloceKey : null; let oldNode = key && keyed.has(key) ? keyed.get(key) : (key ? null : managed[cursor++]); if (oldNode && used.has(oldNode)) oldNode = null; if (oldNode) used.add(oldNode); const result = oldNode ? patchNode(oldNode, newNode) : cloneManaged(newNode); if (result !== oldNode) { if (oldNode && oldNode.parentNode === parent) { disposeNode(oldNode); parent.replaceChild(result, oldNode); } else parent.insertBefore(result, anchor || null); } else if (result !== anchor) parent.insertBefore(result, anchor || null); anchor = result.nextSibling; });',
            '    for (const oldNode of managed) if (!used.has(oldNode) && oldNode.parentNode === parent) { disposeNode(oldNode); parent.removeChild(oldNode); }',
            (
                '    for (const [node, from] of __flipBefore) { if (!node.isConnected) continue; const to = node.getBoundingClientRect(); const dx = from.left - to.left, dy = from.top - to.top; if (dx || dy) node.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }], { duration: 200, easing: "ease-out" }); }'
                if uses_flip else ''
            ),
            '  };',
            '  patchChildren(target, template.content);',
            '};',
            'const __renderTemplate = (source, state, loopScopes = new Map()) => {',
            '  // Templates are data, never callbacks. Accept a render function only for',
            '  // explicit advanced integrations and always normalize the result to text.',
            '  let output = typeof source === "function" ? source(state) : source == null ? "" : String(source);',
            '  output = output.replace(/<slot\\b([^>]*)>\\s*<\\/slot>/g, (_, attributes) => { const name = attributes.match(/(?:^|\\s)name="([^"]*)"/)?.[1] || "default"; return (state.__slots || {})[name] || ""; });',
            '  const __resolveIfBlocks = (text, scope) => {',
            '    let result = ""; let i = 0;',
            '    while (true) {',
            '      const rest = text.slice(i);',
            '      const openMatch = /<if\\s+(?:condition|test)="/.exec(rest);',
            '      if (!openMatch) { result += rest; break; }',
            '      const openStart = i + openMatch.index;',
            '      result += text.slice(i, openStart);',
            '      const condStart = openStart + openMatch[0].length;',
            '      const condEnd = text.indexOf(\'"\', condStart);',
            '      if (condEnd < 0) { result += text.slice(openStart); break; }',
            '      const condition = text.slice(condStart, condEnd);',
            '      const tagEnd = text.indexOf(">", condEnd) + 1;',
            '      if (tagEnd <= condEnd) { result += text.slice(openStart); break; }',
            '      let depth = 1; let pos = tagEnd; let elseStart = -1; let elseTagEnd = -1; let closeStart = -1;',
            '      while (depth > 0) {',
            '        const nextOpen = text.indexOf("<if ", pos);',
            '        const nextClose = text.indexOf("</if>", pos);',
            '        const nextElse = (depth === 1 && elseStart === -1) ? text.indexOf("<else>", pos) : -1;',
            '        const candidates = [nextOpen, nextClose, nextElse].filter(n => n !== -1);',
            '        if (!candidates.length) break;',
            '        const next = Math.min(...candidates);',
            '        if (next === nextOpen) { depth++; pos = next + 4; }',
            '        else if (next === nextElse) { elseStart = next; elseTagEnd = next + 6; pos = elseTagEnd; }',
            '        else { depth--; pos = next + 5; if (depth === 0) closeStart = next; }',
            '      }',
            '      if (depth !== 0 || closeStart < 0) { result += text.slice(openStart); break; }',
            '      const yesEnd = elseStart !== -1 ? elseStart : closeStart;',
            '      const yesContent = text.slice(tagEnd, yesEnd);',
            '      const noContent = elseStart !== -1 ? text.slice(elseTagEnd, closeStart) : "";',
            '      const branch = __evaluate(condition, scope) ? yesContent : noContent;',
            '      result += __resolveIfBlocks(branch, scope);',
            '      i = pos;',
            '    }',
            '    return result;',
            '  };',
            '  const __renderLoops = (source, state) => {',
            '    let cursor = source.indexOf("<for ");',
            '    while (cursor >= 0) {',
            '      const openEnd = source.indexOf(">", cursor); if (openEnd < 0) break;',
            '      const opening = source.slice(cursor, openEnd + 1); const itemMatch = opening.match(/item="([^"]*)"/); const collectionMatch = opening.match(/(?:in|collection)="([^"]*)"/); if (!itemMatch || !collectionMatch) break;',
            '      let depth = 1; let scan = openEnd + 1; let closeStart = -1; while (depth && scan < source.length) { const nextOpen = source.indexOf("<for ", scan); const nextClose = source.indexOf("</for>", scan); if (nextClose < 0) break; if (nextOpen >= 0 && nextOpen < nextClose) { depth++; scan = nextOpen + 5; } else { depth--; closeStart = nextClose; scan = nextClose + 6; } } if (depth || closeStart < 0) break;',
            '      const body = source.slice(openEnd + 1, closeStart); const values = __evaluate(collectionMatch[1], state) || []; const rendered = Array.from(values).map((value, index) => { const loopScope = { ...state, [itemMatch[1]]: value, index }; const nested = __renderLoops(body, loopScope); return __resolveIfBlocks(nested.replace(/data-teloce-bind-([\\w-]+)="([^"]*)"/g, (_, name, expression) => { const decoded = expression.replace(/&#x27;/g, "\\\'").replace(/&quot;/g, "\\\"").replace(/&amp;/g, "&"); const result = __evaluate(decoded, loopScope); const serialized = JSON.stringify(result === undefined ? null : result); return `data-teloce-resolved-${name}="${serialized.replace(/"/g, "&quot;")}"`; }), loopScope).replace(/<([A-Za-z][\\w:-]*)([^>]*?)@([\\w.-]+)="([^"]*)"([^>]*)>/g, (_, tag, before, name, expression, after) => { const encoded = JSON.stringify({ [itemMatch[1]]: value, index }).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); return `<${tag}${before}data-teloce-event-${name}="${expression}" data-teloce-loop-scope="${encoded}"${after}>`; }).replace(/<([A-Za-z][\\w:-]*)((?:(?!data-teloce-loop-scope)[^>])*?)data-teloce-model="([^"]*)"((?:(?!data-teloce-loop-scope)[^>])*?)>/g, (_, tag, before, expression, after) => { const encoded = JSON.stringify({ [itemMatch[1]]: value, index }).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); return `<${tag}${before}data-teloce-model="${expression}" data-teloce-loop-scope="${encoded}"${after}>`; }).replace(/{{\\s*([^{}]+?)\\s*}}/g, (_, expression) => { const result = __evaluate(expression, loopScope); return result == null ? "" : __escapeHtml(String(result)); }); }).join("");',
            '      source = source.slice(0, cursor) + rendered + source.slice(closeStart + 6); cursor = source.indexOf("<for ");',
            '    } return source;',
            '  };',
            '  output = __renderLoops(output, state);',
            '  output = __resolveIfBlocks(output, state);',
            '  output = output.replace(/{{\\s*([^{}]+?)\\s*}}/g, (_, expression) => { const value = __evaluate(expression, state); return value == null ? "" : __escapeHtml(String(value)); });',
            '  output = output.replace(/@([\\w.-]+)="([^"]*)"/g, "data-teloce-event-$1=\\"$2\\"");',
            '  output = output.replace(/:([\\w-]+)="([^"]*)"/g, (_, name, expression) => `${name}=\\"${String(__evaluate(expression, state) ?? "").replace(/\\\"/g, "&quot;")}\\"`);',
            '  return output;',
            '};',
            'export function mount(target, props = {}) {',
            '  if (typeof target === "string") target = document.querySelector(target);',
            '  if (!target) throw new Error("Teloce mount target was not found");',
            '  __installStyle();',
            '  let update = () => {}; let rendering = false; let updateQueued = false; let updateScheduled = false; let suppressUpdates = false;',
            '  const requestUpdate = () => { if (suppressUpdates) return; if (rendering || updateScheduled) { updateQueued = true; return; } updateScheduled = true; queueMicrotask(() => { updateScheduled = false; rendering = true; try { update(); } finally { rendering = false; if (updateQueued) { updateQueued = false; requestUpdate(); } } }); };',
            '  let mounted = false; let loopScopes = new Map();',
            '  let previous = {};',
            '  const __reactiveCache = new WeakMap();',
            '  const __reactive = (value, notify) => { if (!value || typeof value !== "object") return value; const cached = __reactiveCache.get(value); if (cached) return cached; const proxy = new Proxy(value, { get(object, key, receiver) { const result = Reflect.get(object, key, receiver); return result && typeof result === "object" ? __reactive(result, notify) : result; }, set(object, key, next, receiver) { const changed = !Object.is(object[key], next); const result = Reflect.set(object, key, next, receiver); if (changed) notify(); return result; }, deleteProperty(object, key) { const existed = Object.prototype.hasOwnProperty.call(object, key); const result = Reflect.deleteProperty(object, key); if (existed) notify(); return result; } }); __reactiveCache.set(value, proxy); return proxy; };',
            '  const state = new Proxy(Object.assign({}, __createInitialData(), __normalizeProps(props)), { get(object, key, receiver) { const value = Reflect.get(object, key, receiver); return value && typeof value === "object" ? __reactive(value, requestUpdate) : value; }, set(object, key, value) { object[key] = value; requestUpdate(); return true; }, deleteProperty(object, key) { const result = delete object[key]; requestUpdate(); return result; } });',
            '  state.$style = __styleClasses;',
            '  for (const [name, getter] of Object.entries(__component.computed || {})) Object.defineProperty(state, name, { enumerable: true, get: () => getter.call(state) });',
            '  const methods = __component.methods || {};',
            '  for (const [name, method] of Object.entries(methods)) state[name] = method.bind(state);',
            '  state.$emit = (name, detail) => target.dispatchEvent(new CustomEvent(`teloce:${name}`, { detail, bubbles: true }));',
            '  const __handleHookError = (error, source) => { if (source !== "errorCaptured" && typeof __component.errorCaptured === "function") { try { const handled = __component.errorCaptured.call(state, error, null, source); if (handled && typeof handled.then === "function") handled.catch(captured => { if (__dev) console.error("Teloce errorCaptured hook failed:", captured); }); if (handled === false) return; } catch (captured) { if (__dev) console.error("Teloce errorCaptured hook failed:", captured); } } if (__dev) console.error(`Teloce ${source} hook failed:`, error); };',
            '  const __callHook = (name, ...args) => { const hook = __component[name]; if (typeof hook !== "function") return; try { const result = hook.call(state, ...args); if (result && typeof result.then === "function") result.catch(error => __handleHookError(error, name)); return result; } catch (error) { __handleHookError(error, name); } };',
            '  suppressUpdates = true; try { __callHook("beforeCreate"); __callHook("created"); } finally { suppressUpdates = false; }',
            '  const __watchValue = name => String(name).split(".").reduce((value, key) => value == null ? undefined : value[key], state);',
            '  previous = Object.fromEntries(Object.keys(__component.watch || {}).map(name => [name, __watchValue(name)]));',
            '  update = () => {',
            '    const wasMounted = mounted;',
            '    if (wasMounted) __callHook("beforeUpdate");',
            '    if (!mounted) __callHook("beforeMount");',
            '    loopScopes = new Map(); __patch(target, __renderTemplate(__template, state, loopScopes));',
            '    const nativeEvents = new Set(["click", "input", "submit", "change", "keyup", "keydown", "focus", "blur", "mouseenter", "mouseleave"]);',
            '    const __eventExpressionScope = values => new Proxy(values, { get(object, key, receiver) { return Reflect.has(object, key) ? Reflect.get(object, key, receiver) : state[key]; }, set(object, key, value, receiver) { if (Reflect.has(state, key)) { state[key] = value; return true; } return Reflect.set(object, key, value, receiver); } });',
            '    const __bindEvents = (element, force = false) => {',
            '      for (const attribute of Array.from(element.attributes)) if (attribute.name.startsWith("data-teloce-event-")) {',
            '        const eventKey = attribute.name.slice("data-teloce-event-".length); const [eventName, ...modifiers] = eventKey.split("."); const handlerName = attribute.value; const actualEvent = nativeEvents.has(eventName) ? eventName : `teloce:${eventName}`;',
            '        if (!element.__teloceHandlers) element.__teloceHandlers = new Map(); const previousHandler = element.__teloceHandlers.get(attribute.name); const signature = eventKey + "=" + handlerName;',
            '        if (force || !previousHandler || previousHandler.signature !== signature) { if (previousHandler) element.removeEventListener(previousHandler.actualEvent, previousHandler.listener, previousHandler.options); const listener = event => { if (modifiers.includes("self") && event.target !== element) return; if (modifiers.includes("enter") && event.key !== "Enter") return; if (modifiers.includes("esc") && event.key !== "Escape") return; if (modifiers.includes("ctrl") && !event.ctrlKey) return; if (modifiers.includes("shift") && !event.shiftKey) return; if (modifiers.includes("alt") && !event.altKey) return; if (modifiers.includes("meta") && !event.metaKey) return; if (modifiers.includes("right") && event.button !== 2) return; if (modifiers.includes("middle") && event.button !== 1) return; if (modifiers.includes("left") && event.button !== 0) return; if (modifiers.includes("prevent")) event.preventDefault(); if (modifiers.includes("stop")) event.stopPropagation(); const eventScope = { ...state }; try { Object.assign(eventScope, JSON.parse(element.getAttribute("data-teloce-loop-scope") || "{}")); } catch (_) {} const handler = state[handlerName]; if (typeof handler === "function") handler(event?.detail ?? event); else __runEventExpression(handlerName, __eventExpressionScope({ ...eventScope, event, $event: event })); }; const options = { once: modifiers.includes("once"), capture: modifiers.includes("capture"), passive: modifiers.includes("passive") }; element.__teloceHandlers.set(attribute.name, { signature, actualEvent, listener, options }); element.addEventListener(actualEvent, listener, options); }',
            '      }',
            '    };',
            '    target.querySelectorAll("*").forEach(element => {',
            '      __bindEvents(element);',
            '      const model = element.getAttribute("data-teloce-model");',
            '      if (model) { let modelScope = state; try { const loopScope = JSON.parse(element.getAttribute("data-teloce-loop-scope") || "null"); if (loopScope) modelScope = { ...state, ...loopScope }; } catch (_) {} const current = __evaluate(model, modelScope); if (element.type === "checkbox") element.checked = Boolean(current); else if (element.value !== String(current ?? "")) element.value = current ?? ""; if (!element.__teloceModel) { element.__teloceModel = true; const eventName = element.type === "checkbox" || element.tagName === "SELECT" ? "change" : "input"; element.addEventListener(eventName, event => { let writeScope = state; try { const loopScope = JSON.parse(element.getAttribute("data-teloce-loop-scope") || "null"); if (loopScope) writeScope = { ...state, ...loopScope }; } catch (_) {} __assign(model, element.type === "checkbox" ? element.checked : element.value, writeScope); }); } }',
            '      for (const attribute of Array.from(element.attributes)) if (attribute.name.startsWith("data-teloce-bind-")) { const name = attribute.name.slice("data-teloce-bind-".length); __applyBinding(element, name, __evaluate(attribute.value, state)); } else if (attribute.name.startsWith("data-teloce-resolved-")) { const name = attribute.name.slice("data-teloce-resolved-".length); let value; try { value = JSON.parse(attribute.value); } catch (_) { value = attribute.value; } __applyBinding(element, name, value); }',
            '      for (const attribute of Array.from(element.attributes)) { const match = attribute.name.match(/^v-([\\w-]+)$/); const directive = match && __pluginDirectives[match[1]]; if (directive?.render) directive.render(element, { name: match[1], expression: attribute.value, value: __evaluate(attribute.value, state), state, modifiers: [] }); }',
            '    });',
            '    const componentLookup = new Map(Object.entries(__components).map(([name, child]) => [name.toLowerCase(), child]));',
            '    const newlyMounted = new Set();',
            '    let mountedChild = true;',
            '    while (mountedChild) {',
            '      mountedChild = false;',
            '      for (const element of Array.from(target.querySelectorAll("*"))) {',
            '        const child = componentLookup.get(element.tagName.toLowerCase());',
            '        if (!child || element.__teloceMounted || typeof child.mount !== "function") continue;',
            '        element.__teloceMounted = true;',
            '        element.__teloceInstance = child.mount(element, __readProps(element, state));',
            '        newlyMounted.add(element);',
            '        mountedChild = true;',
            '        break;',
            '      }',
            '    }',
            '    for (const element of Array.from(target.querySelectorAll("*"))) {',
            '      if (componentLookup.has(element.tagName.toLowerCase()) && !newlyMounted.has(element) && element.__teloceInstance?.updateProps) { const source = element.__telocePendingPropsSource || element; element.__teloceInstance.updateProps(__readProps(source, state)); element.__telocePendingPropsSource = undefined; }',
            '    }',
            '    target.querySelectorAll("teloce-dynamic").forEach(element => {',
            '      const name = __evaluate(element.getAttribute("data-teloce-is") || "", state);',
            '      const child = __components[name] || __components[String(name).replace(/^./, value => value.toUpperCase())];',
            '      if (!element.__teloceMounted && child && typeof child.mount === "function") { element.__teloceMounted = true; element.__teloceInstance = child.mount(element, __readProps(element, state)); } else if (element.__teloceInstance?.updateProps) { element.__teloceInstance.updateProps(__readProps(element, state)); }',
            '    });',
            '    for (const element of Array.from(target.querySelectorAll("*"))) if (componentLookup.has(element.tagName.toLowerCase())) __bindEvents(element, true);',
            '    if (!mounted) { __callHook("mounted"); __callHook("activated"); }',
            '    mounted = true;',
            '    for (const [name, handler] of Object.entries(__component.watch || {})) { const value = __watchValue(name); if (!Object.is(previous[name], value)) { try { const result = handler.call(state, value, previous[name]); if (result && typeof result.then === "function") result.catch(error => __handleHookError(error, `watch:${name}`)); } catch (error) { __handleHookError(error, `watch:${name}`); } previous[name] = value; } }',
            '    if (wasMounted) __callHook("updated");',
            '  };',
            '  update();',
            '  const updateProps = nextProps => { const normalized = __normalizeProps(nextProps); let changed = false; suppressUpdates = true; try { for (const [key, value] of Object.entries(normalized)) if (!Object.is(state[key], value)) { state[key] = value; changed = true; } for (const key of Object.keys(__component.props || {})) if (!(key in normalized) && state[key] !== undefined) { state[key] = undefined; changed = true; } } finally { suppressUpdates = false; } if (changed) { rendering = true; try { update(); } finally { rendering = false; } } };',
            '  const __hmrRecord = { target, state, reload: async () => { const snapshot = {}; for (const key of Object.keys(state)) if (!key.startsWith("$") && typeof state[key] !== "function") snapshot[key] = state[key]; __unregisterHmr(__hmrRecord); const fresh = await import(`${__moduleUrl}?teloce_hmr=${Date.now()}`); return fresh.mount(target, snapshot); } }; __registerHmr(__hmrRecord);',
            '  const __instance = { state, update, updateProps, unmount: () => { if (!mounted) return; __callHook("deactivated"); __callHook("beforeUnmount"); __unregisterHmr(__hmrRecord); const nodes = [...target.querySelectorAll("*")]; nodes.forEach(element => { element.__teloceInstance?.unmount?.(); if (element.__teloceHandlers) for (const record of element.__teloceHandlers.values()) element.removeEventListener(record.actualEvent, record.listener, record.options); element.__teloceHandlers?.clear?.(); element.__teloceInstance = undefined; element.__teloceMounted = false; }); target.replaceChildren(); mounted = false; __callHook("unmounted"); } }; __hmrRecord.instance = __instance; return __instance;',
            '}',
            'export const createApp = mount;',
            '__component.mount = mount;',
        ]
        # Generated template evaluation is always the constrained evaluator.
        # There is no dynamic-code escape hatch in generated output.
        if shared_runtime_import:
            patch_start = next((index for index, line in enumerate(runtime) if line.startswith('const __patch = ')), None)
            if patch_start is not None:
                patch_end = next((index for index in range(patch_start + 1, len(runtime)) if runtime[index] == '};'), None)
                if patch_end is not None:
                    del runtime[patch_start:patch_end + 1]
            runtime = [line for line in runtime if not line.startswith('  const __reactive = ')]
            runtime = [line.replace(
                'const state = new Proxy(Object.assign({}, __createInitialData(), __normalizeProps(props)), { get(object, key, receiver) { const value = Reflect.get(object, key, receiver); return value && typeof value === "object" ? __reactive(value, requestUpdate) : value; }, set(object, key, value) { object[key] = value; requestUpdate(); return true; }, deleteProperty(object, key) { const result = delete object[key]; requestUpdate(); return result; } });',
                'const state = __createReactive(Object.assign({}, __createInitialData(), __normalizeProps(props)), requestUpdate);',
            ) for line in runtime]
        return [
            line
            .replace("else __evaluate(handlerName", "else __runEventExpression(handlerName")
            # A binding may create a real DOM attribute after the declarative
            # template is cloned. Mark it managed so a later conditional
            # branch can remove stale boolean attributes such as `disabled`.
            .replace(
                'const __applyBinding = (element, name, value) => { ',
                'const __applyBinding = (element, name, value) => { element.__teloceManagedAttributes ||= new Set(); element.__teloceManagedAttributes.add(name); ',
            )
            .replace(
                'const encoded = JSON.stringify({ [itemMatch[1]]: value, index }).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); return `<${tag}${before}data-teloce-event-${name}="${expression}" data-teloce-loop-scope="${encoded}"${after}>`;',
                'const scopeId = String(loopScopes.size); loopScopes.set(scopeId, loopScope); return `<${tag}${before}data-teloce-event-${name}="${expression}" data-teloce-loop-scope="${scopeId}"${after}>`;',
            )
            .replace(
                'const eventScope = { ...state }; try { Object.assign(eventScope, JSON.parse(element.getAttribute("data-teloce-loop-scope") || "{}")); } catch (_) {} const handler = state[handlerName]; if (typeof handler === "function") handler(event?.detail ?? event); else __runEventExpression(handlerName, __eventExpressionScope({ ...eventScope, event, $event: event }));',
                'const scopeId = element.getAttribute("data-teloce-loop-scope"); const eventScope = { ...state, ...(scopeId == null ? {} : loopScopes.get(scopeId) || {}) }; try { const handler = state[handlerName]; const result = typeof handler === "function" ? handler(event?.detail ?? event) : __runEventExpression(handlerName, __eventExpressionScope({ ...eventScope, event, $event: event })); if (result && typeof result.then === "function") result.catch(error => __handleHookError(error, `event:${eventName}`)); } catch (error) { __handleHookError(error, `event:${eventName}`); }',
            )
            .replace(
                'const encoded = JSON.stringify({ [itemMatch[1]]: value, index }).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); return `<${tag}${before}data-teloce-model="${expression}" data-teloce-loop-scope="${encoded}"${after}>`;',
                'const scopeId = String(loopScopes.size); loopScopes.set(scopeId, loopScope); return `<${tag}${before}data-teloce-model="${expression}" data-teloce-loop-scope="${scopeId}"${after}>`;',
            )
            .replace(
                'JSON.parse(element.getAttribute("data-teloce-loop-scope") || "null")',
                '(loopScopes.get(element.getAttribute("data-teloce-loop-scope")) || null)',
            )
            # Run user handlers after the native event dispatch finishes. This
            # prevents synchronous DOM reconciliation from mutating the active
            # event target and keeps state updates consistently batched.
            .replace(
                'const handler = state[handlerName]; if (typeof handler === "function") handler(event?.detail ?? event); else __runEventExpression(handlerName, { ...state, event, $event: event });',
                'queueMicrotask(() => { const handler = state[handlerName]; if (typeof handler === "function") handler(event?.detail ?? event); else __runEventExpression(handlerName, { ...state, event, $event: event }); });',
            )
            for line in runtime
        ]

    def _component_imports(self, component: Component) -> dict:
        """Return local component names and their generated import paths."""
        configured = self.options.get("component_imports", {})
        imports = {}
        extensions = source_extension_pattern(self.source_extensions)
        pattern = rf'(?m)^\s*import\s+([A-Za-z_$][\w$]*)(?:\s*,\s*\{{[^}}]*\}})?\s+from\s+[\'\"]([^\'\"]+{extensions})[\'\"]\s*;?'
        for match in re.finditer(pattern, component.script.raw):
            name, source = match.groups()
            imports[name] = configured.get(name, self._compiled_import(source))
        named_pattern = rf'(?m)^\s*import\s*\{{([^}}]+)\}}\s*from\s+[\'\"]([^\'\"]+{extensions})[\'\"]\s*;?'
        for match in re.finditer(named_pattern, component.script.raw):
            source = match.group(2)
            for item in match.group(1).split(','):
                parts = re.split(r'\s+as\s+', item.strip())
                name = parts[-1].strip()
                if name:
                    imports[name] = configured.get(name, self._compiled_import(source))
        return imports

    def _generate_component_imports(self, component: Component) -> List[str]:
        """Emit browser imports for local component dependencies."""
        configured = self.options.get("component_imports", {})
        lazy_components = set(self.options.get("lazy_components", ()) or ())
        lines = []
        lazy_lines = []
        emitted = set()
        for item in getattr(component.script, "imports", []):
            source = item.source
            if not source.endswith(self.source_extensions):
                continue
            local = item.alias or (item.names[0] if item.names else "")
            path = configured.get(local, self._compiled_import(source))
            if not local or (local, path, item.is_default, item.is_namespace) in emitted:
                continue
            if self.options.get("tree_shake", False) and item.is_default and local not in self._used_components:
                continue
            emitted.add((local, path, item.is_default, item.is_namespace))
            if local in lazy_components and item.is_default:
                lazy_lines.append(f'const {local} = __teloceLazy(() => import({json.dumps(path)}));')
                continue
            if item.is_namespace:
                lines.append(f'import * as {local} from {json.dumps(path)};')
            elif item.is_default:
                lines.append(f'import {local} from {json.dumps(path)};')
            else:
                imported = item.names[0]
                binding = imported if imported == local else f'{imported} as {local}'
                lines.append(f'import {{ {binding} }} from {json.dumps(path)};')
        # Keep compatibility with manually constructed Component objects that
        # do not carry ScriptImport metadata.
        if not lines and not lazy_lines:
            for name, path in self._component_imports(component).items():
                if self.options.get("tree_shake", False) and name not in self._used_components:
                    continue
                if name in lazy_components:
                    lazy_lines.append(f'const {name} = __teloceLazy(() => import({json.dumps(path)}));')
                else:
                    lines.append(f'import {name} from {json.dumps(path)};')
        if lazy_lines:
            runtime_import = self.options.get("shared_runtime_import")
            if runtime_import:
                lines.insert(0, f'import {{ __teloceLazy }} from {json.dumps(runtime_import)};')
            else:
                helper = ('const __teloceLazy = loader => { let loading; let loaded; return { mount(target, props = {}) { const instance = { updateProps(next) { loaded?.updateProps?.(next); }, unmount() { loaded?.unmount?.(); target.replaceChildren(); } }; loading ||= loader().then(module => { const component = module.default || module; if (component?.mount) loaded = component.mount(target, props); return loaded; }); target.setAttribute("data-teloce-loading", "true"); loading.then(() => target.removeAttribute("data-teloce-loading")); return instance; } }; };')
                lines.append(helper)
            lines.extend(lazy_lines)
        return lines

    def _compiled_import(self, source: str) -> str:
        for extension in self.source_extensions:
            if source.endswith(extension):
                return source[: -len(extension)] + ".js"
        return source

    def _strip_component_imports(self, source: str) -> str:
        """Defensively remove imports emitted by component import generation."""
        if not source:
            return ""
        extensions = source_extension_pattern(self.source_extensions)
        patterns = (
            rf'(?m)^\s*import\s+[^;\n]+?\s+from\s+[\'\"][^\'\"]+{extensions}[\'\"]\s*;?\s*$',
            rf'(?m)^\s*import\s+[\'\"][^\'\"]+{extensions}[\'\"]\s*;?\s*$',
        )
        cleaned = source
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        return cleaned.strip()

    def _collect_component_tags(self, nodes: List[ASTNode]) -> set[str]:
        """Collect custom element names referenced by the template AST."""
        names: set[str] = set()
        def visit(node: ASTNode) -> None:
            if isinstance(node, ElementNode):
                if node.tag and (node.tag[0].isupper() or "-" in node.tag):
                    names.add(node.tag)
                for child in node.children:
                    visit(child)
            elif isinstance(node, (ForNode, IfNode, ComponentNode, SlotNode, FragmentNode)):
                for child in getattr(node, "children", []):
                    visit(child)
                if isinstance(node, IfNode):
                    for child in node.else_children:
                        visit(child)
        for node in nodes:
            visit(node)
        return names

    def _collect_actions(self, nodes: List[ASTNode]) -> set[str]:
        """Collect ``use:name`` action names from the template AST."""
        names: set[str] = set()

        def visit(node: ASTNode) -> None:
            if isinstance(node, ElementNode):
                for name in node.attributes:
                    if re.fullmatch(r"use:[A-Za-z_$][\w$]*", name):
                        names.add(name[4:])
                for child in node.children:
                    visit(child)
            elif isinstance(node, (ForNode, IfNode, ComponentNode, SlotNode, FragmentNode)):
                for child in getattr(node, "children", []):
                    visit(child)
                if isinstance(node, IfNode):
                    for child in node.else_children:
                        visit(child)

        for node in nodes:
            visit(node)
        return names

    @staticmethod
    def _collect_actions_from_template(template: str) -> set[str]:
        return set(re.findall(r'\buse:([A-Za-z_$][\w$]*)', template or ""))

    @staticmethod
    def _generate_actions(names: set[str]) -> str:
        """Reference action functions without making missing actions fatal at import."""
        if not names:
            return "{}"
        entries = [
            f'{json.dumps(name)}: (typeof {name} === "function" ? {name} : undefined)'
            for name in sorted(names)
        ]
        return "{ " + ", ".join(entries) + " }"

    def _next_direct_record(self, kind: str, expression: str, name: str = "") -> Optional[dict]:
        """Consume optimizer metadata in AST/generator traversal order."""
        if (
            not self._direct_plan.get("enabled")
            or self._direct_region_depth
            or self._direct_plan.get("fallback")
        ):
            return None
        records = self._direct_plan.get("bindings") or []
        for index in range(self._direct_cursor, len(records)):
            record = records[index]
            if (
                record.get("kind") == kind
                and record.get("expression", "") == str(expression or "")
                and (not name or record.get("name") == name)
            ):
                self._direct_cursor = index + 1
                self._emitted_direct_ids.add(record["id"])
                return record
        # A transformed AST can merge or normalize nodes. Keep compilation
        # deterministic even if an optimizer record is no longer available.
        prefix = "t" if kind == "text" else "b"
        fallback_index = sum(1 for record in records if record.get("kind") == kind)
        return {
            "id": f"{prefix}{fallback_index}",
            "kind": kind,
            "name": name,
            "expression": str(expression or ""),
            "dependencies": [],
            "line": None,
            "column": None,
        }

    @staticmethod
    def _has_unsupported_regions(nodes: List[ASTNode]) -> bool:
        for node in nodes:
            if isinstance(node, (SlotNode, ComponentNode)) or getattr(node, 'virtual', False):
                return True
            if isinstance(node, ElementNode) and node.tag.lower() in {'component', 'slot', 'table', 'select', 'svg'}:
                return True
            if Generator._has_unsupported_regions(getattr(node, 'children', []) or []):
                return True
            if Generator._has_unsupported_regions(getattr(node, 'else_children', []) or []):
                return True
        return False

    def _generate_region(self, node: ASTNode) -> str:
        """Anchor one outer structural block without changing HTML semantics."""
        from teloce.compiler.optimizer import Optimizer
        index = len(self._direct_regions)
        record = {'id': f'r{index}', 'dependencies': [], 'template': ''}
        self._direct_regions.append(record)
        def collect(current):
            expressions = [getattr(current, name, '') for name in ('expression', 'condition', 'collection', 'key')]
            expressions.extend(binding.value for binding in getattr(current, 'bindings', []) or [])
            expressions.extend((getattr(current, 'props', {}) or {}).values())
            for expression in expressions:
                for dependency in Optimizer._dependencies(str(expression or '')):
                    if dependency not in record['dependencies']:
                        record['dependencies'].append(dependency)
                # Arbitrary calls can read other state through methods/filters.
                if '(' in str(expression or '') or '|' in str(expression or ''):
                    if '*' not in record['dependencies']:
                        record['dependencies'].append('*')
            for child in [*(getattr(current, 'children', []) or []), *(getattr(current, 'else_children', []) or [])]:
                collect(child)
        collect(node)
        pending = list(record['dependencies'])
        while pending:
            dependency = pending.pop()
            for root in Optimizer._dependencies(self._computed_bodies.get(dependency, '')):
                if root not in record['dependencies']:
                    record['dependencies'].append(root)
                    pending.append(root)
        self._direct_region_depth += 1
        try:
            markup = self._generate_for(node) if isinstance(node, ForNode) else self._generate_if(node)
        finally:
            self._direct_region_depth -= 1
        record['template'] = markup
        row_plan = self._keyed_row_plan(node, markup)
        if row_plan:
            record['rows'] = row_plan
        return f'<!--teloce-region:{record["id"]}-->{markup}<!--teloce-region-end:{record["id"]}-->'

    def _keyed_row_plan(self, node: ASTNode, markup: str) -> Optional[dict]:
        """Cache rows only when every rendered dependency is a simple path.

        Calls, nested structures, computed values and integrations retain the
        general region renderer rather than risking an incomplete dependency set.
        """
        if not isinstance(node, ForNode) or not node.key or node.key == 'index' or getattr(node, 'index', 'index') != 'index':
            return None
        if len(node.children) != 1 or not isinstance(node.children[0], ElementNode):
            return None
        paths = set()
        def visit(current):
            if isinstance(current, (ForNode, IfNode, ComponentNode, SlotNode)):
                return False
            expressions = [getattr(current, 'expression', '')]
            expressions.extend(binding.value for binding in getattr(current, 'bindings', []) or [])
            for expression in expressions:
                expression = str(expression or '').strip()
                if not expression:
                    continue
                if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', expression):
                    return False
                if expression.split('.')[0] in self._computed_bodies:
                    return False
                paths.add(expression)
            return all(visit(child) for child in getattr(current, 'children', []) or [])
        if not visit(node.children[0]):
            return None
        match = re.fullmatch(r'<for key="([^"<>]*)" item="([^"<>]*)" in="([^"<>]*)">(.*)</for>', markup, re.S)
        if not match:
            return None
        key, item, collection, body = match.groups()
        if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', key):
            return None
        # Authored interpolations in ordinary attributes must also be tracked.
        for expression in re.findall(r'{{\s*(.*?)\s*}}', body):
            if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', expression):
                return None
            if expression.split('.')[0] in self._computed_bodies:
                return None
            paths.add(expression)
        return {'item': item, 'collection': html.unescape(collection), 'key': html.unescape(key),
                'body': body, 'paths': sorted(paths)}

    @staticmethod
    def _binding_reader(expression: str) -> Optional[str]:
        """Emit simple safe state reads; complex expressions keep the evaluator."""
        expression = expression.strip()
        if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*', expression):
            return None
        parts = expression.split('.')
        blocked = {'__proto__', 'prototype', 'constructor', 'caller', 'callee', 'arguments'}
        builtins = {'true', 'false', 'null', 'undefined', 'Math', 'Number', 'String', 'Boolean', 'Array', 'Object', 'JSON', 'Date', 'parseInt', 'parseFloat', 'isNaN', 'this'}
        if parts[0] in builtins or any(part in blocked for part in parts):
            return None
        root = json.dumps(parts[0])
        read = 'scope[' + root + ']' + ''.join('?.[' + json.dumps(part) + ']' for part in parts[1:])
        return 'scope => Object.prototype.hasOwnProperty.call(scope, ' + root + ') ? ' + read + ' : undefined'

    def _direct_plan_literal(self) -> str:
        """Serialize stable metadata and compiler-generated safe readers."""
        if not self._direct_plan.get('enabled'):
            return '{ enabled: false, structural: false, fallback: false, refreshIntegrations: false, bindings: [] }'
        plan = {
            'version': 2, 'enabled': True,
            'structural': bool(self._direct_plan.get('structural')),
            'targetedStructural': self._targeted_structural,
            'fallback': bool(self._direct_plan.get('fallback')),
            'refreshIntegrations': bool(self._direct_plan.get('refreshIntegrations')),
            'regions': self._direct_regions,
        }
        bindings = []
        for record in self._direct_plan.get('bindings', []):
            if record['id'] not in self._emitted_direct_ids:
                continue
            literal = json.dumps(record, ensure_ascii=False)
            reader = self._binding_reader(record['expression'])
            if reader:
                literal = literal[:-1] + ', read: ' + reader + '}'
            bindings.append(literal)
        return json.dumps(plan, ensure_ascii=False)[:-1] + ', "bindings": [' + ', '.join(bindings) + ']}'

    def _generate_template(self, nodes: List[ASTNode]) -> str:
        """Generate template code from AST nodes."""
        result = []
        for node in nodes:
            result.append(self._generate_node(node))
        return ''.join(result)
    
    def _generate_node(self, node: ASTNode) -> str:
        """Generate code for a single node."""
        if isinstance(node, ElementNode):
            return self._generate_element(node)
        elif isinstance(node, TextNode):
            return self._generate_text(node)
        elif isinstance(node, InterpolationNode):
            return self._generate_interpolation(node)
        elif isinstance(node, ForNode):
            if self._targeted_structural and not self._direct_region_depth and self._direct_plan.get("enabled") and not self._direct_plan.get("fallback"):
                return self._generate_region(node)
            return self._generate_for(node)
        elif isinstance(node, IfNode):
            if self._targeted_structural and not self._direct_region_depth and self._direct_plan.get("enabled") and not self._direct_plan.get("fallback"):
                return self._generate_region(node)
            return self._generate_if(node)
        else:
            return ''
    
    def _generate_element(self, node: ElementNode) -> str:
        """Generate code for an element."""
        tag = node.tag
        attrs = []
        direct_binding_ids = []

        dynamic_expression = None
        if tag.lower() == "component":
            for binding in node.bindings:
                if binding.name == "is":
                    dynamic_expression = binding.value
                    break
            tag = "teloce-dynamic"
            if dynamic_expression:
                attrs.append(f'data-teloce-is="{html.escape(dynamic_expression, quote=True)}"')

        if self.scope_id and not any(name.startswith('data-v-') for name in node.attributes):
            attrs.append(f'{self.scope_id}=""')
        
        # Regular attributes
        has_class_binding = any(binding.name == "class" for binding in node.bindings)
        for name, value in node.attributes.items():
            if name == "class" and self.module_mapping:
                value = " ".join(self.module_mapping.get(token, token) for token in str(value).split())
            emitted_name = {
                "v-memo": "data-teloce-memo",
                "v-scrolly": "data-teloce-scrolly",
                "v-chart-annotation": "data-teloce-chart-annotation",
                "v-data-table": "data-teloce-data-table",
            }.get(name, name)
            # Memo keys are expressions, not static strings. Keep the
            # expression in the generated template so the renderer evaluates
            # it for every update before reconciliation compares keys.
            emitted_value = f'{{{{ {value} }}}}' if name == "v-memo" else value
            attrs.append(f'{emitted_name}="{html.escape(str(emitted_value), quote=True)}"')
            if name == "class" and has_class_binding:
                attrs.append(f'data-teloce-static-class="{html.escape(str(value), quote=True)}"')
        
        # Bindings
        for binding in node.bindings:
            direct_record = (
                self._next_direct_record("binding", binding.value, binding.name)
                if binding.name != "attrs" else None
            )
            if direct_record:
                direct_binding_ids.append(direct_record["id"])
            if dynamic_expression is not None and binding.name == "is":
                continue
            if binding.name == 'model' or binding.name.startswith('model.'):
                attrs.append(f'data-teloce-model="{html.escape(binding.value, quote=True)}"')
                modifiers = binding.name.partition('.')[2]
                if modifiers:
                    attrs.append(f'data-teloce-model-modifiers="{html.escape(modifiers, quote=True)}"')
            elif binding.name == 'class':
                attrs.append(f'data-teloce-bind-class="{html.escape(binding.value, quote=True)}"')
            elif binding.name == 'style':
                attrs.append(f'data-teloce-bind-style="{html.escape(binding.value, quote=True)}"')
            elif binding.name == 'show':
                attrs.append(f'data-teloce-bind-show="{html.escape(binding.value, quote=True)}"')
            elif binding.name == 'hide':
                attrs.append(f'data-teloce-bind-hide="{html.escape(binding.value, quote=True)}"')
            else:
                attrs.append(f'data-teloce-bind-{binding.name}="{html.escape(binding.value, quote=True)}"')

        if direct_binding_ids:
            attrs.append(
                f'data-teloce-direct-bindings="{html.escape(",".join(direct_binding_ids), quote=True)}"'
            )
        
        # Events
        for event in node.events:
            attrs.append(f'@{event.name}="{event.handler}"')

        # Transition/animation directives
        for directive in getattr(node, "transitions", []):
            attr_name = f'data-teloce-{directive.kind}'
            payload = f'{directive.name}:{directive.params}' if directive.params else directive.name
            attrs.append(f'{attr_name}="{html.escape(payload, quote=True)}"')
        
        # Build opening tag
        attrs_str = ' ' + ' '.join(attrs) if attrs else ''
        opening = f'<{tag}{attrs_str}>'
        
        # Children
        children_html = self._generate_template(node.children)
        
        # Closing tag
        closing = '' if ElementFactory.is_void(tag) else f'</{tag}>'
        
        return f'{opening}{children_html}{closing}'
    
    def _generate_text(self, node: TextNode) -> str:
        """Generate code for text."""
        return node.value
    
    def _generate_interpolation(self, node: InterpolationNode) -> str:
        """Generate code for interpolation."""
        record = self._next_direct_record("text", node.expression)
        if not record:
            return f'{{{{ {node.expression} }}}}'
        marker = record["id"]
        # Paired comments force the browser to keep the interpolation's text
        # node separate from any authored prefix/suffix text. Without the end
        # anchor, `Hello {{ name }}!` becomes one `Hello`/`name!` text node and
        # a direct update would accidentally delete the exclamation mark.
        return f'<!--teloce-text:{marker}-->{{{{ {node.expression} }}}}<!--teloce-text-end:{marker}-->'
    
    def _generate_for(self, node: ForNode) -> str:
        """Generate code for for loop."""
        item = node.item or 'item'
        collection = node.collection or 'items'
        key = node.key or 'index'
        
        children = self._generate_template(node.children)
        key_expression = "index"
        if node.key and node.key != "index":
            # Give the DOM reconciler a stable identity for each repeated row.
            key_expression = node.key if not node.key.isidentifier() or node.key in {item, getattr(node, "index", "index")} else f"{item}.{node.key}"
            children = re.sub(
                r"<([A-Za-z][\w:-]*)",
                rf'<\1 data-teloce-key="{{{{ {key_expression} }}}}"',
                children,
                count=1,
            )
        tag = "virtual-for" if getattr(node, "virtual", False) else "for"
        index_name = getattr(node, "index", "index")
        options = f' index="{html.escape(index_name, quote=True)}"' if index_name != "index" else ""
        for option, value in getattr(node, "virtual_options", {}).items():
            options += f' {option}="{html.escape(str(value), quote=True)}"'
        return f'<{tag} key="{html.escape(key_expression, quote=True)}" item="{item}" in="{collection}"{options}>{children}</{tag}>'
    
    def _generate_if(self, node: IfNode) -> str:
        """Generate code for if statement."""
        condition = node.condition or 'condition'
        
        children = self._generate_template(node.children)
        
        if node.else_children:
            else_children = self._generate_template(node.else_children)
            return f'<if condition="{condition}">{children}<else>{else_children}</if>'
        
        return f'<if condition="{condition}">{children}</if>'
    
    def _indent(self) -> str:
        """Get the current indentation."""
        return '  ' * self.indent_level

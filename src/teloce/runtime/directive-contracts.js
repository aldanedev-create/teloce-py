/**
 * Contracts for compiler-lowered directives and browser directive extensions.
 * This module defines JSDoc types only; it executes no directive behavior.
 * @module
 */
/** @import {DynamicRecord, DynamicValue} from './contracts.js' */

/**
 * Context passed to custom `v-name.modifier` hooks. Values are evaluated in the
 * nearest loop scope; `state` includes row locals and live component state.
 * `oldValue` is the previously evaluated value, not a deep historical snapshot.
 * @template [T=unknown]
 * @typedef {{name: string, expression: string, value: T, oldValue?: T,
 *   state: DynamicRecord, modifiers: string[]}} DirectiveContext
 */
/**
 * A directive-owned resource. Runtime calls these methods with this resource
 * as their receiver. `destroy` must release listeners, observers and timers.
 * @template [T=unknown]
 * @typedef {{update?: (context: DirectiveContext<T>) => void, destroy?: () => void}} DirectiveResource
 */
/** @template [T=unknown]
 * @typedef {void | (() => void) | DirectiveResource<T>} DirectiveMountResult
 */
/**
 * A custom directive registers `render` or `mounted` to create its resource.
 * Compiled rendering calls resource.update or updated on value changes, and
 * beforeUnmount -> resource cleanup -> destroy -> unmounted on disposal.
 * Each hook receives the directive definition as its receiver. Standalone
 * rendering replaces nodes and therefore destroys/recreates resources.
 * @template [T=unknown]
 * @typedef {{name?: string,
 *   render?: (element: Element, context: DirectiveContext<T>) => DirectiveMountResult<T>,
 *   mounted?: (element: Element, context: DirectiveContext<T>) => DirectiveMountResult<T>,
 *   updated?: (element: Element, context: DirectiveContext<T>) => void,
 *   beforeUnmount?: (element: Element, context: DirectiveContext<T>) => void,
 *   destroy?: (element: Element, context: DirectiveContext<T>) => void,
 *   unmounted?: (element: Element, context: DirectiveContext<T>) => void}} CustomDirective
 */
/** @template [T=unknown]
 * @typedef {{signature: string, valueSignature?: string, directive: CustomDirective<T>,
 *   context: DirectiveContext<T>, cleanup?: () => void,
 *   update?: (context: DirectiveContext<T>) => void}} DirectiveRecord
 */
/** @typedef {Element & {__teloceDirectives?: Map<string, DirectiveRecord<DynamicValue>>}} CustomDirectiveElement */

/**
 * Native event modifiers. Keyboard/mouse filters run before prevent/stop.
 * `.once`, `.capture`, `.passive` are native addEventListener options.
 * `.passive.prevent` cannot prevent the browser default; avoid that combination.
 * @typedef {'self'|'enter'|'esc'|'ctrl'|'shift'|'alt'|'meta'|'right'|'middle'|'left'|'prevent'|'stop'|'once'|'capture'|'passive'} EventModifier
 */
/** Listener ownership for `@event`/v-on; remove with the original capture option.
 * @typedef {{actualEvent: string, signature: string, listener: EventListener,
 *   options: AddEventListenerOptions}} EventRecord
 */
/**
 * `v-model.trim` normalizes text, `.number` converts finite numeric strings,
 * `.lazy` commits on change. Composition owns the control until it ends.
 * Checkbox arrays compare string values; radios and select options use strings.
 * @typedef {'trim'|'number'|'lazy'} ModelModifier
 */
/** @typedef {string|number|boolean|string[]|null|undefined} ModelValue */
/** Native controls accepted by v-model (component models are a separate path).
 * @typedef {HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement} ModelControl
 */
/** @typedef {{eventName: 'input'|'change', signature: string, modifiers: Set<string>,
 *   listener: EventListener, compositionStart: EventListener, compositionEnd: EventListener,
 *   composing: boolean, lastValue?: DynamicValue}} ModelRecord
 */

/** `use:action` receives an element and arbitrary evaluated parameters.
 * Object results retain their receiver for update/destroy; function results are
 * cleanup callbacks. Changes call update, otherwise destroy and create again.
 * @template [T=unknown]
 * @typedef {void|(()=>void)|{update?: (params: T) => void, destroy?: () => void}} ActionResult
 */
/** @template [T=unknown]
 * @typedef {(element: Element, params: T) => ActionResult<T>} DomAction
 */
/** @typedef {{signature: string, params: DynamicValue,
 *   update?: (params: DynamicValue) => void, destroy?: () => void}} ActionRecord */

/** `:class` merges with static classes; arrays/objects represent class tokens.
 * @typedef {string|string[]|Record<string, unknown>|null|undefined} ClassValue
 */
/** `:style` sets property values and removes obsolete managed properties.
 * @typedef {string|Record<string, string|number|null|undefined>|null|undefined} StyleValue
 */
/** `:attrs` forwards attributes while blocking internal metadata, inline
 * handler/srcdoc attributes and dangerous URL schemes. Values false/null remove.
 * @typedef {Record<string, string|number|boolean|null|undefined|ClassValue|StyleValue>} ForwardedAttributes
 */
/** `v-show`/hide preserve nodes and use JavaScript truthiness, not string parsing.
 * @typedef {unknown} VisibilityValue
 */
/** `v-text` writes textContent, escaping markup through the DOM API.
 * @typedef {string|number|boolean|null|undefined} TextValue
 */
/** `v-html` accepts HTML strings processed by the runtime sanitizer. Treat
 * untrusted HTML with a dedicated, reviewed sanitizer; this is not a trust type.
 * @typedef {string|null|undefined} HtmlValue
 */
/** `v-if`/v-else-if/v-else select structural branches through the compiled plan.
 * @typedef {unknown} ConditionalValue
 */
/** `v-for` accepts arrays or object values. Stable unique :key expressions
 * preserve row identity; index aliases belong to each row, not global state.
 * @template [T=unknown]
 * @typedef {T[]|Record<string,T>} LoopCollection
 */
/** `v-memo` supplies dependency snapshots to reconciliation, not an event hook.
 * @typedef {string|number|boolean|null|unknown[]} MemoDependencies
 */
/** v-virtual-for uses the loop value plus row-height, overscan and viewport
 * metadata. It owns a scroll listener and pending animation-frame cleanup.
 * @typedef {{itemHeight?: number, overscan?: number, minHeight?: number}} VirtualListOptions
 */
/** v-scrolly owns an observer/focus listeners; v-step names active steps.
 * Observer callbacks must be ignored after cleanup.
 * @typedef {{name: string, element: Element}} StepDetail
 */
/** v-chart-annotation manages an aside, textContent and positioning.
 * @typedef {{text?: string, target?: string, position?: 'top'|'bottom', x?: number}} AnnotationValue
 */
/** poll uses a URL, millisecond interval and optional state path. One request
 * runs at a time; cleanup aborts it and blocks late body callbacks.
 * @typedef {{url: string, interval?: number, target?: string}} PollOptions
 */
/** live accepts ws/wss URLs or named adapters. Adapter callbacks must stop
 * affecting state after disposal; cleanup releases connections and retries.
 * @typedef {(apply: (payload: DynamicValue) => void) => void|(()=>void)|{destroy:()=>void}} LiveAdapter
 */
/** data-table supplies configuration to the table factory; cleanup unmounts it.
 * @typedef {import('./contracts.js').TableOptions} DataTableValue
 */
/** data-teloce-link marks navigation links handled by the SPA router, not by
 * custom directive hooks. The href remains a normal URL for browser fallback.
 * @typedef {string} SpaLinkUrl
 */
/** @typedef {{'model':ModelValue,'show':VisibilityValue,'hide':VisibilityValue,
 * 'text':TextValue,'html':HtmlValue,'class':ClassValue,'style':StyleValue,
 * 'attrs':ForwardedAttributes,'if':ConditionalValue,'for':LoopCollection,
 * 'memo':MemoDependencies,'virtual-for':LoopCollection,'scrolly':boolean,
 * 'step':string,'chart-annotation':AnnotationValue,'poll':PollOptions,
 * 'live':string,'data-table':DataTableValue,'link':SpaLinkUrl}} BuiltinDirectiveValues
 */
export {};

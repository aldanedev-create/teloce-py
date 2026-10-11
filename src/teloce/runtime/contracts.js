/**
 * Values originating in user component state, plugins and evaluated expressions.
 * These open boundaries deliberately permit arbitrary application values; the
 * scheduler, signals, DOM handles and framework-owned records use narrower types.
 * @typedef {any} DynamicValue
 */
/** @typedef {Record<PropertyKey, DynamicValue>} DynamicRecord */

/** @typedef {(...args: DynamicValue[]) => DynamicValue} DynamicCallback */ /**
 * Compiler renderer nodes carry private expando records for mounted directives,
 * child components and event/model listeners. Extensions remain dynamic.
 * @typedef {Node & DynamicRecord} RuntimeElement
 */
/** @typedef {Event & Partial<KeyboardEvent & MouseEvent & MessageEvent>} RuntimeEvent */
export {};

/**
 * @typedef {{delimiter?: string, tsv?: boolean, headers?: false | string[],
 *   strict?: boolean, types?: Record<string, string | DynamicCallback>,
 *   signal?: AbortSignal, columns?: string[],
 *   onRowError?: (error: {row: number, expected: number, received: number}) => void}} DataOptions
 */
/** @typedef {{key: string, label?: string, sortable?: boolean,
 *   render?: (value: DynamicValue, row: DynamicRecord) => Node | string | number | null}} TableColumn
 */
/** @typedef {{columns?: Array<string | TableColumn>, rows?: DynamicRecord[],
 *   pageSize?: number, key?: (row: DynamicRecord) => string | number,
 *   searchPlaceholder?: string, emptyText?: string, sortable?: boolean,
 *   virtual?: boolean}} TableOptions
 */
/** @typedef {{data?: () => DynamicRecord,
 *   render?: (state: DynamicRecord, props: DynamicRecord) => Node,
 *   beforeMount?: DynamicCallback, mounted?: DynamicCallback,
 *   updated?: DynamicCallback, beforeUnmount?: DynamicCallback,
 *   unmounted?: DynamicCallback} & DynamicRecord} ComponentDefinition
 */
/** @typedef {{definition: ComponentDefinition, props: DynamicRecord,
 *   state: DynamicRecord, mounted: boolean,
 *   mount: (target: string | Element | null) => ComponentInstance,
 *   updateProps: (props?: DynamicRecord) => ComponentInstance,
 *   unmount: () => ComponentInstance}} ComponentInstance
 */
/** @typedef {{loading?: Node | (() => Node), error?: Node | ((error: unknown) => Node),
 *   onError?: (error: unknown) => void}} AsyncOptions
 */
/** @typedef {{template?: string, components?: DynamicRecord, filters?: Record<string, DynamicCallback>,
 *   actions?: DynamicRecord, table?: DynamicCallback, style?: string, styleId?: string,
 *   styleClasses?: Record<string, string>, dev?: boolean, moduleUrl?: string,
 *   hydrate?: boolean, direct?: boolean, directPlan?: DynamicRecord, props?: DynamicRecord,
 *   component?: string, sourceLocations?: DynamicRecord, onError?: (error: unknown, phase: string) => void}} CompiledOptions
 */

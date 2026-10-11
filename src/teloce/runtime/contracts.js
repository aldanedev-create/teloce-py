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
 *   hydrate?: boolean, direct?: boolean, directPlan?: DirectPlan, props?: DynamicRecord,
 *   component?: string, sourceLocations?: DynamicRecord, onError?: (error: unknown, phase: string) => void}} CompiledOptions
 */

/** Mounted child resources owned by the compiled renderer.
 * @typedef {{updateProps?: (props: DynamicRecord) => void, unmount?: () => void}} MountedChild
 */

/** A public error report consumed by host integrations.
 * @typedef {{category: string, message: string, stack: string, phase?: string,
 *   expression?: string | null, component?: string, filename?: string,
 *   line?: number, column?: number}} RuntimeDiagnostic
 */
/** Compiler-owned simple binding; evaluated application values remain dynamic.
 * @typedef {{id: string, kind: 'text' | 'binding', name: string, expression: string,
 *   dependencies?: string[], read?: (state: DynamicRecord) => DynamicValue}} DirectBinding
 */
/** @typedef {{item: string, collection: string, key: string, body: string,
 *   paths: string[]}} KeyedRowPlan
 */
/** @typedef {{id: string, template: string, dependencies?: string[], rows?: KeyedRowPlan}} DirectRegion
 */
/** @typedef {{enabled?: boolean, fallback?: boolean | string, structural?: boolean,
 *   targetedStructural?: boolean, refreshIntegrations?: boolean,
 *   bindings?: DirectBinding[], regions?: DirectRegion[]}} DirectPlan
 */

/** @typedef {{type?: string, required?: boolean, default?: DynamicValue,
 *   defaultFactory?: () => DynamicValue, validator?: (value: DynamicValue) => boolean}} PropDescriptor
 */
/** @typedef {{key?: string, type?: string}} QueryDescriptor */
/** Public compiled component definition; state and plugin extensions stay open.
 * @typedef {{name?: string, data?: () => DynamicRecord,
 *   props?: Record<string, string | PropDescriptor>,
 *   queryState?: Record<string, string | QueryDescriptor>,
 *   methods?: Record<string, DynamicCallback>, computed?: Record<string, DynamicCallback>,
 *   watch?: Record<string, (value: DynamicValue, previous: DynamicValue) => DynamicValue>} & DynamicRecord} CompiledDefinition
 */

/** @typedef {{scopeId: string, snapshot: DynamicValue[] | null, node: Node | null,
 *   needsBind: boolean, markup?: string}} CachedRow
 */
/** Framework-owned keyed row snapshots; values inside snapshots are application data.
 * @typedef {{rows: Map<string, CachedRow>, order: CachedRow[], rowRoots: Set<string>,
 *   rowReaders: Array<(scope: DynamicRecord) => DynamicValue>,
 *   byScope?: Map<string, CachedRow>}} RowCache
 */

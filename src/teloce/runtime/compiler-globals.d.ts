/** Helpers prepended by compiler/generator.py and build/builder.py at build time. */
declare function __safeEvaluate(expression: string | undefined, scope: import('./contracts.js').DynamicRecord): import('./contracts.js').DynamicValue;
declare function __runEventExpression(expression: string, scope: import('./contracts.js').DynamicRecord, event?: Event): import('./contracts.js').DynamicValue;
declare function __setSafePath(path: string, value: import('./contracts.js').DynamicValue, scope: import('./contracts.js').DynamicRecord): import('./contracts.js').DynamicValue;
declare function __createReactive(initial: import('./contracts.js').DynamicRecord, notify: (dependency?: string) => void): import('./contracts.js').DynamicRecord;
declare function __patch(target: Node | null, html: string | null, options?: import('./contracts.js').DynamicRecord): void;

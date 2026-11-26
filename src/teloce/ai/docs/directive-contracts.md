# Directive contracts and runtime checks

Teloce remains JavaScript. `npm ci` followed by `npm run typecheck` checks its JSDoc with strict TypeScript without emitting files. Shared contracts live in `src/teloce/runtime/directive-contracts.js`; application values remain dynamic at explicit boundaries. Types catch invalid contracts, while DOM regression tests check lifecycle behavior.

| Directive family | Documented contract |
| --- | --- |
| `@event` / `v-on` | Event filters, listener options, registration and removal |
| `v-model` | Native control values, modifiers, composition and listener cleanup |
| `:attribute` / `v-bind` | Attribute ownership, classes, styles and forwarded attributes |
| `v-show`, `v-hide`, `v-text`, `v-html` | Visibility, text conversion and HTML safety boundary |
| `v-if`, `v-else-if`, `v-else` | Conditional branch ownership |
| `v-for`, virtual lists, `v-memo` | Row scope, keys, cached dependencies and viewport options |
| Scrolly, step and annotation directives | Observer ownership and activation details |
| Poll, live and data-table directives | Timers, adapters, disposal and table options |
| `use:action` and custom `v-name.modifiers` | Mount result, update context and cleanup |
| `data-teloce-link` | SPA navigation URL contract; routing is handled separately |

## Custom directives

```js
/** @type {import('./directive-contracts.js').CustomDirective<number>} */
const counter = {
  mounted(element, context) {
    element.textContent = String(context.value);
    return {
      update(next) { element.textContent = String(next.value); },
      destroy() { /* Release resources owned by this mount. */ },
    };
  },
};
```

`context` includes the directive name, expression, evaluated value, previous value, scoped state and modifiers. Previous values are references, not deep snapshots. Loop expressions read row aliases and live component state. Resource methods retain their returned object's `this` receiver. Cleanup runs when a directive disappears or its host is removed.

The compiled renderer can update a retained directive. The standalone runtime replaces rendered nodes, so it disposes and recreates directives on each render. Standalone and programmatic model helpers support a smaller native-input subset than compiled `v-model`; these contracts do not imply feature parity.

JSDoc does not validate browser data, sanitize arbitrary plugin code, or prove the absence of runtime bugs. Add regression tests when extending a directive or lifecycle contract.

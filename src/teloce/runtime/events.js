/** Component event dispatch helpers. @module */
/** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent} from './contracts.js' */

/** @param {DynamicValue} instance @param {string} name */ export function emit(instance, name, /** @type {DynamicValue[]} */ ...args) {
  const handler = instance?.props?.[`on${name[0]?.toUpperCase()}${name.slice(1)}`];
  if (typeof handler === 'function') return handler(/** @type {DynamicValue[]} */ ...args);
}

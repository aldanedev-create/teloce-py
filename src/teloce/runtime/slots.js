/** Named component slot normalization. @module */
/** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent} from './contracts.js' */

/** @param {DynamicValue} slots @param {DynamicValue} fallback */ export function renderSlot(slots, name = 'default', fallback = []) {
  const slot = slots?.[name];
  return typeof slot === 'function' ? slot() : fallback;
}

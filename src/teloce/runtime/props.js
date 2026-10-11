/** Reactive component property initialization. @module */
/** @import {DynamicValue, DynamicRecord, DynamicCallback, RuntimeElement, RuntimeEvent} from './contracts.js' */
export function defineProps(/** @type {DynamicRecord} */ definition = {}) { return definition; }
/** @param {DynamicRecord} props */ export function validateProps(props, /** @type {DynamicRecord} */ definition = {}) {
  for (const [name, rule] of Object.entries(definition)) {
    if (rule?.required && !(name in props)) throw new Error(`Missing required prop: ${name}`);
  }
  return props;
}

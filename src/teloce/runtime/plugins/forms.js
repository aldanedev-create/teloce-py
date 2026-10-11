/** Optional form state and validation; authorization stays on the server. */
/** @typedef {Record<string, unknown>} Values */
/** @typedef {(value: unknown, values: Values) => string | null | undefined} Validator */
/** @typedef {{errors: Record<string,string>, touched: Record<string,boolean>, submitting:boolean}} FormStatus */
/** @param {Values} initial @param {Record<string,Validator[]>} [rules] */
export function createForm(initial, rules = {}) {
  let values = structuredClone(initial);
  /** @type {FormStatus} */
  const status = {errors: {}, touched: {}, submitting:false};
  /** @type {Set<() => void>} */ const listeners = new Set();
  const notify = () => { for (const listener of listeners) listener(); };
  const known = (/** @type {string} */ field) => {
    if (!Object.hasOwn(initial, field)) throw new Error(`Unknown form field: ${field}`);
  };
  const validate = () => {
    const errors = Object.create(null);
    for (const [field, validators] of Object.entries(rules)) {
      known(field);
      for (const validator of validators) {
        const error = validator(values[field], values);
        if (error) { errors[field] = error; break; }
      }
    }
    status.errors = errors; notify(); return Object.keys(errors).length === 0;
  };
  return {
    get values() { return structuredClone(values); }, status,
    /** @param {string} field @param {unknown} value */
    set(field, value) { known(field); values[field] = value; delete status.errors[field]; notify(); },
    /** @param {string} field */
    touch(field) { known(field); status.touched[field] = true; notify(); },
    validate,
    /** Map Flaxon/FastAPI-style field paths and simple field-error dictionaries. @param {unknown} response */
    setServerErrors(response) {
      const body = /** @type {{errors?:unknown,detail?:unknown}} */ (response || {});
      const source = body.errors ?? body.detail ?? response;
      const errors = Object.create(null);
      if (Array.isArray(source)) {
        for (const item of source) {
          const path = Array.isArray(item.loc) ? item.loc.filter((/** @type {unknown} */ part) => part !== 'body').join('.') : String(item.field || '');
          if (Object.hasOwn(initial,path)) errors[path] = String(item.msg || item.message || 'Invalid value');
          else errors._form = String(item.msg || item.message || 'Invalid value');
        }
      } else if (source && typeof source === 'object') {
        for (const [field,message] of Object.entries(source)) errors[Object.hasOwn(initial,field) ? field : '_form'] = String(message);
      }
      status.errors = errors; notify();
    },
    reset() { if (status.submitting) throw new Error('Cannot reset a submitting form'); values = structuredClone(initial); status.errors = {}; status.touched = {}; notify(); },
    /** Prevent duplicate submissions; validation failures do not call the handler. @template T @param {(values:Values)=>Promise<T>} handler @returns {Promise<T | undefined>} */
    async submit(handler) {
      if (status.submitting) return;
      for (const field of Object.keys(initial)) status.touched[field] = true;
      if (!validate()) return;
      status.submitting = true; notify();
      try { return await handler(structuredClone(values)); }
      finally { status.submitting = false; notify(); }
    },
    /** @param {()=>void} listener */ subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
/** @param {unknown} value */
export const required = value => value == null || String(value).trim() === '' ? 'This field is required' : null;
/** @param {number} length @returns {Validator} */
export const minLength = length => value => String(value ?? '').length < length ? `Use at least ${length} characters` : null;
/** @param {unknown} value */
export const email = value => value === '' || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value)) ? null : 'Enter a valid email';

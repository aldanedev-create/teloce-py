/** @template T @param {() => T} fn @returns {() => T} */
export const onMounted = (fn) => fn;
/** @template T @param {() => T} fn @returns {() => T} */
export const onUnmounted = (fn) => fn;
/** @template T @param {() => T} fn @returns {() => T} */
export const onUpdated = (fn) => fn;

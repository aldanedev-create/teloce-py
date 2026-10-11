/** @typedef {() => unknown} Job */

/** @type {Set<Job>} */
const pending = new Set();
/** @type {Set<Job>} */
const batched = new Set();
let scheduled = false;
let batchDepth = 0;

/** @param {Job} job @returns {void} */
export function queueJob(job) {
  if (batchDepth) {
    batched.add(job);
    return;
  }
  pending.add(job);
  if (!scheduled) {
    scheduled = true;
    queueMicrotask(flushJobs);
  }
}

/** @template T @param {() => T} fn @returns {T} */
export function batch(fn) {
  batchDepth += 1;
  try {
    return fn();
  } finally {
    batchDepth -= 1;
    if (!batchDepth && batched.size) {
      for (const job of batched) pending.add(job);
      batched.clear();
      if (!scheduled) {
        scheduled = true;
        queueMicrotask(flushJobs);
      }
    }
  }
}

/** @returns {void} */
export function flushJobs() {
  scheduled = false;
  const jobs = [...pending];
  pending.clear();
  /** @type {unknown[]} */
  const errors = [];
  for (const job of jobs) {
    try { job(); } catch (error) { errors.push(error); }
  }
  // Report failures after running unrelated work; never discard the rest of
  // the snapshot just because one application effect throws.
  if (errors.length === 1) throw errors[0];
  if (errors.length) {
    const failure = typeof AggregateError === 'function'
      ? new AggregateError(errors, 'Teloce scheduled jobs failed')
      : Object.assign(new Error('Teloce scheduled jobs failed'), { errors });
    throw failure;
  }
}

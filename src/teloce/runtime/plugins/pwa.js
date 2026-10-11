/** Optional PWA registration. Does not cache API responses or provide offline writes. */
/** @typedef {{workerURL?:string,scope?:string,enabled?:boolean}} PwaOptions */
/** @param {PwaOptions} options */
export async function registerPwa(options) {
  if (!('serviceWorker' in navigator) || options.enabled === false) return null;
  const worker = new URL(options.workerURL || './sw.js',import.meta.url);
  if (worker.origin !== location.origin) throw new Error('Service worker must be same-origin');
  const registration = await navigator.serviceWorker.register(worker.href,{scope:options.scope});
  /** @type {Map<ServiceWorker,()=>void>} */ const observers = new Map();
  const notify = () => { if (registration.waiting) document.dispatchEvent(new CustomEvent('teloce:pwa-update', {detail:registration})); };
  const observe = () => {
    const worker = registration.installing;
    if (!worker || observers.has(worker)) return;
    const changed = () => { if (worker.state === 'installed') notify(); };
    observers.set(worker,changed); worker.addEventListener('statechange',changed);
  };
  registration.addEventListener('updatefound',observe); observe(); notify();
  return {
    registration,
    destroy() { registration.removeEventListener('updatefound',observe); for (const [worker,listener] of observers) worker.removeEventListener('statechange',listener); observers.clear(); },
    get updateAvailable() { return Boolean(registration.waiting); },
    async checkForUpdate() { await registration.update(); },
    activateUpdate() { registration.waiting?.postMessage({type:'TELOCE_SKIP_WAITING'}); },
  };
}

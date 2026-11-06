/** Optional PWA registration. Does not cache API responses or provide offline writes. */
/**
 * @typedef {{workerURL?:string,scope?:string,enabled?:boolean,manifest?:boolean,manifestURL?:string,
 *   theme_color?:string}} PwaOptions
 */

/**
 * A browser only offers installation when the page links a manifest. Hosts such as Flaxon add the
 * link themselves; for any other host the plugin adds it (once) next to the other plugin files.
 * @param {PwaOptions} options @param {string} base
 */
function ensureManifest(options, base) {
  if (options.manifest === false) return;
  if (!document.querySelector('link[rel="manifest"]')) {
    const link = document.createElement('link');
    link.rel = 'manifest';
    link.href = new URL(options.manifestURL || './manifest.webmanifest', base).href;
    link.setAttribute('data-teloce-pwa', '');
    document.head.append(link);
  }
  if (options.theme_color && !document.querySelector('meta[name="theme-color"]')) {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.content = options.theme_color;
    meta.setAttribute('data-teloce-pwa', '');
    document.head.append(meta);
  }
}

/** @param {unknown} error @param {URL} worker @param {string | undefined} scope */
function explainRegistrationError(error, worker, scope) {
  const message = error instanceof Error ? error.message : String(error);
  const scopeProblem = /max scope|scope/i.test(message) && /not under|outside|allowed/i.test(message);
  const hint = scopeProblem
    ? ` A service worker can only control the folder it is served from. Serve ${worker.pathname} with the header ` +
      `"Service-Worker-Allowed: ${scope || '/'}" (teloce.plugins.pwa_server does this), serve it from the site root ` +
      `and set plugins.pwa.workerURL, or choose a narrower plugins.pwa.scope.`
    : '';
  const wrapped = new Error(`Teloce PWA: could not register the service worker. ${message}${hint}`);
  /** @type {any} */ (wrapped).cause = error;
  return wrapped;
}

/** @param {PwaOptions} options */
export async function registerPwa(options) {
  if (!('serviceWorker' in navigator) || options.enabled === false) return null;
  const worker = new URL(options.workerURL || './sw.js',import.meta.url);
  if (worker.origin !== location.origin) throw new Error('Service worker must be same-origin');
  ensureManifest(options, import.meta.url);
  /** @type {ServiceWorkerRegistration} */ let registration;
  try {
    registration = await navigator.serviceWorker.register(worker.href,{scope:options.scope});
  } catch (error) {
    throw explainRegistrationError(error, worker, options.scope);
  }
  /** @type {Map<ServiceWorker,()=>void>} */ const observers = new Map();
  // A waiting worker is an *update* only when another worker already controls the page. On the very
  // first install the new worker briefly waits too, and that must not look like an available update.
  const notify = () => { if (registration.waiting && navigator.serviceWorker.controller) document.dispatchEvent(new CustomEvent('teloce:pwa-update', {detail:registration})); };
  const observe = () => {
    const worker = registration.installing;
    if (!worker || observers.has(worker)) return;
    const changed = () => {
      if (worker.state === 'installed') notify();
      // A worker that never installs (for example a precached file returned 404) becomes redundant.
      else if (worker.state === 'redundant' && !registration.active && !registration.waiting) {
        document.dispatchEvent(new CustomEvent('teloce:pwa-error', {detail:new Error(
          'Teloce PWA: the service worker failed to install. A precached file probably could not be fetched; ' +
          'check that the build is served at the "public_path" it was built with.')}));
      }
    };
    observers.set(worker,changed); worker.addEventListener('statechange',changed);
  };
  registration.addEventListener('updatefound',observe); observe(); notify();
  return {
    registration,
    destroy() { registration.removeEventListener('updatefound',observe); for (const [worker,listener] of observers) worker.removeEventListener('statechange',listener); observers.clear(); },
    get updateAvailable() { return Boolean(registration.waiting && navigator.serviceWorker.controller); },
    async checkForUpdate() { await registration.update(); },
    activateUpdate() { registration.waiting?.postMessage({type:'TELOCE_SKIP_WAITING'}); },
  };
}

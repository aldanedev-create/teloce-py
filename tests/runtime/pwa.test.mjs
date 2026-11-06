// Unit tests for src/teloce/runtime/plugins/pwa.js with a fake browser environment.
import test from 'node:test';
import assert from 'node:assert/strict';
import { registerPwa } from '../../src/teloce/runtime/plugins/pwa.js';

const ORIGIN = 'https://app.test';
const OPTS = { workerURL: `${ORIGIN}/static/teloce-plugins/sw.js`, manifestURL: `${ORIGIN}/static/teloce-plugins/manifest.webmanifest`, scope: '/' };

class FakeWorker extends EventTarget { constructor(state = 'installing') { super(); this.state = state; this.messages = []; } postMessage(m) { this.messages.push(m); } set(state) { this.state = state; this.dispatchEvent(new Event('statechange')); } }
class FakeRegistration extends EventTarget { constructor() { super(); this.installing = null; this.waiting = null; this.active = null; this.updates = 0; } async update() { this.updates += 1; } }

function env({ controller = null, register, supported = true } = {}) {
  const registration = new FakeRegistration();
  const events = [];
  const head = { children: [], append(node) { this.children.push(node); } };
  const matches = selector => head.children.find(node => (selector === 'link[rel="manifest"]' && node.rel === 'manifest') || (selector === 'meta[name="theme-color"]' && node.name === 'theme-color'));
  const doc = {
    head, querySelector: selector => matches(selector) || null,
    createElement: tag => ({ tag, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } }),
    dispatchEvent: event => { events.push([event.type, event.detail]); return true; },
  };
  const registrations = [];
  const sw = { controller, register: register || (async (url, opts) => { registrations.push([url, opts]); return registration; }) };
  Object.defineProperty(globalThis, 'document', { value: doc, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'location', { value: { origin: ORIGIN }, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'navigator', { value: supported ? { serviceWorker: sw } : {}, configurable: true, writable: true });
  return { registration, events, head, sw, registrations };
}
test.afterEach(() => { for (const key of ['document', 'location', 'navigator']) delete globalThis[key]; });

test('pwa: does nothing when unsupported or disabled', async () => {
  env({ supported: false });
  assert.equal(await registerPwa({ ...OPTS }), null);
  const e = env();
  assert.equal(await registerPwa({ ...OPTS, enabled: false }), null);
  assert.equal(e.head.children.length, 0);
  assert.equal(e.registrations.length, 0);
});

test('pwa: links the manifest and theme color once, then registers with the scope', async () => {
  const e = env();
  await registerPwa({ ...OPTS, theme_color: '#0f172a' });
  const link = e.head.children.find(n => n.rel === 'manifest');
  assert.equal(link.href, OPTS.manifestURL);
  assert.equal(e.head.children.find(n => n.name === 'theme-color').content, '#0f172a');
  assert.deepEqual(e.registrations, [[OPTS.workerURL, { scope: '/' }]]);
  await registerPwa({ ...OPTS, theme_color: '#0f172a' });           // second call: nothing duplicated
  assert.equal(e.head.children.length, 2);
});

test('pwa: respects an existing manifest link and manifest:false', async () => {
  const e = env();
  e.head.append({ rel: 'manifest', href: '/server-added.webmanifest' });
  await registerPwa({ ...OPTS, theme_color: '#fff' });
  assert.equal(e.head.children.filter(n => n.rel === 'manifest').length, 1);
  const f = env();
  await registerPwa({ ...OPTS, manifest: false });
  assert.equal(f.head.children.length, 0);
});

test('pwa: manifest URL defaults to the file next to the plugin module', async () => {
  const e = env();
  await registerPwa({ workerURL: OPTS.workerURL });
  const href = e.head.children.find(n => n.rel === 'manifest').href;
  assert.ok(href.endsWith('/plugins/manifest.webmanifest'), href);
});

test('pwa: rejects a cross-origin worker before touching the page', async () => {
  const e = env();
  await assert.rejects(registerPwa({ workerURL: 'https://evil.test/sw.js' }), /same-origin/);
  assert.equal(e.head.children.length, 0);
});

test('pwa: scope errors become an actionable message and keep the cause', async () => {
  const original = new Error("The path of the provided scope ('/') is not under the max scope allowed ('/static/teloce-plugins/').");
  env({ register: async () => { throw original; } });
  await assert.rejects(registerPwa({ ...OPTS }), error => {
    assert.match(error.message, /Service-Worker-Allowed: \//);
    assert.match(error.message, /pwa_server/);
    assert.equal(error.cause, original);
    return true;
  });
  env({ register: async () => { throw new Error('boom'); } });
  await assert.rejects(registerPwa({ ...OPTS }), error => /boom/.test(error.message) && !/Service-Worker-Allowed/.test(error.message));
});

test('pwa: the first install is not announced as an update', async () => {
  const e = env({ controller: null });
  e.registration.installing = new FakeWorker();
  const pwa = await registerPwa({ ...OPTS });
  const worker = e.registration.installing;
  e.registration.installing = null; e.registration.waiting = worker;
  worker.set('installed');
  assert.deepEqual(e.events, []);
  assert.equal(pwa.updateAvailable, false);
});

test('pwa: a waiting worker behind an active controller is an update, activated explicitly', async () => {
  const e = env({ controller: {} });
  const pwa = await registerPwa({ ...OPTS });
  assert.equal(pwa.updateAvailable, false);
  const worker = new FakeWorker();
  e.registration.installing = worker;
  e.registration.dispatchEvent(new Event('updatefound'));
  e.registration.installing = null; e.registration.waiting = worker;
  worker.set('installed');
  assert.deepEqual(e.events.map(x => x[0]), ['teloce:pwa-update']);
  assert.equal(pwa.updateAvailable, true);
  assert.deepEqual(worker.messages, []);                 // nothing happens automatically
  pwa.activateUpdate();
  assert.deepEqual(worker.messages, [{ type: 'TELOCE_SKIP_WAITING' }]);
  await pwa.checkForUpdate();
  assert.equal(e.registration.updates, 1);
});

test('pwa: an update already waiting at startup is announced', async () => {
  const e = env({ controller: {} });
  e.registration.waiting = new FakeWorker('installed');
  await registerPwa({ ...OPTS });
  assert.deepEqual(e.events.map(x => x[0]), ['teloce:pwa-update']);
});

test('pwa: a worker that never installs reports a clear error', async () => {
  const e = env({ controller: null });
  const worker = new FakeWorker();
  e.registration.installing = worker;
  await registerPwa({ ...OPTS });
  worker.set('redundant');
  const [type, detail] = e.events[0];
  assert.equal(type, 'teloce:pwa-error');
  assert.match(detail.message, /failed to install/);
  assert.match(detail.message, /public_path/);
});

test('pwa: a redundant worker that replaced an active one is not an install failure', async () => {
  const e = env({ controller: {} });
  e.registration.active = new FakeWorker('activated');
  const worker = new FakeWorker();
  e.registration.installing = worker;
  await registerPwa({ ...OPTS });
  worker.set('redundant');
  assert.deepEqual(e.events, []);
});

test('pwa: destroy stops observing', async () => {
  const e = env({ controller: {} });
  const worker = new FakeWorker();
  e.registration.installing = worker;
  const pwa = await registerPwa({ ...OPTS });
  pwa.destroy();
  e.registration.installing = null; e.registration.waiting = worker;
  worker.set('installed');
  assert.deepEqual(e.events, []);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../public/guard-sw.js', import.meta.url), 'utf8');

function worker(windows = []) {
  const handlers = {};
  const notifications = [];
  const opened = [];
  const self = {
    location: { origin: 'https://nivra.example' },
    addEventListener: (name, handler) => { handlers[name] = handler; },
    skipWaiting: async () => {},
    clients: {
      claim: async () => {},
      matchAll: async () => windows,
      openWindow: async (url) => opened.push(url),
    },
    registration: { showNotification: async (title, options) => notifications.push({ title, options }) },
  };
  vm.runInNewContext(source, { self, URL });
  async function dispatch(name, fields = {}) {
    const promises = [];
    handlers[name]({ ...fields, waitUntil: (promise) => promises.push(promise) });
    await Promise.all(promises);
  }
  return { handlers, notifications, opened, dispatch };
}

test('push requests the exact notification behavior; API caching is absent', async () => {
  const sw = worker();
  assert.equal(sw.handlers.fetch, undefined);
  const payload = { type: 'alert', eventId: 'event-1', title: 'NIVRA alert', body: 'Go to Entrance', url: '/guard' };
  await sw.dispatch('push', { data: { json: () => payload } });
  assert.deepEqual(JSON.parse(JSON.stringify(sw.notifications)), [{
    title: 'NIVRA alert', options: {
      body: 'Go to Entrance', tag: 'event-1', renotify: true, requireInteraction: true,
      vibrate: [800, 400, 800, 400, 800], data: { url: '/guard' },
    },
  }]);
});

test('click focuses the existing guard window and never opens an arbitrary push URL', async () => {
  let focused = false;
  let closed = false;
  const sw = worker([{ url: 'https://nivra.example/guard', focus: async () => { focused = true; } }]);
  await sw.dispatch('notificationclick', { notification: {
    data: { url: 'https://evil.example' }, close: () => { closed = true; },
  } });
  assert.equal(closed, true);
  assert.equal(focused, true);
  assert.deepEqual(sw.opened, []);
});

test('click opens guard when only unrelated windows exist', async () => {
  const sw = worker([{ url: 'https://nivra.example/wall', focus: () => assert.fail('wrong window') }]);
  await sw.dispatch('notificationclick', { notification: { close() {} } });
  assert.deepEqual(sw.opened, ['/guard']);
});

test('malformed or unrelated pushes do not notify', async () => {
  const sw = worker();
  await sw.dispatch('push');
  await sw.dispatch('push', { data: { json() { throw new Error('invalid JSON'); } } });
  await sw.dispatch('push', { data: { json: () => ({ type: 'other' }) } });
  await sw.dispatch('push', { data: { json: () => null } });
  assert.deepEqual(sw.notifications, []);
});

test('manifest and icon sizes match the install contract', () => {
  const manifest = JSON.parse(readFileSync(new URL('../public/guard.webmanifest', import.meta.url), 'utf8'));
  assert.equal(manifest.name, 'NIVRA Guard');
  assert.equal(manifest.start_url, '/guard');
  assert.equal(manifest.display, 'standalone');
  assert.equal(manifest.theme_color, '#0b0b0c');
  assert.equal(manifest.background_color, '#0b0b0c');
  for (const size of [192, 512]) {
    const icon = manifest.icons.find((entry) => entry.sizes === `${size}x${size}`);
    assert.ok(icon.purpose.includes('maskable'));
    const png = readFileSync(new URL(`../public${icon.src}`, import.meta.url));
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
  }
});

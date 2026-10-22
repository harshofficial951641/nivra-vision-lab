/* Notifications only: deliberately no fetch handler or API caching. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data;
  try { data = event.data.json(); } catch { return; }
  if (!data || data.type !== 'alert' || typeof data.eventId !== 'string') return;
  event.waitUntil(self.registration.showNotification(
    typeof data.title === 'string' ? data.title : 'NIVRA alert',
    {
      body: typeof data.body === 'string' ? data.body : 'Open NIVRA Guard.',
      tag: data.eventId,
      renotify: true,
      requireInteraction: true,
      vibrate: [800, 400, 800, 400, 800],
      data: { url: '/guard' },
    },
  ));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      const url = new URL(client.url);
      if (url.origin === self.location.origin && url.pathname === '/guard') {
        await client.focus();
        return;
      }
    }
    await self.clients.openWindow('/guard');
  })());
});

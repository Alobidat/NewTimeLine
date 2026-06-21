// Kill-switch service worker.
//
// Earlier builds registered Flutter's caching service worker, which then kept serving a stale
// main.dart.js even across hard refreshes. We now build with --pwa-strategy=none (new visitors
// never register a SW), and ship THIS file at the same URL so any browser that still has the
// old SW registered updates to this one on its next visit — and this one wipes all caches,
// unregisters itself, and reloads the page so the client lands on the fresh, uncached bundle.
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (_) {}
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) {
      try { client.navigate(client.url); } catch (_) {}
    }
  })());
});

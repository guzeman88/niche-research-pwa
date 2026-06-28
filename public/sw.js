/* global self, caches, URL, fetch */

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.map((key) => caches.delete(key)))
    await self.clients.claim()

    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    await Promise.all(clients.map(async (client) => {
      const url = new URL(client.url)
      if (url.searchParams.get('v') === '16' && url.searchParams.get('reset') === '1') return
      await client.navigate('/?v=16&reset=1')
    }))

    await self.registration.unregister()
  })())
})

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request))
})

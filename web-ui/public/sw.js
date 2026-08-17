const CACHE_VERSION = 'v2'
const CACHE_NAME = `landsense-web-ui-${CACHE_VERSION}`

const APP_SHELL = ['/', '/manifest.json']

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME)
      await cache.addAll(APP_SHELL)
      await self.skipWaiting()
    })()
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((k) => k.startsWith('landsense-web-ui-') && k !== CACHE_NAME).map((k) => caches.delete(k)))
      await self.clients.claim()
    })()
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  const url = new URL(req.url)

  if (url.origin !== self.location.origin) return

  // Never cache authenticated API responses. In particular, /alerts/my is
  // scoped by the bearer token even though every citizen uses the same URL.
  if (url.pathname.startsWith('/alerts/') || req.headers.has('Authorization')) {
    event.respondWith(fetch(req))
    return
  }

  if (req.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(req)
          return fresh
        } catch {
          const cache = await caches.open(CACHE_NAME)
          return (await cache.match('/')) || Response.error()
        }
      })()
    )
    return
  }

  event.respondWith(
    (async () => {
      try {
        const fresh = await fetch(req)
        const cache = await caches.open(CACHE_NAME)
        if (req.method === 'GET') cache.put(req, fresh.clone())
        return fresh
      } catch {
        const cache = await caches.open(CACHE_NAME)
        return (await cache.match(req)) || Response.error()
      }
    })()
  )
})

function riskToBody(risk) {
  const r = String(risk || '').toUpperCase()
  if (r.includes('HIGH')) return 'High risk in your area. Evacuate immediately.'
  if (r.includes('WARN')) return 'Risk is rising. Stay alert and be ready to move.'
  if (r.includes('SAFE')) return 'Current status looks safe.'
  return 'Please check your safety status.'
}

self.addEventListener('push', (event) => {
  event.waitUntil(
    (async () => {
      let title = 'Landslide Alert'
      let body = 'Please check your safety status.'
      let data = { url: '/' }

      try {
        const text = event.data ? event.data.text() : ''
        if (text) {
          try {
            const parsed = JSON.parse(text)
            const risk = parsed.risk || parsed.risk_level || parsed.level
            title = parsed.title || title
            body = parsed.body || riskToBody(risk)
            data = { ...data, ...parsed, risk }
          } catch {
            body = text
          }
        }
      } catch {
        // Ignore malformed push payloads.
      }

      await self.registration.showNotification(title, {
        body,
        tag: 'landsense-push',
        renotify: true,
        data
      })
    })()
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = (event.notification.data && event.notification.data.url) || '/'

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const client of allClients) {
        if ('focus' in client) {
          await client.focus()
          if ('navigate' in client) {
            await client.navigate(targetUrl)
          }
          return
        }
      }
      if (self.clients.openWindow) {
        await self.clients.openWindow(targetUrl)
      }
    })()
  )
})

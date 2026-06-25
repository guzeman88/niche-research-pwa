const APP_CACHE_VERSION = 'etsy-niches-v14'
const VERSION_KEY = 'etsy-niches-app-version'
const LEGACY_PATHS = new Set(['/explore', '/scheduler', '/settings'])

async function clearStaleAppCaches() {
  if (!('caches' in window)) return
  const keys = await caches.keys()
  await Promise.all(keys.map((key) => caches.delete(key)))
}

function isLegacyPath(pathname: string) {
  return LEGACY_PATHS.has(pathname) || pathname.startsWith('/reports')
}

export function registerPwaUpdates() {
  if (!('serviceWorker' in navigator)) return

  if (isLegacyPath(window.location.pathname)) {
    window.location.replace('/?v=14&legacy=1')
    return
  }

  navigator.serviceWorker.addEventListener('message', (event) => {
    if (event.data?.type === 'APP_CACHE_RESET') {
      window.location.replace('/?v=14&reset=1')
    }
  })

  const previousVersion = window.localStorage.getItem(VERSION_KEY)
  const shouldReset = previousVersion !== APP_CACHE_VERSION
  window.localStorage.setItem(VERSION_KEY, APP_CACHE_VERSION)

  navigator.serviceWorker.getRegistrations()
    .then((registrations) => {
      if (!shouldReset && registrations.length === 0) return Promise.resolve()
      return clearStaleAppCaches()
        .then(() => navigator.serviceWorker.register('/sw.js?v=14', { scope: '/' }))
        .then((registration) => registration.update())
    })
    .catch(() => {})
}

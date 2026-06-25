import { registerSW } from 'virtual:pwa-register'

const APP_CACHE_VERSION = 'etsy-niches-v13'
const VERSION_KEY = 'etsy-niches-app-version'

async function clearStaleAppCaches() {
  if (!('caches' in window)) return
  const keys = await caches.keys()
  await Promise.all(
    keys
      .filter((key) => key.includes('etsy-niches') && !key.includes(APP_CACHE_VERSION))
      .map((key) => caches.delete(key)),
  )
}

export function registerPwaUpdates() {
  if (!('serviceWorker' in navigator)) return

  const updateSW = registerSW({
    immediate: true,
    onRegisteredSW: (_url, registration) => {
      registration?.update().catch(() => {
        // Update checks are opportunistic; the app can still run from network/static data.
      })
    },
    onRegisterError: () => {
      // Registration errors should not block the research UI.
    },
  })

  const previousVersion = window.localStorage.getItem(VERSION_KEY)
  if (previousVersion === APP_CACHE_VERSION) return

  window.localStorage.setItem(VERSION_KEY, APP_CACHE_VERSION)
  clearStaleAppCaches()
    .then(() => updateSW(true))
    .catch(() => {})
}

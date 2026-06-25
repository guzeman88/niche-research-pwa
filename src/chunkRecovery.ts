const ASSET_REFRESH_VERSION = 'etsy-niches-assets-v15'
const ASSET_REFRESH_KEY = 'etsy-niches-asset-refresh-version'

const CHUNK_ERROR_PATTERNS = [
  'Importing a module script failed',
  'Failed to fetch dynamically imported module',
  'Unable to preload CSS',
  'error loading dynamically imported module',
]

export function isChunkLoadError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || '')
  return CHUNK_ERROR_PATTERNS.some((pattern) => message.includes(pattern))
}

async function clearBrowserAppState() {
  if ('caches' in window) {
    const keys = await caches.keys()
    await Promise.all(keys.map((key) => caches.delete(key)))
  }

  if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations()
    await Promise.all(registrations.map((registration) => registration.unregister()))
  }
}

export function refreshForCurrentAssets(error: unknown) {
  if (!isChunkLoadError(error)) return false
  if (window.sessionStorage.getItem(ASSET_REFRESH_KEY) === ASSET_REFRESH_VERSION) return false

  window.sessionStorage.setItem(ASSET_REFRESH_KEY, ASSET_REFRESH_VERSION)
  clearBrowserAppState()
    .finally(() => {
      window.location.replace(`/?v=15&asset_refresh=${Date.now()}`)
    })

  return true
}

export function installChunkRecovery() {
  window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    refreshForCurrentAssets((event as unknown as { payload?: unknown }).payload)
  })

  window.addEventListener('error', (event) => {
    refreshForCurrentAssets(event.error || event.message)
  })

  window.addEventListener('unhandledrejection', (event) => {
    if (refreshForCurrentAssets(event.reason)) {
      event.preventDefault()
    }
  })
}

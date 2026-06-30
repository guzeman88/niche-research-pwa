import { useEffect } from 'react'
import { ensureScannerRunning, hasConfiguredBackend } from '../lib/api'

const HEARTBEAT_MS = 60_000
const PUBLIC_PATH_PREFIXES = ['/auth/', '/api-application']

export default function useScannerHeartbeat(enabled = true) {
  useEffect(() => {
    if (!enabled) return
    if (PUBLIC_PATH_PREFIXES.some((path) => window.location.pathname.startsWith(path))) return
    if (!hasConfiguredBackend()) return

    let cancelled = false

    const ensureRunning = () => {
      if (cancelled) return
      ensureScannerRunning().catch(() => {
        // The PWA can run from static snapshots; scanner startup is best-effort when a backend exists.
      })
    }

    ensureRunning()
    const interval = window.setInterval(ensureRunning, HEARTBEAT_MS)
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') ensureRunning()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      cancelled = true
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [enabled])
}

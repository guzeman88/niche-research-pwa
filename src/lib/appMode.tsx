import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type AppMode = 'developer' | 'user'

const APP_MODE_KEY = 'niche-research-pwa:app-mode:v1'
export const USER_DATA_EVENT = 'niche-research-pwa:user-data-updated'

interface AppModeContextValue {
  mode: AppMode
  isUserMode: boolean
  userDataVersion: number
  setMode: (mode: AppMode) => void
  refreshUserData: () => void
}

const AppModeContext = createContext<AppModeContextValue | null>(null)

export function readStoredAppMode(): AppMode {
  if (typeof window === 'undefined' || !window.localStorage) return 'developer'
  return window.localStorage.getItem(APP_MODE_KEY) === 'user' ? 'user' : 'developer'
}

export function AppModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<AppMode>(() => readStoredAppMode())
  const [userDataVersion, setUserDataVersion] = useState(0)

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === APP_MODE_KEY) {
        setModeState(event.newValue === 'user' ? 'user' : 'developer')
      }
    }
    const handleUserData = () => setUserDataVersion((value) => value + 1)
    window.addEventListener('storage', handleStorage)
    window.addEventListener(USER_DATA_EVENT, handleUserData)
    return () => {
      window.removeEventListener('storage', handleStorage)
      window.removeEventListener(USER_DATA_EVENT, handleUserData)
    }
  }, [])

  const value = useMemo<AppModeContextValue>(() => ({
    mode,
    isUserMode: mode === 'user',
    userDataVersion,
    setMode(nextMode) {
      setModeState(nextMode)
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(APP_MODE_KEY, nextMode)
      }
    },
    refreshUserData() {
      setUserDataVersion((current) => current + 1)
    },
  }), [mode, userDataVersion])

  return <AppModeContext.Provider value={value}>{children}</AppModeContext.Provider>
}

export function useAppMode() {
  const context = useContext(AppModeContext)
  if (!context) throw new Error('useAppMode must be used inside AppModeProvider')
  return context
}

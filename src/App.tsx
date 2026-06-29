import { Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import useScannerHeartbeat from './hooks/useScannerHeartbeat'
import { AppModeProvider, useAppMode } from './lib/appMode'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Keywords = lazy(() => import('./pages/Keywords'))
const StoreGenerator = lazy(() => import('./pages/StoreGenerator'))
const Stores = lazy(() => import('./pages/Stores'))
const EtsyAuth = lazy(() => import('./pages/EtsyAuth'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageFallback() {
  return (
    <div className="page">
      <div className="panel p-4">
        <div className="h-4 w-28 rounded bg-surface-700/80" />
        <div className="mt-4 h-20 rounded bg-surface-800/80" />
      </div>
    </div>
  )
}

function page(element: ReactNode) {
  return <Suspense fallback={<PageFallback />}>{element}</Suspense>
}

export default function App() {
  return (
    <AppModeProvider>
      <AppRoutes />
    </AppModeProvider>
  )
}

function AppRoutes() {
  const { mode } = useAppMode()
  useScannerHeartbeat(mode === 'developer')

  return (
    <Routes>
      <Route path="/auth/etsy" element={page(<EtsyAuth />)} />
      <Route element={<Layout />}>
        <Route index element={page(<Dashboard />)} />
        <Route path="/keywords" element={page(<Keywords />)} />
        <Route path="/store-generator" element={page(<StoreGenerator />)} />
        <Route path="/stores" element={page(<Stores />)} />
        <Route path="*" element={page(<NotFound />)} />
      </Route>
    </Routes>
  )
}

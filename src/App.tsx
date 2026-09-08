import { Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import BrandLogo from './components/BrandLogo'
import useScannerHeartbeat from './hooks/useScannerHeartbeat'
import { AppModeProvider, useAppMode } from './lib/appMode'
import {RequireAccount, useAuth} from './lib/auth'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Keywords = lazy(() => import('./pages/Keywords'))
const StoreGenerator = lazy(() => import('./pages/StoreGenerator'))
const Workspace = lazy(() => import('./pages/Workspace'))
const Account = lazy(() => import('./pages/Account'))
const SignIn = lazy(() => import('./pages/SignIn'))
const ConfirmAccount = lazy(() => import('./pages/ConfirmAccount'))
const Stores = lazy(() => import('./pages/Stores'))
const EtsyAuth = lazy(() => import('./pages/EtsyAuth'))
const ApiApplicationLanding = lazy(() => import('./pages/ApiApplicationLanding'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageFallback() {
  return (
    <div className="page">
      <div className="panel p-4">
        <BrandLogo className="mb-4" markClassName="h-7 w-7" wordmarkClassName="text-[14px] font-extrabold leading-none tracking-tight" />
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
  const auth = useAuth()
  useScannerHeartbeat(mode === 'developer' && auth.profile?.role === 'admin')

  return (
    <Routes>
      <Route path="/signin" element={page(<SignIn />)} />
      <Route path="/auth/confirm" element={page(<ConfirmAccount />)} />
      <Route path="/api-application" element={page(<ApiApplicationLanding />)} />
      <Route path="/auth/etsy" element={page(<EtsyAuth />)} />
      <Route element={<RequireAccount><Layout /></RequireAccount>}>
        <Route index element={page(<Dashboard />)} />
        <Route path="/keywords" element={page(<Keywords />)} />
        <Route path="/store-generator" element={page(<StoreGenerator />)} />
        <Route path="/workspace" element={page(<Workspace />)} />
        <Route path="/account" element={page(<Account />)} />
        <Route path="/stores" element={page(<Stores />)} />
        <Route path="*" element={page(<NotFound />)} />
      </Route>
    </Routes>
  )
}

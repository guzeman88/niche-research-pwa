import { Suspense, lazy } from 'react'
import type { ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import BrandLogo from './components/BrandLogo'
import { AppModeProvider } from './lib/appMode'
import {RequireAccount, useAuth} from './lib/auth'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Keywords = lazy(() => import('./pages/Keywords'))
const StoreGenerator = lazy(() => import('./pages/StoreGenerator'))
const LaunchLab = lazy(() => import('./pages/LaunchLab'))
const Workspace = lazy(() => import('./pages/Workspace'))
const EvidenceOperations = lazy(() => import('./pages/EvidenceOperations'))
const ProductValidation = lazy(() => import('./pages/ProductValidation'))
const SellingProducts = lazy(() => import('./pages/SellingProducts'))
const Production = lazy(() => import('./pages/Production'))
const Account = lazy(() => import('./pages/Account'))
const SignIn = lazy(() => import('./pages/SignIn'))
const ConfirmAccount = lazy(() => import('./pages/ConfirmAccount'))
const Stores = lazy(() => import('./pages/Stores'))
const EtsyAuth = lazy(() => import('./pages/EtsyAuth'))
const ApiApplicationLanding = lazy(() => import('./pages/ApiApplicationLanding'))
const Privacy = lazy(() => import('./pages/Privacy'))
const Terms = lazy(() => import('./pages/Terms'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageFallback() {
  return (
    <div className="page">
      <div className="panel p-4">
        <BrandLogo className="mb-4" markClassName="h-7 w-7" wordmarkClassName="text-[14px] font-extrabold leading-none tracking-tight" />
        <div className="h-4 w-28 rounded-sm bg-surface-700/80" />
        <div className="mt-4 h-20 rounded-sm bg-surface-800/80" />
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
  return (
    <Routes>
      <Route path="/signin" element={page(<SignIn />)} />
      <Route path="/auth/confirm" element={page(<ConfirmAccount />)} />
      <Route path="/api-application" element={page(<ApiApplicationLanding />)} />
      <Route path="/privacy" element={page(<Privacy />)} />
      <Route path="/terms" element={page(<Terms />)} />
      <Route path="/auth/etsy" element={page(<EtsyAuth />)} />
      <Route path="/validation" element={<OperatorPage>{page(<ProductValidation />)}</OperatorPage>} />
      <Route path="/selling" element={<OperatorPage>{page(<SellingProducts />)}</OperatorPage>} />
      <Route path="/production" element={<OperatorPage>{page(<Production />)}</OperatorPage>} />
      <Route element={<RequireAccount><Layout /></RequireAccount>}>
        <Route index element={page(<Dashboard />)} />
        <Route path="/keywords" element={page(<Keywords />)} />
        <Route path="/store-generator" element={page(<StoreGenerator />)} />
        <Route path="/launch" element={<Administrator>{page(<LaunchLab />)}</Administrator>} />
        <Route path="/workspace" element={page(<Workspace />)} />
        <Route path="/evidence" element={<Administrator>{page(<EvidenceOperations />)}</Administrator>} />
        <Route path="/account" element={page(<Account />)} />
        <Route path="/stores" element={page(<Stores />)} />
        <Route path="*" element={page(<NotFound />)} />
      </Route>
    </Routes>
  )
}

function OperatorPage({children}:{children:ReactNode}){
  const standalone=['localhost','127.0.0.1','[::1]'].includes(location.hostname)
  if(standalone)return children
  return <RequireAccount><Administrator><Layout content={children}/></Administrator></RequireAccount>
}
function Administrator({children}:{children:ReactNode}){
  const auth=useAuth()
  return auth.profile?.role==='admin'?children:<Navigate to="/" replace/>
}

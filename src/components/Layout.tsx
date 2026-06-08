import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import { warmUpBackend } from '../lib/api'

export default function Layout() {
  const [warming, setWarming] = useState(true)

  useEffect(() => {
    warmUpBackend().then(() => setWarming(false))
  }, [])

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Warm-up banner */}
      {warming && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-primary-600/90 backdrop-blur text-white text-xs text-center py-1.5 animate-pulse">
          Waking up backend... data will appear momentarily
        </div>
      )}
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 flex-shrink-0 border-r border-surface-700 bg-surface-900">
        <Sidebar />
      </aside>
      {/* Main content */}
      <main className={`flex-1 overflow-y-auto pb-16 lg:pb-0 ${warming ? 'pt-6' : ''}`}>
        <Outlet />
      </main>
      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-surface-700 bg-surface-900">
        <Sidebar mobile />
      </nav>
    </div>
  )
}

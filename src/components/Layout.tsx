import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 flex-shrink-0 border-r border-surface-700 bg-surface-900">
        <Sidebar />
      </aside>
      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-16 lg:pb-0">
        <Outlet />
      </main>
      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-surface-700 bg-surface-900">
        <Sidebar mobile />
      </nav>
    </div>
  )
}

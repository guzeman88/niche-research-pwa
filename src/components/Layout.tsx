import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface-950 text-surface-50">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 flex-shrink-0 border-r nav-surface">
        <Sidebar />
      </aside>
      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-24 lg:pb-0">
        <Outlet />
      </main>
      {/* Mobile bottom nav */}
      <nav
        aria-label="Primary"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] lg:hidden"
      >
        <div className="pointer-events-auto w-full max-w-[25rem] rounded-lg border mobile-nav-surface">
          <Sidebar mobile />
        </div>
      </nav>
    </div>
  )
}

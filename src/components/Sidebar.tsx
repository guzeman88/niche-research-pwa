import { NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/explore', label: 'Explore', icon: '🔍' },
  { to: '/keywords', label: 'Keywords', icon: '🔑' },
  { to: '/scheduler', label: 'Scheduler', icon: '⚙️' },
  { to: '/settings', label: 'Settings', icon: '🔧' },
]

export default function Sidebar({ mobile = false }: { mobile?: boolean }) {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
  })

  const dbOk = health?.integrity === 'ok'

  if (mobile) {
    return (
      <div className="flex items-center justify-around py-2 px-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-xs transition-colors ${
                isActive ? 'text-primary-400 bg-primary-500/10' : 'text-slate-400 hover:text-slate-200'
              }`
            }
          >
            <span className="text-lg">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-4">
      {/* Logo */}
      <div className="mb-6">
        <h1 className="text-lg font-bold text-white flex items-center gap-2">
          <span className="text-2xl">🔍</span>
          Niche Research
        </h1>
        <p className="text-xs text-slate-500 mt-1">Etsy intelligence tool</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'text-white bg-primary-600/20 border border-primary-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-surface-800'
              }`
            }
          >
            <span>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Status */}
      <div className="pt-4 border-t border-surface-700">
        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${dbOk ? 'bg-emerald-400' : 'bg-red-400'}`} />
          <span className="text-slate-500">
            {dbOk ? 'Backend connected' : 'Backend offline'}
          </span>
        </div>
      </div>
    </div>
  )
}

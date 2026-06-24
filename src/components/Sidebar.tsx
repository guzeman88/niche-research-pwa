import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'
import Icon from './Icon'
import type { IconName } from './Icon'

const NAV_ITEMS: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'Dashboard', icon: 'home' },
  { to: '/explore', label: 'Explore', icon: 'compass' },
  { to: '/keywords', label: 'Keywords', icon: 'search' },
  { to: '/store-generator', label: 'Store Gen', icon: 'layers' },
  { to: '/stores', label: 'My Stores', icon: 'package' },
  { to: '/scheduler', label: 'Scheduler', icon: 'activity' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
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
      <div className="flex items-center gap-1 overflow-x-auto px-2">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex min-w-[4.25rem] flex-col items-center gap-0.5 px-2 py-1.5 rounded-xl text-[10px] font-semibold transition-all duration-150 ${
                isActive
                  ? 'text-primary-200'
                  : 'text-surface-300 hover:text-surface-100'
              }`
            }
          >
            <Icon name={icon} size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-5">
      <div className="mb-8">
        <h1 className="text-lg font-extrabold text-surface-50 tracking-tight flex items-center gap-2">
          <Icon name="search" size={22} className="text-primary-200" />
          Niche Research
        </h1>
        <p className="text-[11px] text-surface-300 mt-1 font-medium">Etsy intelligence</p>
      </div>

      <nav className="flex-1 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150 ${
                isActive
                  ? 'text-white bg-primary-400/15 border border-primary-400/20'
                  : 'text-surface-200 hover:text-surface-50 hover:bg-surface-700'
              }`
            }
          >
            <Icon name={icon} size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="pt-4 border-t border-surface-500/50">
        <div className="flex items-center gap-2 text-[11px]">
          <span className={`w-2 h-2 rounded-full ${dbOk ? 'bg-emerald-400 shadow-[0_0_6px_#a3be8c]' : 'bg-red-400'}`} />
          <span className="text-surface-300 font-medium">
            {dbOk ? 'Backend connected' : 'Offline'}
          </span>
        </div>
      </div>
    </div>
  )
}

import { NavLink } from 'react-router-dom'
import Icon from './Icon'
import type { IconName } from './Icon'

const NAV_ITEMS: { to: string; label: string; shortLabel?: string; icon: IconName }[] = [
  { to: '/', label: 'Dashboard', icon: 'home' },
  { to: '/keywords', label: 'Keywords', icon: 'search' },
  { to: '/store-generator', label: 'Store Generator', shortLabel: 'Generator', icon: 'layers' },
  { to: '/stores', label: 'My Stores', icon: 'package' },
]

export default function Sidebar({ mobile = false }: { mobile?: boolean }) {
  const fastDataReady = !import.meta.env.DEV && import.meta.env.VITE_ALLOW_STATIC_DATA !== '0'
  const statusOk = fastDataReady || import.meta.env.DEV

  if (mobile) {
    return (
      <div className="grid grid-cols-4 gap-1 p-1.5">
        {NAV_ITEMS.map(({ to, label, shortLabel, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `group relative flex min-w-0 flex-col items-center justify-center gap-1 rounded-lg px-1.5 py-2 text-[10px] font-semibold leading-none transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary-400/45 ${
                isActive
                  ? 'bg-surface-700/80 text-surface-50 shadow-[0_10px_22px_rgba(7,10,14,0.24),inset_0_1px_0_rgba(255,255,255,0.06)]'
                  : 'text-surface-300 hover:bg-surface-800/70 hover:text-surface-100'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-primary-400/18 text-primary-100 ring-1 ring-primary-300/25'
                      : 'text-surface-300 group-hover:text-surface-100'
                  }`}
                >
                  <Icon name={icon} size={17} />
                </span>
                <span className="max-w-full truncate">{shortLabel || label}</span>
                {isActive && (
                  <span className="absolute -bottom-1 h-0.5 w-6 rounded-full bg-primary-200 shadow-[0_0_10px_rgba(136,192,208,0.55)]" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-4">
      <div className="mb-7 rounded-lg border border-surface-600/60 bg-surface-800/70 p-3">
        <h1 className="text-[15px] font-extrabold text-surface-50 tracking-tight flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-400/30 bg-primary-400/10">
            <Icon name="search" size={17} className="text-primary-100" />
          </span>
          Etsy Pipeline
        </h1>
        <p className="text-[11px] text-surface-300 mt-1.5 font-medium">Research console</p>
      </div>

      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-semibold transition-all duration-150 ${
                isActive
                  ? 'text-white bg-primary-400/15 border border-primary-400/25 shadow-[inset_3px_0_0_rgba(111,150,200,0.95)]'
                  : 'text-surface-300 hover:text-surface-50 hover:bg-surface-800/70'
              }`
            }
          >
            <Icon name={icon} size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="pt-4 border-t border-surface-600/60">
        <div className="flex items-center gap-2 rounded-lg border border-surface-600/55 bg-surface-800/55 px-3 py-2 text-[11px]">
          <span className={`w-2 h-2 rounded-full ${statusOk ? 'bg-emerald-400 shadow-[0_0_6px_#a3be8c]' : 'bg-red-400'}`} />
          <span className="text-surface-300 font-medium">
            {statusOk ? 'Fast data ready' : 'Offline'}
          </span>
        </div>
      </div>
    </div>
  )
}

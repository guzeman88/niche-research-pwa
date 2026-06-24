import { useState, useRef, useCallback, type ReactNode } from 'react'
import Icon from './Icon'

interface Props {
  onRefresh: () => Promise<void> | void
  children: ReactNode
  disabled?: boolean
}

export default function PullToRefresh({ onRefresh, children, disabled }: Props) {
  const [pulling, setPulling] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [pullDist, setPullDist] = useState(0)
  const startY = useRef(0)
  const scrollEl = useRef<HTMLDivElement>(null)

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (disabled || refreshing) return
    const el = scrollEl.current
    if (el && el.scrollTop <= 0) {
      startY.current = e.touches[0].clientY
      setPulling(true)
    }
  }, [disabled, refreshing])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!pulling) return
    const dist = Math.max(0, (e.touches[0].clientY - startY.current) * 0.4)
    setPullDist(Math.min(dist, 80))
  }, [pulling])

  const handleTouchEnd = useCallback(async () => {
    if (!pulling) return
    setPulling(false)
    if (pullDist > 50) {
      setRefreshing(true)
      setPullDist(0)
      try { await onRefresh() } catch {
        // Refresh is best-effort; the page keeps the last loaded data.
      }
      setTimeout(() => setRefreshing(false), 400)
    } else {
      setPullDist(0)
    }
  }, [pulling, pullDist, onRefresh])

  return (
    <div className="relative h-full overflow-hidden">
      {/* Pull indicator */}
      <div
        className="absolute left-0 right-0 z-30 flex items-center justify-center transition-all duration-200 pointer-events-none"
        style={{
          top: -60 + Math.min(pullDist, 60),
          opacity: Math.min(pullDist / 40, 1),
        }}
      >
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full bg-surface-900/90 backdrop-blur border border-surface-600/60 shadow-lg ${refreshing ? 'animate-pulse' : ''}`}>
          <Icon name="refresh-cw" size={16} className={`text-primary-200 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="text-[12px] font-semibold text-surface-100">
            {refreshing ? 'Refreshing…' : pullDist > 50 ? 'Release to refresh' : 'Pull to refresh'}
          </span>
        </div>
      </div>

      {/* Content */}
      <div
        ref={scrollEl}
        className="h-full overflow-y-auto"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{
          transform: pulling ? `translateY(${Math.min(pullDist, 60)}px)` : 'translateY(0)',
          transition: pulling ? 'none' : 'transform 0.25s ease-out',
        }}
      >
        {children}
      </div>
    </div>
  )
}

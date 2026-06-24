import { useQuery } from '@tanstack/react-query'
import { getBreakouts } from '../lib/api'
import Icon from './Icon'

export default function BreakoutFeed() {
  const { data: breakouts } = useQuery<{ keyword: string }[]>({
    queryKey: ['breakouts', 'feed'],
    queryFn: () => getBreakouts(15),
    refetchInterval: 30_000,
  })

  if (!breakouts || breakouts.length === 0) {
    return (
      <div className="panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <Icon name="trending-up" size={14} className="text-accent-green" />
          <span className="section-label">Breakout Feed</span>
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse ml-auto" />
        </div>
        <p className="text-[12px] text-surface-300 text-center py-6">No breakouts yet — run more scans to detect velocity</p>
      </div>
    )
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="trending-up" size={14} className="text-accent-green" />
        <span className="section-label">Breakout Feed</span>
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse ml-auto" />
        <span className="text-[10px] text-surface-400 font-medium">{breakouts.length} rising</span>
      </div>
      <div className="space-y-1 max-h-[300px] overflow-y-auto">
        {breakouts.map((b, i) => (
          <div key={b.keyword} className="flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-surface-700/35 transition-colors border-b border-surface-600/25 last:border-0">
            <span className="text-[10px] text-surface-400 w-5 flex-shrink-0 font-bold tabular-nums">{i + 1}</span>
            <Icon name="trending-up" size={12} className="text-accent-green flex-shrink-0" />
            <span className="text-[12px] text-surface-100 font-medium truncate flex-1">{b.keyword}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-green/10 text-accent-green font-bold border border-accent-green/20 flex-shrink-0">↑ BREAKOUT</span>
          </div>
        ))}
      </div>
    </div>
  )
}

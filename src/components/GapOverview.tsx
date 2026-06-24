import { useQuery } from '@tanstack/react-query'
import { getTopGaps } from '../lib/api'
import Icon from './Icon'
import type { GapReport } from '../types/gaps'

const GAP_CONFIG = [
  { key: 'volume_gap_score' as const, label: 'Volume Gap', desc: 'Supply/demand imbalance', color: '#5e81ac', icon: 'bar-chart' as const },
  { key: 'quality_gap_score' as const, label: 'Quality Gap', desc: 'Weak incumbent listings', color: '#a3be8c', icon: 'award' as const },
  { key: 'tag_gap_score' as const, label: 'Tag Gap', desc: 'Uncovered buyer terms', color: '#ebcb8b', icon: 'tag' as const },
  { key: 'price_gap_score' as const, label: 'Price Gap', desc: 'Underserved price range', color: '#b48ead', icon: 'dollar-sign' as const },
  { key: 'style_gap_score' as const, label: 'Style Gap', desc: 'Style monopoly opening', color: '#b48ead', icon: 'grid' as const },
  { key: 'recency_gap_score' as const, label: 'Recency Gap', desc: 'Aging competition', color: '#d08770', icon: 'clock' as const },
]

export default function GapOverview() {
  const { data: gaps } = useQuery<GapReport[]>({ queryKey: ['gaps', 500], queryFn: () => getTopGaps(500) })

  // Compute averages from all gaps
  const averages = GAP_CONFIG.map(config => {
    const allGaps = (gaps || [])
    const values = allGaps.map(g => (g as any)[config.key] as number).filter(v => v != null && !isNaN(v))
    const avg = values.length > 0 ? values.reduce((a: number, b: number) => a + b, 0) / values.length : 0
    return { ...config, avg: Math.round(avg) }
  })

  return (
    <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-4">
        <Icon name="activity" size={14} className="text-primary-200" />
        <span className="text-[11px] font-bold text-surface-200 uppercase tracking-wider">Gap Analysis Overview</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {averages.map(g => (
          <div key={g.key} className="text-center">
            <Icon name={g.icon} size={16} className="mx-auto mb-1.5" />
            <div className="text-lg font-extrabold tracking-tight" style={{ color: g.color }}>{g.avg}</div>
            <div className="text-[9px] text-surface-300 uppercase font-semibold tracking-wide">{g.label}</div>
            <div className="mt-2 h-1 bg-surface-700 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all" style={{ width: `${g.avg}%`, backgroundColor: g.color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

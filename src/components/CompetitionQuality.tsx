import type { KeywordSearchData } from '../types/research'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

export default function CompetitionQuality({ data }: Props) {
  if (!data) return null

  const score = data.competition_quality_score || 0
  const reviewPts = Math.min(40, data.avg_review_count > 500 ? 40 : data.avg_review_count > 150 ? 36 : data.avg_review_count > 50 ? 28 : data.avg_review_count > 20 ? 18 : data.avg_review_count > 5 ? 10 : 5)
  const starPts = Math.min(30, (data.pct_star_sellers || 0) * 0.3)
  const bestPts = Math.min(20, (data.pct_bestsellers || 0) * 0.2)
  const volPts = data.total_listing_count > 0 ? Math.min(10, Math.log10(data.total_listing_count) / Math.log10(500000) * 10) : 5

  const color = score > 70 ? '#bf616a' : score > 40 ? '#ebcb8b' : '#a3be8c'

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="sliders" size={14} className="text-accent-amber" />
        <span className="section-label">Competition Quality</span>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="text-3xl font-extrabold tracking-tight" style={{ color }}>{score.toFixed(0)}</div>
        <div className="flex-1">
          <div className="text-[10px] text-surface-300 mb-1">
            {score > 70 ? 'Hard to compete — very established market' : score > 40 ? 'Moderate competition — achievable with good SEO' : 'Easy entry — weak incumbent listings'}
          </div>
          <div className="progress-track h-2">
            <div className="h-full rounded-full transition-all" style={{ width: `${score}%`, backgroundColor: color }} />
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <BreakdownRow label="Avg Review Count" points={reviewPts} max={40} detail={`${data.avg_review_count?.toFixed(0)} reviews avg`} />
        <BreakdownRow label="Star Sellers" points={starPts} max={30} detail={`${data.pct_star_sellers?.toFixed(0)}% of listings`} />
        <BreakdownRow label="Bestseller Badges" points={bestPts} max={20} detail={`${data.pct_bestsellers?.toFixed(0)}% have it`} />
        <BreakdownRow label="Listing Volume" points={volPts} max={10} detail={`${data.total_listing_count?.toLocaleString()} total`} />
      </div>
    </div>
  )
}

function BreakdownRow({ label, points, max, detail }: { label: string; points: number; max: number; detail: string }) {
  const pct = Math.round((points / max) * 100)
  return (
    <div>
      <div className="flex justify-between items-center text-[10px] mb-0.5">
        <span className="text-surface-200">{label}</span>
        <span className="text-surface-300">{detail}</span>
      </div>
      <div className="progress-track">
        <div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

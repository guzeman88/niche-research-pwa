import type { KeywordSearchData } from '../types/research'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

export default function CompetitionQuality({ data }: Props) {
  if (!data) return null

  const score = finiteNumber(data.competition_quality_score)
  const avgReviewCount = finiteNumber(data.avg_review_count)
  const starPct = finiteNumber(data.pct_star_sellers)
  const bestPct = finiteNumber(data.pct_bestsellers)
  const listingCount = finiteNumber(data.total_listing_count)

  if (score == null && avgReviewCount == null && starPct == null && bestPct == null && listingCount == null) {
    return null
  }

  const reviewPts = avgReviewCount == null
    ? null
    : Math.min(40, avgReviewCount > 500 ? 40 : avgReviewCount > 150 ? 36 : avgReviewCount > 50 ? 28 : avgReviewCount > 20 ? 18 : avgReviewCount > 5 ? 10 : 0)
  const starPts = starPct == null ? null : Math.min(30, starPct * 0.3)
  const bestPts = bestPct == null ? null : Math.min(20, bestPct * 0.2)
  const volPts = listingCount == null || listingCount <= 0 ? null : Math.min(10, Math.log10(listingCount) / Math.log10(500000) * 10)

  const color = score == null ? '#8793a2' : score > 70 ? '#bf616a' : score > 40 ? '#ebcb8b' : '#a3be8c'

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="sliders" size={14} className="text-accent-amber" />
        <span className="section-label">Competition Quality</span>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="text-3xl font-extrabold tracking-tight" style={{ color }}>{score == null ? '-' : score.toFixed(0)}</div>
        <div className="flex-1">
          <div className="text-[10px] text-surface-300 mb-1">
            {score == null ? 'No competition score data yet' : score > 70 ? 'Hard to compete - very established market' : score > 40 ? 'Moderate competition - achievable with good SEO' : 'Easy entry - weak incumbent listings'}
          </div>
          <div className="progress-track h-2">
            {score != null && <div className="h-full rounded-full transition-all" style={{ width: `${score}%`, backgroundColor: color }} />}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <BreakdownRow label="Avg Review Count" points={reviewPts} max={40} detail={avgReviewCount == null ? 'No data' : `${avgReviewCount.toFixed(0)} reviews avg`} />
        <BreakdownRow label="Star Sellers" points={starPts} max={30} detail={starPct == null ? 'No data' : `${starPct.toFixed(0)}% of listings`} />
        <BreakdownRow label="Bestseller Badges" points={bestPts} max={20} detail={bestPct == null ? 'No data' : `${bestPct.toFixed(0)}% have it`} />
        <BreakdownRow label="Listing Volume" points={volPts} max={10} detail={listingCount == null ? 'No data' : `${listingCount.toLocaleString()} total`} />
      </div>
    </div>
  )
}

function BreakdownRow({ label, points, max, detail }: { label: string; points: number | null; max: number; detail: string }) {
  const pct = points == null ? 0 : Math.round((points / max) * 100)
  return (
    <div>
      <div className="flex justify-between items-center text-[10px] mb-0.5">
        <span className="text-surface-200">{label}</span>
        <span className="text-surface-300">{detail}</span>
      </div>
      <div className="progress-track">
        {points != null && <div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-400" style={{ width: `${pct}%` }} />}
      </div>
    </div>
  )
}

function finiteNumber(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

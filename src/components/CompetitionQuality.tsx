import type { KeywordSearchData } from '../types/research'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

export default function CompetitionQuality({ data }: Props) {
  if (!data) return null

  const score = finiteNumber(data.competition_quality_score)
  const observations = [
    ['Average reviews', formatNumber(data.avg_review_count)],
    ['Star sellers', formatPercent(data.pct_star_sellers)],
    ['Bestseller badges', formatPercent(data.pct_bestsellers)],
    ['Total listings', formatInteger(data.total_listing_count)],
  ]

  if (score == null && observations.every(([, value]) => value === 'TBD')) return null

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="sliders" size={14} className="text-accent-amber" />
        <span className="section-label">Competition observations</span>
      </div>

      <div className="rounded-lg border border-surface-600/45 bg-surface-900/45 p-3 mb-3">
        <div className="text-[10px] text-surface-300 uppercase font-semibold">Validated competition rank</div>
        <div className="text-2xl font-extrabold tracking-tight text-surface-200">
          {score == null ? 'TBD' : score.toFixed(0)}
        </div>
        <div className="text-[10px] text-surface-400 mt-1">
          {score == null ? 'Requires a versioned model calibrated against real outcomes.' : 'Versioned score supplied by the evidence record.'}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {observations.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-surface-800/30 p-2.5">
            <div className="text-[9px] text-surface-400 uppercase font-semibold">{label}</div>
            <div className="text-base font-bold text-surface-100 mt-0.5">{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function formatNumber(value: unknown): string {
  const numeric = finiteNumber(value)
  return numeric == null ? 'TBD' : numeric.toFixed(1)
}

function formatInteger(value: unknown): string {
  const numeric = finiteNumber(value)
  return numeric == null ? 'TBD' : numeric.toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function formatPercent(value: unknown): string {
  const numeric = finiteNumber(value)
  return numeric == null ? 'TBD' : `${numeric.toFixed(1)}%`
}

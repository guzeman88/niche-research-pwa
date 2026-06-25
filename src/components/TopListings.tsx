import type { KeywordSearchData } from '../types/research'
import { fmtPrice } from '../lib/utils'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

export default function TopListings({ data }: Props) {
  if (!data || !data.top_listing_titles?.length) return null

  const estMonthlyRevenue = positiveNumber(data.estimated_market_monthly_revenue_usd)
  const reviewCount = finiteNumber(data.avg_review_count)
  const starPct = finiteNumber(data.pct_star_sellers)
  const bestPct = finiteNumber(data.pct_bestsellers)
  const favs = finiteNumber(data.avg_favorites)
  const maxFavorites = finiteNumber(data.max_favorites)

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="package" size={14} className="text-accent-amber" />
        <span className="section-label">Top Listings Overview</span>
      </div>

      <div className="rounded-lg border border-surface-600/45 bg-surface-900/45 p-3 mb-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] text-surface-300 uppercase font-semibold">Est. Market Revenue</div>
            <div className="text-xl font-extrabold text-accent-green tracking-tight">
              {estMonthlyRevenue == null ? 'No data' : <>{fmtPrice(estMonthlyRevenue)}<span className="text-[10px] text-surface-400 font-medium ml-1">/mo</span></>}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-surface-300 uppercase font-semibold">Avg Reviews/Top 20</div>
            <div className="text-lg font-extrabold text-surface-50 tracking-tight">{formatNumber(reviewCount)}</div>
            <div className="text-[9px] text-surface-400">From scraped listing data</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Star Sellers</div>
          <div className="text-lg font-extrabold" style={{ color: scoreColor(starPct) }}>{formatPercent(starPct)}</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Bestsellers</div>
          <div className="text-lg font-extrabold" style={{ color: scoreColor(bestPct) }}>{formatPercent(bestPct)}</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Avg Favorites</div>
          <div className="text-lg font-extrabold text-surface-50">{formatNumber(favs)}</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Max Favorites</div>
          <div className="text-lg font-extrabold text-surface-50">{formatNumber(maxFavorites)}</div>
        </div>
      </div>

      <div className="mt-3">
        <div className="text-[10px] text-surface-300 uppercase font-semibold mb-1.5">Top Listings</div>
        <div className="space-y-1">
          {data.top_listing_titles.slice(0, 5).map((title: string, i: number) => (
            <div key={i} className="flex items-center gap-2 text-[11px] text-surface-200 py-1 border-b border-surface-600/30 last:border-0">
              <span className="text-surface-400 text-[10px] w-4 flex-shrink-0">{i + 1}.</span>
              <span className="truncate">{title}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function finiteNumber(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function positiveNumber(value: unknown): number | null {
  const numeric = finiteNumber(value)
  return numeric != null && numeric > 0 ? numeric : null
}

function formatNumber(value: number | null): string {
  return value == null ? 'No data' : value.toFixed(0)
}

function formatPercent(value: number | null): string {
  return value == null ? 'No data' : `${value.toFixed(0)}%`
}

function scoreColor(value: number | null): string {
  if (value == null) return '#8793a2'
  return value > 40 ? '#bf616a' : value > 20 ? '#ebcb8b' : '#a3be8c'
}

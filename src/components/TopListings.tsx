import type { KeywordSearchData } from '../types/research'
import { fmtPrice } from '../lib/utils'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

export default function TopListings({ data }: Props) {
  if (!data || !data.top_listing_titles?.length) return null

  // Simulated top listings from scraper data — the scraper collects this but we need to surface it
  // For now, show the market-level aggregates with revenue estimates
  const estMonthlyRevenue = data.estimated_market_monthly_revenue_usd || 0
  const reviewCount = data.avg_review_count || 0
  const starPct = data.pct_star_sellers || 0
  const bestPct = data.pct_bestsellers || 0
  const favs = data.avg_favorites || 0

  // Revenue calculation explanation (EverBee heuristic)
  const estSales = Math.round(reviewCount * 20) // reviews × 20 = estimated lifetime sales
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="package" size={14} className="text-accent-amber" />
        <span className="section-label">Top Listings Overview</span>
      </div>

      {/* Revenue estimate card */}
      <div className="rounded-lg border border-surface-600/45 bg-surface-900/45 p-3 mb-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] text-surface-300 uppercase font-semibold">Est. Market Revenue</div>
            <div className="text-xl font-extrabold text-accent-green tracking-tight">{fmtPrice(estMonthlyRevenue)}<span className="text-[10px] text-surface-400 font-medium ml-1">/mo</span></div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-surface-300 uppercase font-semibold">Avg Reviews/Top 20</div>
            <div className="text-lg font-extrabold text-surface-50 tracking-tight">{reviewCount.toFixed(0)}</div>
            <div className="text-[9px] text-surface-400">× 20 = ~{estSales} est. sales</div>
          </div>
        </div>
      </div>

      {/* Competition quality indicators */}
      <div className="grid grid-cols-2 gap-2 mb-2">
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Star Sellers</div>
          <div className="text-lg font-extrabold" style={{ color: starPct > 40 ? '#bf616a' : starPct > 20 ? '#ebcb8b' : '#a3be8c' }}>{starPct.toFixed(0)}%</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Bestsellers</div>
          <div className="text-lg font-extrabold" style={{ color: bestPct > 30 ? '#bf616a' : bestPct > 15 ? '#ebcb8b' : '#a3be8c' }}>{bestPct.toFixed(0)}%</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Avg Favorites</div>
          <div className="text-lg font-extrabold text-surface-50">{favs.toFixed(0)}</div>
        </div>
        <div className="bg-surface-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[10px] text-surface-300 uppercase font-semibold mb-0.5">Max Favorites</div>
          <div className="text-lg font-extrabold text-surface-50">{data.max_favorites || 0}</div>
        </div>
      </div>

      {/* Listing titles from the report payload */}
      <div className="mt-3">
        <div className="text-[10px] text-surface-300 uppercase font-semibold mb-1.5">Top Listings</div>
        <div className="space-y-1">
          {(data.top_listing_titles || []).slice(0, 5).map((title: string, i: number) => (
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

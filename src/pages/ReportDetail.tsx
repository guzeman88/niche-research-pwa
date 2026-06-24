import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getReport } from '../lib/api'
import Icon from '../components/Icon'
import ScoreBadge from '../components/ScoreBadge'
import SeasonalityChart from '../components/SeasonalityChart'
import PriceDistribution from '../components/PriceDistribution'
import TopListings from '../components/TopListings'
import CompetitionQuality from '../components/CompetitionQuality'
import GapMeter from '../components/GapMeter'
import { fmtPrice, fmtDate, scoreColor } from '../lib/utils'
import type { NicheReport, KeywordSearchData } from '../types/research'

export default function ReportDetail() {
  const { reportId } = useParams<{ reportId: string }>()
  const { data: report, isLoading, isError } = useQuery<NicheReport>({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId!),
    enabled: !!reportId,
  })

  if (isLoading) return <div className="p-8 text-center text-surface-300">Loading report…</div>
  if (isError || !report) return (
    <div className="p-8 text-center">
      <Icon name="x-circle" size={48} className="text-surface-400 mx-auto mb-4" />
      <h3 className="text-lg font-bold text-white mb-2">Report not found</h3>
      <Link to="/explore" className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-400 text-surface-50 text-[13px] font-semibold rounded-xl mt-3">Back to Explore</Link>
    </div>
  )

  const scraperData: KeywordSearchData | null = report.keyword_search_data?.[0] || null

  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/" className="text-surface-300 hover:text-surface-100">
          <Icon name="arrow-left" size={20} />
        </Link>
        <div>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">{report.seed_keywords?.join(', ')}</h2>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[11px] text-surface-300">{fmtDate(report.generated_at)}</span>
            <span className="text-[11px] text-surface-400">·</span>
            <span className="text-[11px] text-surface-300">Sources: {report.sources_used?.join(', ') || 'none'}</span>
          </div>
        </div>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-5 gap-2.5">
        <ScoreSquare label="Opportunity" score={report.opportunity_score} color="emerald" />
        <ScoreSquare label="Demand" score={report.demand_score} color="indigo" />
        <ScoreSquare label="Competition" score={report.competition_score} color="amber" invert />
        <ScoreSquare label="Margin" score={report.margin_score} color="violet" />
        <ScoreSquare label="Trend" score={report.trend_velocity_score} color="blue" />
      </div>

      {/* Market overview + Price chart */}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Icon name="globe" size={14} className="text-primary-200" />
            <span className="text-[11px] font-bold text-surface-200 uppercase tracking-wider">Market Overview</span>
          </div>
          <MetRow label="Avg Price" value={fmtPrice(report.avg_price_usd)} />
          <MetRow label="Sweet Spot" value={report.price_sweet_spot || '—'} accent />
          <MetRow label="Est. Monthly Revenue" value={fmtPrice(report.estimated_market_monthly_revenue_usd)} />
          <MetRow label="Comp. Quality" value={`${report.avg_competition_quality?.toFixed(0) || '—'}/100`} />
          {scraperData && <MetRow label="Total Listings" value={scraperData.total_listing_count?.toLocaleString() || '—'} />}
        </div>
        <PriceDistribution data={scraperData} />
      </div>

      {/* Top listings + Competition quality */}
      <div className="grid lg:grid-cols-2 gap-5">
        <TopListings data={scraperData} />
        <CompetitionQuality data={scraperData} />
      </div>

      {/* Seasonality + Favorites */}
      <div className="grid lg:grid-cols-2 gap-5">
        <SeasonalityChart data={report.seasonality || []} peakMonths={report.peak_months || []} />
        <FavoritesAnalytics data={scraperData} />
      </div>

      {/* Gap meter */}
      {report.report_id && (
        <GapMeterWrapper keyword={report.seed_keywords?.[0] || ''} />
      )}

      {/* AI Synthesis */}
      {(report.keyword_clusters?.length > 0 || report.entry_strategy) && (
        <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl p-5 space-y-4">
          <h3 className="text-[12px] font-bold text-surface-100 flex items-center gap-2"><Icon name="cpu" size={16} className="text-primary-200" />AI Synthesis</h3>
          {report.keyword_clusters?.map((c, i) => (
            <div key={i} className="bg-surface-800/50 rounded-xl p-4 border border-surface-500/40">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[13px] font-bold text-surface-50">{c.cluster_name}</span>
                <span className="text-[11px] text-surface-300">~{fmtPrice(c.estimated_monthly_revenue_potential_usd)}/mo</span>
              </div>
              <p className="text-[11px] text-surface-300 mb-2">{c.rationale}</p>
              <div className="flex flex-wrap gap-1.5">
                {c.keywords?.map((k: string, j: number) => <span key={j} className="text-[10px] px-2.5 py-0.5 rounded-full bg-primary-400/10 text-primary-200 font-medium border border-primary-400/15">{k}</span>)}
              </div>
            </div>
          ))}
          {report.underserved_angles?.length > 0 && (
            <div>
              <h4 className="text-[11px] font-bold text-surface-200 uppercase tracking-wider mb-2">Underserved Angles</h4>
              <ul className="list-disc list-inside text-[12px] text-surface-100 space-y-1">
                {report.underserved_angles.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
          {report.competitor_gaps?.length > 0 && (
            <div>
              <h4 className="text-[11px] font-bold text-surface-200 uppercase tracking-wider mb-2">Competitor Gaps</h4>
              <ul className="list-disc list-inside text-[12px] text-surface-100 space-y-1">
                {report.competitor_gaps.map((g, i) => <li key={i}>{g}</li>)}
              </ul>
            </div>
          )}
          {report.entry_strategy && (
            <div>
              <h4 className="text-[11px] font-bold text-surface-200 uppercase tracking-wider mb-1.5">Entry Strategy</h4>
              <p className="text-[12px] text-surface-100 leading-relaxed">{report.entry_strategy}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sub-components ──

function ScoreSquare({ label, score, color, invert }: { label: string; score: number; color: string; invert?: boolean }) {
  const display = invert ? 100 - score : score
  const colors: Record<string, string> = { emerald: 'text-accent-green', indigo: 'text-accent-blue', amber: 'text-accent-amber', violet: 'text-accent-violet', blue: 'text-accent-blue' }
  return (
    <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl p-3 text-center">
      <div className="text-[9px] text-surface-300 uppercase font-semibold tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-extrabold tracking-tight ${colors[color] || 'text-surface-50'}`}>{Math.round(display)}</div>
      <div className="text-[10px] text-surface-400">/100</div>
    </div>
  )
}

function MetRow({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-surface-500/30 last:border-0">
      <span className="text-[11px] text-surface-200">{label}</span>
      <span className={`text-[12px] font-bold ${accent ? 'text-primary-200' : 'text-surface-50'}`}>{value}</span>
    </div>
  )
}

function FavoritesAnalytics({ data }: { data: KeywordSearchData | null }) {
  if (!data) return null
  return (
    <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="star" size={14} className="text-accent-amber" />
        <span className="text-[11px] font-bold text-surface-200 uppercase tracking-wider">Favorites Analytics</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="text-center bg-surface-800/30 rounded-lg p-3">
          <div className="text-lg font-extrabold text-surface-50">{data.avg_favorites?.toFixed(0) || '—'}</div>
          <div className="text-[9px] text-surface-300 uppercase font-semibold">Avg Favorites</div>
        </div>
        <div className="text-center bg-surface-800/30 rounded-lg p-3">
          <div className="text-lg font-extrabold text-surface-50">{data.max_favorites || '—'}</div>
          <div className="text-[9px] text-surface-300 uppercase font-semibold">Max Favorites</div>
        </div>
        <div className="text-center bg-surface-800/30 rounded-lg p-3">
          <div className="text-lg font-extrabold text-surface-50">{data.pct_high_favorites?.toFixed(0) || '—'}%</div>
          <div className="text-[9px] text-surface-300 uppercase font-semibold">High (&ge;100)</div>
        </div>
      </div>
      <p className="text-[10px] text-surface-400 mt-3 text-center">
        Favorites = explicit save-for-later intent. High favorites with low competition = strong buyer demand signal.
      </p>
    </div>
  )
}

// Gap meter wrapper — fetches gap data for this keyword
function GapMeterWrapper({ keyword }: { keyword: string }) {
  const { data: gap } = useQuery<any>({
    queryKey: ['gap', keyword],
    queryFn: async () => {
      try { return await (await fetch(`https://niche-research-api.onrender.com/api/gaps/${encodeURIComponent(keyword)}`)).json() } catch { return null }
    },
    enabled: !!keyword,
  })

  if (!gap) return null

  const signals = [
    { label: 'Volume Gap', score: gap.volume_gap_score || 0, weight: 0.25 },
    { label: 'Quality Gap', score: gap.quality_gap_score || 0, weight: 0.15 },
    { label: 'Tag Gap', score: gap.tag_gap_score || 0, weight: 0.25 },
    { label: 'Style Gap', score: gap.style_gap_score || 0, weight: 0.15 },
    { label: 'Price Gap', score: gap.price_gap_score || 0, weight: 0.10 },
    { label: 'Recency Gap', score: gap.recency_gap_score || 0, weight: 0.10 },
  ]

  return (
    <>
      <GapMeter signals={signals} compositeScore={gap.composite_gap_score || 0} />
      {gap.entry_angle && (
        <div className="bg-indigo-950/30 border border-accent-blue/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1.5">
            <Icon name="target" size={14} className="text-accent-blue" />
            <span className="text-[11px] font-bold text-accent-blue uppercase tracking-wider">Entry Angle</span>
          </div>
          <p className="text-[12px] text-surface-100 leading-relaxed">{gap.entry_angle}</p>
        </div>
      )}
    </>
  )
}

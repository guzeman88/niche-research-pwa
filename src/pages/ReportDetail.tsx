import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getReport } from '../lib/api'
import ScoreBadge from '../components/ScoreBadge'
import SeasonalityChart from '../components/SeasonalityChart'
import { fmtPrice, fmtDate } from '../lib/utils'
import type { NicheReport } from '../types/research'

export default function ReportDetail() {
  const { reportId } = useParams<{ reportId: string }>()

  const { data: report, isLoading } = useQuery<NicheReport>({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId!),
    enabled: !!reportId,
  })

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <div className="text-slate-500">Loading report…</div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="p-6">
        <div className="card text-center py-12">
          <h3 className="text-lg font-semibold text-slate-300 mb-2">Report not found</h3>
          <Link to="/explore" className="btn-primary mt-4">Back to Explore</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-slate-500 hover:text-slate-300 text-sm">← Back</Link>
        <h2 className="text-xl font-bold text-white">{report.seed_keywords?.join(', ')}</h2>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="card text-center"><div className="text-xs text-slate-500">Opportunity</div><div className="text-xl font-bold text-emerald-400">{report.opportunity_score?.toFixed(0)}</div></div>
        <div className="card text-center"><div className="text-xs text-slate-500">Demand</div><div className="text-xl font-bold text-blue-400">{report.demand_score?.toFixed(0)}</div></div>
        <div className="card text-center"><div className="text-xs text-slate-500">Competition</div><div className="text-xl font-bold text-amber-400">{report.competition_score?.toFixed(0)}</div></div>
        <div className="card text-center"><div className="text-xs text-slate-500">Margin</div><div className="text-xl font-bold text-green-400">{report.margin_score?.toFixed(0)}</div></div>
        <div className="card text-center"><div className="text-xs text-slate-500">Trend</div><div className="text-xl font-bold text-purple-400">{report.trend_velocity_score?.toFixed(0)}</div></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card"><div className="text-xs text-slate-500">Avg Price</div><div className="text-lg font-bold">{fmtPrice(report.avg_price_usd)}</div></div>
        <div className="card"><div className="text-xs text-slate-500">Monthly Revenue</div><div className="text-lg font-bold">{fmtPrice(report.estimated_market_monthly_revenue_usd)}</div></div>
        <div className="card"><div className="text-xs text-slate-500">Comp Quality</div><div className="text-lg font-bold">{report.avg_competition_quality?.toFixed(0)}/100</div></div>
        <div className="card"><div className="text-xs text-slate-500">Sources</div><div className="text-lg font-bold">{report.sources_used?.length || 0}</div></div>
      </div>

      <SeasonalityChart data={report.seasonality || []} peakMonths={report.peak_months || []} />

      {report.entry_strategy && (
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Entry Strategy</h3>
          <p className="text-sm text-slate-400">{report.entry_strategy}</p>
        </div>
      )}

      {report.underserved_angles?.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Underserved Angles</h3>
          <ul className="list-disc list-inside text-sm text-slate-400 space-y-1">
            {report.underserved_angles.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      <div className="text-xs text-slate-600">Report ID: {report.report_id} · {fmtDate(report.generated_at)}</div>
    </div>
  )
}

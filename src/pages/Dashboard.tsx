import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getStats, getHealth, getBreakouts, listReports } from '../lib/api'
import StatsCard from '../components/StatsCard'
import ScoreBadge from '../components/ScoreBadge'
import { fmt, fmtDate } from '../lib/utils'
import type { StatsResponse, HealthResponse } from '../types/api'
import type { ReportListItem } from '../types/research'

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery<StatsResponse>({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 10_000,
  })

  const { data: health } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
  })

  const { data: breakouts } = useQuery<{ keyword: string; breakout: boolean }[]>({
    queryKey: ['breakouts'],
    queryFn: () => getBreakouts(10),
  })

  const { data: reports } = useQuery<ReportListItem[]>({
    queryKey: ['reports'],
    queryFn: () => listReports('__global__', 10),
  })

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Dashboard</h2>
          <p className="text-sm text-slate-500 mt-1">Niche research overview</p>
        </div>
        <Link to="/explore" className="btn-primary">+ New Research</Link>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatsCard label="Total Seeds" value={fmt(stats?.total_seeds)} subtitle={`${stats?.scanned || 0} scanned`} color="blue" />
        <StatsCard label="Coverage" value={`${stats?.coverage_pct || 0}%`} subtitle={`${fmt(stats?.unscanned)} remaining`} color="green" />
        <StatsCard label="Avg Opportunity" value={stats?.avg_opportunity ? `${stats.avg_opportunity}%` : '—'} color="amber" />
        <StatsCard label="Breakouts" value={fmt(stats?.breakout_count)} subtitle="rapidly improving" color="red" />
        <StatsCard label="Avg Gap Score" value={stats?.avg_gap_score ? `${stats.avg_gap_score}%` : '—'} />
        <StatsCard label="DB Size" value={health ? `${health.size_mb} MB` : '—'} subtitle={`v${health?.schema_version || '?'}`} />
        <StatsCard label="Top Gap Keyword" value={stats?.top_gap_keyword?.keyword || '—'} subtitle={stats?.top_gap_keyword ? `score: ${stats.top_gap_keyword.gap_score}` : ''} />
        <StatsCard label="Domains" value={fmt(stats?.domains?.length)} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Breakouts */}
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">🔴 Breakout Keywords</h3>
          {breakouts && breakouts.length > 0 ? (
            <div className="space-y-2">
              {breakouts.map((b) => (
                <div key={b.keyword} className="flex items-center justify-between py-1 border-b border-surface-700 last:border-0">
                  <span className="text-sm text-slate-300">{b.keyword}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">BREAKOUT</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No breakouts detected yet. Run more scans to detect velocity.</p>
          )}
        </div>

        {/* Recent reports */}
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Recent Reports</h3>
          {reports && reports.length > 0 ? (
            <div className="space-y-2">
              {reports.map((r) => (
                <Link
                  key={r.report_id}
                  to={`/reports/${r.report_id}`}
                  className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-surface-700/50 transition-colors"
                >
                  <div>
                    <div className="text-sm text-slate-300">{r.seed_keywords?.join(', ') || 'Unnamed'}</div>
                    <div className="text-xs text-slate-500">{fmtDate(r.generated_at)}</div>
                  </div>
                  <ScoreBadge score={r.opportunity_score} size="sm" />
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No reports yet. Run your first research!</p>
          )}
        </div>
      </div>
    </div>
  )
}

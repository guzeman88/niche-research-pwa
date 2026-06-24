import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getStats, listReports } from '../lib/api'
import Icon from '../components/Icon'
import ScoreDistribution from '../components/ScoreDistribution'
import GapOverview from '../components/GapOverview'
import BreakoutFeed from '../components/BreakoutFeed'
import PullToRefresh from '../components/PullToRefresh'
import { DashboardSkeleton } from '../components/Skeleton'
import { fmt, fmtDate, scoreColor } from '../lib/utils'
import type { StatsResponse } from '../types/api'
import type { ReportListItem } from '../types/research'

export default function Dashboard() {
  const qc = useQueryClient()
  const { data: stats } = useQuery<StatsResponse>({ queryKey: ['stats'], queryFn: getStats, refetchInterval: 15_000 })
  const { data: reports } = useQuery<ReportListItem[]>({ queryKey: ['reports'], queryFn: () => listReports('__global__', 12) })
  const refresh = () => { qc.invalidateQueries(); return Promise.resolve() }

  const opportunities = (reports || []).sort((a, b) => (b.opportunity_score || 0) - (a.opportunity_score || 0)).slice(0, 8)
  const domains = (stats?.domains || []).sort((a: any, b: any) => (b.cnt || 0) - (a.cnt || 0)).slice(0, 6)
  const topOpportunity = opportunities[0]
  const topGap = (stats as any)?.top_gap_keyword

  if (!stats && !reports) return <DashboardSkeleton />

  return (
    <PullToRefresh onRefresh={refresh}>
    <div className="page">
      <div className="page-header">
        <div>
          <p className="text-[12px] text-primary-100 font-semibold">Etsy intelligence</p>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Dashboard</h2>
        </div>
        <Link to="/explore" className="btn-primary text-[13px]">
          <Icon name="plus-circle" size={16} />
          Research
        </Link>
      </div>

      <div className="flex gap-2.5 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none">
        <Chip val={fmt(stats?.total_seeds)} label="Keywords" sub={`${stats?.total_seeds || 0} seeds`} color="indigo" />
        <Chip val={stats?.avg_opportunity ? `${stats.avg_opportunity}` : '-'} label="Avg Opp" sub={topOpportunity ? 'from reports' : 'no reports'} color="emerald" />
        <Chip val={fmt(stats?.breakout_count)} label="Breakouts" sub="rising fast" color="amber" />
        <Chip val={stats?.avg_gap_score ? `${stats.avg_gap_score}` : '-'} label="Avg Gap" sub={topGap?.keyword ? 'top gap available' : 'no gap data'} color="violet" />
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <MetricCard icon="database" label="Coverage" value={`${stats?.coverage_pct || 0}%`} sub={`${fmt(stats?.scanned)} of ${fmt(stats?.total_seeds)} scanned`} color="indigo" />
        <MetricCard icon="target" label="Avg Opportunity" value={stats?.avg_opportunity ? `${stats.avg_opportunity}` : '-'} sub={topOpportunity ? `Top: ${topOpportunity.seed_keywords?.join(', ') || 'Unnamed'} ${(topOpportunity.opportunity_score || 0).toFixed(1)}` : 'No reports yet'} color="emerald" />
        <MetricCard icon="zap" label="Total Scans" value={fmt(stats?.total_scans)} sub={`${fmt(stats?.domains?.length)} domains`} color="amber" />
        <MetricCard icon="activity" label="Avg Gap Score" value={stats?.avg_gap_score ? `${stats.avg_gap_score}` : '-'} sub={topGap?.keyword ? `Top: ${topGap.keyword} ${(topGap.gap_score || 0).toFixed(1)}` : 'No gap data yet'} color="violet" />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <ScoreDistribution />
        <GapOverview />
      </div>

      <Section title="Top Opportunities" link="/keywords" linkLabel="See all">
        <div className="panel overflow-hidden">
          {opportunities.length > 0 ? opportunities.map((r, i) => (
            <Link
              key={r.report_id}
              to={`/reports/${r.report_id}`}
              className="flex items-center gap-3 px-4 py-3 border-b border-surface-600/35 last:border-b-0 hover:bg-surface-700/45 transition-colors"
            >
              <RankBadge rank={i + 1} />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-semibold text-surface-50 truncate">{r.seed_keywords?.join(', ') || 'Unnamed'}</div>
                <div className="text-[10px] text-surface-300 mt-0.5">{fmtDate(r.generated_at)}</div>
              </div>
              <div className="flex items-center gap-2">
                <div className="progress-track w-12 hidden sm:block">
                  <div className="h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, (r.opportunity_score || 0))}%` }} />
                </div>
                <span className={`text-[13px] font-bold tabular-nums ${scoreColor(r.opportunity_score || 0)}`}>{(r.opportunity_score || 0).toFixed(1)}</span>
              </div>
            </Link>
          )) : (
            <div className="px-4 py-10 text-center text-sm text-surface-300">No reports yet.</div>
          )}
        </div>
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Domain Breakdown" subtitle="by keyword volume">
          <div className="panel p-4 space-y-2.5">
            {domains.length > 0 ? domains.map((d: any) => (
              <div key={d.domain} className="flex items-center gap-3">
                <span className="text-[11px] text-surface-200 w-20 text-right truncate flex-shrink-0">{d.domain}</span>
                <div className="progress-track flex-1">
                  <div className="h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, (d.cnt / (Math.max(...(domains.map((x: any) => x.cnt) || [1])) || 1)) * 100)}%` }} />
                </div>
                <span className="text-[11px] font-bold text-surface-100 w-8 text-right tabular-nums">{d.cnt}</span>
              </div>
            )) : (
              <div className="text-sm text-surface-300 text-center py-6">No domain data yet</div>
            )}
          </div>
        </Section>

        <BreakoutFeed />
      </div>
    </div>
    </PullToRefresh>
  )
}

function Chip({ val, label, sub, color }: { val: string; label: string; sub: string; color: 'indigo' | 'emerald' | 'amber' | 'violet' }) {
  const colors = { indigo: 'from-surface-800 to-surface-700/50 border-accent-blue/20', emerald: 'from-accent-green/20 to-accent-green/10 border-accent-green/20', amber: 'from-accent-amber/20 to-accent-amber/10 border-accent-amber/20', violet: 'from-accent-violet/20 to-accent-violet/10 border-accent-violet/20' }
  const textColors = { indigo: 'text-accent-blue', emerald: 'text-accent-green', amber: 'text-accent-amber', violet: 'text-accent-violet' }
  return (
    <div className={`flex-shrink-0 bg-gradient-to-b ${colors[color]} border rounded-lg px-4 py-2.5 min-w-[98px] shadow-[0_10px_24px_rgba(7,10,14,0.14)]`}>
      <div className={`text-lg font-extrabold tracking-tight ${textColors[color]}`}>{val}</div>
      <div className="text-[10px] text-surface-200 font-medium">{label}</div>
      <div className="text-[9px] text-surface-400 mt-0.5">{sub}</div>
    </div>
  )
}

function MetricCard({ icon, label, value, sub, color }: { icon: import('../components/Icon').IconName; label: string; value: string; sub: string; color: 'indigo' | 'emerald' | 'amber' | 'violet' }) {
  const borders = { indigo: 'border-t-indigo-500/30', emerald: 'border-t-emerald-500/30', amber: 'border-t-amber-500/30', violet: 'border-t-violet-500/30' }
  const textColors = { indigo: 'text-accent-blue', emerald: 'text-accent-green', amber: 'text-accent-amber', violet: 'text-accent-violet' }
  return (
    <div className={`metric-panel border-t-2 ${borders[color]}`}>
      <Icon name={icon} size={18} className={`${textColors[color]} mb-2`} />
      <div className="text-xl font-extrabold text-surface-50 tracking-tight">{value}</div>
      <div className="text-[10px] text-surface-300 mt-0.5 uppercase tracking-wide font-semibold">{label}</div>
      <div className="text-[10px] text-surface-400 mt-0.5">{sub}</div>
    </div>
  )
}

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return <span className="w-6 h-6 rounded-lg bg-accent-amber/15 text-accent-amber flex items-center justify-center text-[11px] font-extrabold border border-accent-amber/20 flex-shrink-0">1</span>
  if (rank === 2) return <span className="w-6 h-6 rounded-lg bg-surface-200/10 text-surface-200 flex items-center justify-center text-[11px] font-extrabold border border-surface-200/15 flex-shrink-0">2</span>
  if (rank === 3) return <span className="w-6 h-6 rounded-lg bg-amber-700/10 text-accent-amber-600 flex items-center justify-center text-[11px] font-extrabold border border-amber-700/15 flex-shrink-0">3</span>
  return <span className="w-6 h-6 rounded-lg bg-transparent text-surface-400 flex items-center justify-center text-[11px] font-bold flex-shrink-0">{rank}</span>
}

function Section({ title, subtitle, link, linkLabel, icon, children }: { title: string; subtitle?: string; link?: string; linkLabel?: string; icon?: import('../components/Icon').IconName; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-1.5">
          {icon && <Icon name={icon} size={14} className="text-surface-300" />}
          <span className="section-label">{title}</span>
          {subtitle && <span className="text-[10px] text-surface-400 ml-1">{subtitle}</span>}
        </div>
        {link && linkLabel && <Link to={link} className="text-[11px] font-semibold text-primary-200 hover:text-primary-200">{linkLabel} -&gt;</Link>}
      </div>
      {children}
    </div>
  )
}

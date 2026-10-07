import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getOpportunities, listReports } from '../lib/api'
import Icon from '../components/Icon'
import ScoreDistribution from '../components/ScoreDistribution'
import GapOverview from '../components/GapOverview'
import BreakoutFeed from '../components/BreakoutFeed'
import PullToRefresh from '../components/PullToRefresh'
import { DashboardSkeleton } from '../components/Skeleton'
import { fmt, fmtDate, scoreColor } from '../lib/utils'
import type { DashboardSummary, StatsResponse } from '../types/api'
import type { ReportListItem } from '../types/research'
import { useAppMode } from '../lib/appMode'
import { getUserOpportunities, getUserStats } from '../lib/userData'
import { dashboardFreshness, getDashboardSummary, refreshDashboardSummary } from '../lib/dashboardSummary'

interface DashboardOpportunity {
  id: string
  title: string
  generatedAt?: string | null
  opportunityScore: number | null
}

export default function Dashboard() {
  const qc = useQueryClient()
  const { mode, isUserMode, userDataVersion } = useAppMode()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { data: userStats } = useQuery<StatsResponse>({
    queryKey: ['stats', 'user', userDataVersion],
    queryFn: getUserStats,
    enabled: isUserMode,
  })
  const { data: dashboard } = useQuery<DashboardSummary>({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummary,
    enabled: !isUserMode,
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
  const { data: reports } = useQuery<ReportListItem[]>({
    queryKey: ['reports', mode],
    queryFn: () => listReports('__global__', 12),
    enabled: !isUserMode,
  })
  const { data: keywordOpportunities } = useQuery<Record<string, unknown>[]>({
    queryKey: ['opportunities', 'dashboard', mode, userDataVersion],
    queryFn: () => isUserMode ? getUserOpportunities(12) : getOpportunities(undefined, 12),
  })
  const stats = isUserMode ? userStats : dashboard?.stats
  const refresh = async () => {
    setIsRefreshing(true)
    try {
      if (!isUserMode) {
        const next = await refreshDashboardSummary()
        qc.setQueryData(['dashboard-summary'], next)
      }
      await qc.refetchQueries({ type: 'active' })
    } catch {
      await qc.refetchQueries({ queryKey: ['dashboard-summary'] })
    } finally {
      setIsRefreshing(false)
    }
  }

  const opportunities = normalizeDashboardOpportunities(reports, keywordOpportunities)
  const domains = (stats?.domains || []).sort((a: any, b: any) => (b.cnt || 0) - (a.cnt || 0)).slice(0, 6)
  const topOpportunity = opportunities[0]
  const topGap = (stats as any)?.top_gap_keyword

  if (!stats && !reports && !keywordOpportunities) return <DashboardSkeleton />

  return (
    <PullToRefresh onRefresh={refresh}>
    <div className="page">
      <div className="page-header">
        <div>
          <p className="text-[12px] text-primary-100 font-semibold">{isUserMode ? 'User scan workspace' : 'EtGen intelligence'}</p>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Dashboard</h2>
        </div>
        <Link to="/store-generator" className="btn-primary text-[13px]">
          <Icon name="plus-circle" size={16} />
          Generate Ideas
        </Link>
      </div>

      {!isUserMode && dashboard && <FreshnessBar dashboard={dashboard} refreshing={isRefreshing} onRefresh={refresh} />}

      <div className="grid grid-cols-2 gap-2.5 sm:flex sm:overflow-x-auto sm:pb-1 sm:-mx-1 sm:px-1 sm:scrollbar-none">
        <Chip val={fmt(stats?.total_seeds)} label="Keywords" sub={stats?.total_seeds ? (isUserMode ? 'user scan rows' : `${stats.total_seeds} seeds`) : 'No data'} color="indigo" />
        <Chip val={stats?.avg_opportunity != null ? `${stats.avg_opportunity}` : 'TBD'} label="Avg Opp" sub={topOpportunity ? 'verified ranking' : 'Awaiting evidence'} color="emerald" />
        <Chip val={fmt(stats?.breakout_count)} label="Breakouts" sub={isUserMode ? 'from imports' : 'rising fast'} color="amber" />
        <Chip val={stats?.avg_gap_score != null ? `${stats.avg_gap_score}` : 'TBD'} label="Avg Gap" sub={topGap?.keyword ? 'verified gap' : 'Awaiting evidence'} color="violet" />
      </div>

      {!isUserMode && stats?.evidence_backed != null && (
        <p className="text-sm text-surface-200" role="status">
          {fmt(stats.evidence_backed)} keywords have marketplace supply or pricing evidence. {fmt(stats.successful)} returned source signals;
          {' '}{fmt(stats.no_data)} returned no data; {fmt(stats.failed)} failed; {fmt(stats.stale)} are over 30 days old.
          {stats.evidence_backed === 0 && ' Rankings remain TBD until verified inputs and a versioned model are available.'}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2.5">
        <MetricCard icon="database" label="Attempted coverage" value={stats?.coverage_pct == null ? 'TBD' : `${stats.coverage_pct}%`} sub={`${fmt(stats?.scanned)} of ${fmt(stats?.total_seeds)} attempted`} color="indigo" />
        <MetricCard icon="target" label="Avg Opportunity" value={stats?.avg_opportunity != null ? `${stats.avg_opportunity}` : 'TBD'} sub={topOpportunity ? `Top: ${topOpportunity.title} ${formatScore(topOpportunity.opportunityScore)}` : 'Awaiting verified score'} color="emerald" />
        <MetricCard icon="zap" label="Historical scan records" value={fmt(stats?.total_scans)} sub="lifetime database total" color="amber" />
        <MetricCard icon="activity" label="Avg Gap Score" value={stats?.avg_gap_score != null ? `${stats.avg_gap_score}` : 'TBD'} sub={topGap?.keyword ? `Top: ${topGap.keyword} ${formatScore(topGap.gap_score)}` : 'Awaiting verified score'} color="violet" />
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <ScoreDistribution />
        <GapOverview />
      </div>

      <Section title="Research leads" link="/keywords" linkLabel="See all">
        <div className="panel overflow-hidden">
          {opportunities.length > 0 ? opportunities.map((r, i) => (
            <div
              key={r.id}
              className="flex items-center gap-3 px-4 py-3 border-b border-surface-600/35 last:border-b-0"
            >
              <RankBadge rank={i + 1} />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-semibold text-surface-50 truncate">{r.title}</div>
                <div className="text-[10px] text-surface-300 mt-0.5">{r.generatedAt ? fmtDate(r.generatedAt) : 'keyword scan'}</div>
              </div>
              <div className="flex items-center gap-2">
                <div className="progress-track w-12 hidden sm:block">
                  {r.opportunityScore != null && <div className="h-full rounded-full bg-linear-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, r.opportunityScore)}%` }} />}
                </div>
                <span className={`text-[13px] font-bold tabular-nums ${r.opportunityScore == null ? 'text-surface-400' : scoreColor(r.opportunityScore)}`}>{formatScore(r.opportunityScore)}</span>
              </div>
            </div>
          )) : (
            <div className="px-4 py-10 text-center text-sm text-surface-300">Opportunity rankings are TBD until verified evidence is available.</div>
          )}
        </div>
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Domain Breakdown" subtitle="by keyword volume">
          <div className="panel p-4 space-y-2.5">
            {domains.length > 0 ? domains.map((d: any) => (
              <div key={d.domain} className="flex items-center gap-3">
                <span className="text-[11px] text-surface-200 w-20 text-right truncate shrink-0">{d.domain}</span>
                <div className="progress-track flex-1">
                  <div className="h-full rounded-full bg-linear-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, (d.cnt / (Math.max(...(domains.map((x: any) => x.cnt) || [1])) || 1)) * 100)}%` }} />
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

function FreshnessBar({ dashboard, refreshing, onRefresh }: { dashboard: DashboardSummary; refreshing: boolean; onRefresh: () => Promise<void> }) {
  const freshness = dashboardFreshness(dashboard.generated_at)
  const fallback = dashboard.delivery.mode === 'fallback'
  const degraded = dashboard.data_status === 'degraded' || freshness !== 'fresh' || fallback
  const label = fallback ? 'Static fallback' : freshness === 'stale' ? 'Live data stale' : freshness === 'delayed' ? 'Live data delayed' : dashboard.data_status === 'degraded' ? 'Live · provider issue' : 'Live · current'
  const detail = `${relativeAge(dashboard.generated_at)} · snapshot ${String(dashboard.snapshot_version).slice(0, 12)}`
  return (
    <div className={`flex flex-col gap-3 rounded-lg border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${degraded ? 'border-accent-amber/30 bg-accent-amber/5' : 'border-accent-green/25 bg-accent-green/5'}`} role="status">
      <div className="flex min-w-0 items-start gap-3">
        <Icon name={degraded ? 'alert-triangle' : 'check-circle'} size={17} className={`mt-0.5 shrink-0 ${degraded ? 'text-accent-amber' : 'text-accent-green'}`} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className={`text-[12px] font-bold ${degraded ? 'text-accent-amber' : 'text-accent-green'}`}>{label}</span>
            <span className="text-[11px] text-surface-300">{detail}</span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-surface-300">
            Coverage refreshes within five minutes. {dashboard.evidence.marketplace_insights_rows.toLocaleString()} Marketplace Insights observations cover {dashboard.evidence.marketplace_insights_keywords.toLocaleString()} keywords. {dashboard.evidence.versioned_scores.toLocaleString()} evidence-qualified scores are available.
          </p>
          {fallback && <p className="mt-1 text-[11px] text-accent-amber">The live account service could not be reached; these values are from the last published static release.</p>}
        </div>
      </div>
      <button type="button" className="btn-secondary shrink-0 text-[12px]" onClick={() => void onRefresh()} disabled={refreshing} aria-label="Refresh dashboard data now">
        <Icon name={refreshing ? 'loader' : 'refresh-cw'} size={14} className={refreshing ? 'animate-spin' : ''} />
        {refreshing ? 'Refreshing' : 'Refresh now'}
      </button>
    </div>
  )
}

function relativeAge(value: string): string {
  const elapsed = Date.now() - Date.parse(value)
  if (!Number.isFinite(elapsed) || elapsed < 0) return 'Updated just now'
  const minutes = Math.floor(elapsed / 60_000)
  if (minutes < 1) return 'Updated just now'
  if (minutes < 60) return `Updated ${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Updated ${hours}h ago`
  return `Updated ${Math.floor(hours / 24)}d ago`
}

function Chip({ val, label, sub, color }: { val: string; label: string; sub: string; color: 'indigo' | 'emerald' | 'amber' | 'violet' }) {
  const colors = { indigo: 'from-surface-800 to-surface-700/50 border-accent-blue/20', emerald: 'from-accent-green/20 to-accent-green/10 border-accent-green/20', amber: 'from-accent-amber/20 to-accent-amber/10 border-accent-amber/20', violet: 'from-accent-violet/20 to-accent-violet/10 border-accent-violet/20' }
  const textColors = { indigo: 'text-accent-blue', emerald: 'text-accent-green', amber: 'text-accent-amber', violet: 'text-accent-violet' }
  return (
    <div className={`min-w-0 bg-linear-to-b ${colors[color]} border rounded-lg px-4 py-2.5 shadow-[0_10px_24px_rgba(7,10,14,0.14)] sm:min-w-[98px] sm:shrink-0`}>
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
  if (rank === 1) return <span className="w-6 h-6 rounded-lg bg-accent-amber/15 text-accent-amber flex items-center justify-center text-[11px] font-extrabold border border-accent-amber/20 shrink-0">1</span>
  if (rank === 2) return <span className="w-6 h-6 rounded-lg bg-surface-200/10 text-surface-200 flex items-center justify-center text-[11px] font-extrabold border border-surface-200/15 shrink-0">2</span>
  if (rank === 3) return <span className="w-6 h-6 rounded-lg bg-amber-700/10 text-accent-amber-600 flex items-center justify-center text-[11px] font-extrabold border border-amber-700/15 shrink-0">3</span>
  return <span className="w-6 h-6 rounded-lg bg-transparent text-surface-400 flex items-center justify-center text-[11px] font-bold shrink-0">{rank}</span>
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

function numericScore(value: number | null | undefined): number {
  return Number.isFinite(value) ? Number(value) : -1
}

function normalizeDashboardOpportunities(reports?: ReportListItem[], keywordOpportunities?: Record<string, unknown>[]): DashboardOpportunity[] {
  const reportItems = (reports || []).map((report) => ({
    id: report.report_id,
    title: report.seed_keywords?.join(', ') || 'Unnamed',
    generatedAt: report.generated_at,
    opportunityScore: Number.isFinite(report.opportunity_score) ? Number(report.opportunity_score) : null,
  }))
  const source = keywordOpportunities?.length
    ? keywordOpportunities.map((keyword, index) => ({
      id: String(keyword.keyword || `keyword-${index}`),
      title: String(keyword.keyword || 'Unnamed'),
      generatedAt: typeof keyword.scanned_at === 'string' ? keyword.scanned_at : null,
      opportunityScore: firstScore(keyword.primary_score, keyword.opportunity_score, keyword.gap_score),
    }))
    : reportItems

  return source
    .sort((a, b) => numericScore(b.opportunityScore) - numericScore(a.opportunityScore))
    .slice(0, 8)
}

function firstScore(...values: unknown[]): number | null {
  for (const value of values) {
    if (value == null || value === '') continue
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
  }
  return null
}

function formatScore(value: number | null | undefined): string {
  return Number.isFinite(value) ? Number(value).toFixed(1) : 'TBD'
}

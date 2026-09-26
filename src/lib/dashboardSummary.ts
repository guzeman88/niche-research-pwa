import type { DashboardSummary, StatsResponse } from '../types/api'
import { accountRequest } from './accountApi'

interface StaticRelease {
  generated_at?: string
  commit?: string
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  try {
    return await accountRequest<DashboardSummary>('/dashboard/summary')
  } catch (liveFailure) {
    const [statsResponse, releaseResponse] = await Promise.all([
      fetch('/data/stats.json', { cache: 'no-store' }),
      fetch('/data/release.json', { cache: 'no-store' }),
    ])
    if (!statsResponse.ok) throw liveFailure
    const stats = await statsResponse.json() as StatsResponse
    const release = releaseResponse.ok ? await releaseResponse.json() as StaticRelease : {}
    return {
      schema_version: 1,
      snapshot_version: release.commit || 'static',
      generated_at: release.generated_at || new Date(0).toISOString(),
      data_status: 'degraded',
      input_fingerprint: release.commit || 'static-fallback',
      source_watermarks: {},
      duration_ms: 0,
      stats,
      evidence: {
        versioned_scores: 0,
        versioned_gaps: 0,
        marketplace_insights_rows: 0,
        marketplace_insights_keywords: 0,
        shop_stats_rows: 0,
      },
      providers: [],
      delivery: {
        mode: 'fallback',
        refresh_interval_seconds: 60,
        fallback_generated_at: release.generated_at,
        reason: liveFailure instanceof Error ? liveFailure.message : 'Live dashboard unavailable.',
      },
    }
  }
}

export function refreshDashboardSummary(): Promise<DashboardSummary> {
  return accountRequest<DashboardSummary>('/dashboard/refresh', {})
}

export function dashboardFreshness(generatedAt: string, now = Date.now()): 'fresh' | 'delayed' | 'stale' {
  const age = now - Date.parse(generatedAt)
  if (!Number.isFinite(age) || age > 15 * 60_000) return 'stale'
  if (age > 10 * 60_000) return 'delayed'
  return 'fresh'
}

import type {QueryClient} from '@tanstack/react-query'
import type { DashboardSummary, StatsResponse } from '../types/api'
import { accountRequest } from './accountApi'

interface StaticRelease {
  generated_at?: string
  commit?: string
  source_data_as_of?: string | null
}

export async function getDashboardSummary(context?:{client?:QueryClient;queryKey?:readonly unknown[]}): Promise<DashboardSummary> {
  try {
    return await accountRequest<DashboardSummary>('/dashboard/summary')
  } catch (liveFailure) {
    const previous=context?.queryKey?context.client?.getQueryData<DashboardSummary>(context.queryKey):undefined
    if(previous?.delivery.mode==='live')throw liveFailure // Keep the last atomic live result and its error visible.

    const [statsResponse, releaseResponse] = await Promise.all([
      fetch('/data/stats.json', { cache: 'no-store' }),
      fetch('/data/release.json', { cache: 'no-store' }),
    ])
    if (!statsResponse.ok) throw liveFailure
    const stats = await statsResponse.json() as StatsResponse
    const release = releaseResponse.ok ? await releaseResponse.json() as StaticRelease : {}
    return {
      schema_version: 1,
      scope: 'historical_static_release',
      snapshot_version: release.commit || 'static',
      generated_at: release.source_data_as_of || release.generated_at || new Date(0).toISOString(),
      data_status: 'degraded',
      input_fingerprint: release.commit || 'static-fallback',
      source_watermarks: {},
      duration_ms: 0,
      stats,
      evidence: {
        versioned_scores: null,
        versioned_gaps: null,
        marketplace_insights_rows: null,
        marketplace_insights_keywords: null,
        shop_stats_rows: null,
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

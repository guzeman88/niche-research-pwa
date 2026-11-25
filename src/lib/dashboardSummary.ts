import type {QueryClient} from '@tanstack/react-query'
import type { DashboardSummary, StatsResponse } from '../types/api'
import { accountRequest } from './accountApi'
import {readPublicResearchWithMetadata} from './publicResearch'

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

    const published=await readPublicResearchWithMetadata('stats.json')
    if(!published.data)throw liveFailure
    const stats=published.data as StatsResponse
    let release:StaticRelease={}
    if(!published.manifest){const response=await fetch('/data/release.json',{cache:'no-store'});if(response.ok)release=await response.json() as StaticRelease}
    const manifest=published.manifest
    const version=manifest?.id||release.commit||'static'
    const generated=manifest?.generated_at||release.generated_at
    return {
      schema_version: 1,
      scope: manifest?'local_research_projection':'historical_static_release',
      snapshot_version: version,
      generated_at: manifest?.source_data_as_of || release.source_data_as_of || generated || new Date(0).toISOString(),
      data_status: 'degraded',
      input_fingerprint: version,
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
        fallback_generated_at: generated,
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

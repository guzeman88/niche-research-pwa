/// <reference types="vite/client" />

import type {
  NicheReport, ReportListItem,
} from '../types/research'
import type {
  StatsResponse, HealthResponse, KeywordItem, AdapterStatus,
} from '../types/api'
import type { SchedulerStatus, SchedulerHistoryItem } from '../types/scheduler'
import type { GapReport } from '../types/gaps'

const BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '');

// Warm-up: ping backend immediately on load to wake it from Render cold start
let _warmPromise: Promise<boolean> | null = null;
export function warmUpBackend(): Promise<boolean> {
  if (_warmPromise) return _warmPromise;
  _warmPromise = new Promise((resolve) => {
    let attempts = 0;
    const tryPing = () => {
      fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(3000) })
        .then(r => r.ok ? resolve(true) : retry())
        .catch(() => retry());
    };
    const retry = () => {
      if (++attempts >= 15) { resolve(false); return; }
      setTimeout(tryPing, 2000);
    };
    tryPing();
  });
  return _warmPromise;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Cache-bust GET requests to bypass stale service worker cache
  const isGet = !options?.method || options.method === 'GET';
  const sep = path.includes('?') ? '&' : '?';
  const url = `${BASE_URL}${path}${isGet ? `${sep}_t=${Date.now()}` : ''}`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options,
    });
  } catch (err) {
    throw new Error(`Network error: backend unreachable at ${url}`);
  }
  const contentType = res.headers.get('content-type') || '';
  // If we got HTML instead of JSON, the backend is unreachable
  if (!res.ok || contentType.includes('text/html')) {
    throw new Error(contentType.includes('text/html')
      ? 'Backend offline — deploy the API to Render to enable research'
      : `${res.status}: ${(await res.text().catch(() => '')).slice(0, 200)}`);
  }
  if (contentType.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return res.text() as unknown as T;
}

// ── Research ────────────────────────────────────────────────────────────

export function runResearch(keywords: string[], storeSlug = '__global__', skipScraper = false): Promise<{ run_id: string; status: string }> {
  return request('/api/research/run', {
    method: 'POST',
    body: JSON.stringify({ keywords, store_slug: storeSlug, skip_scraper: skipScraper }),
  });
}

export function listReports(storeSlug = '__global__', limit = 50): Promise<ReportListItem[]> {
  return request(`/api/research/reports?store_slug=${storeSlug}&limit=${limit}`);
}

export function getReport(reportId: string): Promise<NicheReport> {
  return request(`/api/research/reports/${reportId}`);
}

export function getLatestReport(storeSlug = '__global__'): Promise<NicheReport> {
  return request(`/api/research/reports/latest?store_slug=${storeSlug}`);
}

// ── Keywords ────────────────────────────────────────────────────────────

export function listKeywords(domain?: string, limit = 2000): Promise<KeywordItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (domain) params.set('domain', domain);
  return request(`/api/keywords?${params}`);
}

export function searchKeywords(q: string, limit = 100): Promise<KeywordItem[]> {
  return request(`/api/keywords/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export function runDiscovery(opts?: Record<string, boolean | number>): Promise<{ total_added: number; sources_run: string[]; db_stats: Record<string, unknown> }> {
  return request('/api/keywords/discover', {
    method: 'POST',
    body: JSON.stringify(opts || {}),
  });
}

export function getOpportunities(domain?: string, limit = 100): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (domain) params.set('domain', domain);
  return request(`/api/keywords/opportunities?${params}`);
}

export function getBreakouts(limit = 20): Promise<{ keyword: string; breakout: boolean }[]> {
  return request(`/api/keywords/breakouts?limit=${limit}`);
}

export function getDomains(): Promise<string[]> {
  return request('/api/keywords/domains');
}

export function getKeywordCoverage(): Promise<Record<string, unknown>> {
  return request('/api/keywords/coverage');
}

// ── Gaps ────────────────────────────────────────────────────────────────

export function getTopGaps(limit = 100): Promise<GapReport[]> {
  return request(`/api/gaps?limit=${limit}`);
}

export function getGapReport(keyword: string): Promise<GapReport> {
  return request(`/api/gaps/${encodeURIComponent(keyword)}`);
}

// ── Scheduler ───────────────────────────────────────────────────────────

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return request('/api/scheduler/status');
}

export function startScheduler(mode = 'continuous', batchSize = 5): Promise<Record<string, unknown>> {
  return request('/api/scheduler/start', {
    method: 'POST',
    body: JSON.stringify({ mode, batch_size: batchSize }),
  });
}

export function stopScheduler(): Promise<Record<string, unknown>> {
  return request('/api/scheduler/stop', { method: 'POST' });
}

export function pauseScheduler(): Promise<Record<string, unknown>> {
  return request('/api/scheduler/pause', { method: 'POST' });
}

export function resumeScheduler(): Promise<Record<string, unknown>> {
  return request('/api/scheduler/resume', { method: 'POST' });
}

export function getSchedulerHistory(limit = 20): Promise<SchedulerHistoryItem[]> {
  return request(`/api/scheduler/history?limit=${limit}`);
}

// ── Stats ───────────────────────────────────────────────────────────────

export function getStats(): Promise<StatsResponse> {
  return request('/api/stats');
}

export function getHealth(): Promise<HealthResponse> {
  return request('/api/stats/health');
}

// ── Settings ────────────────────────────────────────────────────────────

export function getSettings(): Promise<{ settings: Record<string, unknown>; guidelines: Record<string, unknown> }> {
  return request('/api/settings');
}

export function updateSettings(data: { settings?: Record<string, unknown>; guidelines?: Record<string, unknown> }): Promise<Record<string, unknown>> {
  return request('/api/settings', { method: 'PUT', body: JSON.stringify(data) });
}

export function getAdapterStatus(): Promise<AdapterStatus> {
  return request('/api/settings/adapters');
}

// ── Export ──────────────────────────────────────────────────────────────

export function getExportCsvUrl(domain?: string, sortBy = 'gap_score'): string {
  const params = new URLSearchParams({ sort_by: sortBy });
  if (domain) params.set('domain', domain);
  return `${BASE_URL}/api/export/csv?${params}`;
}

export function getExportJsonUrl(includeRaw = false): string {
  return `${BASE_URL}/api/export/json?include_raw=${includeRaw}`;
}

/// <reference types="vite/client" />

import type {
  NicheReport, ReportListItem,
} from '../types/research'
import type {
  StatsResponse, HealthResponse, KeywordItem, AdapterStatus,
} from '../types/api'
import type { SchedulerStatus, SchedulerHistoryItem } from '../types/scheduler'
import type { GapReport } from '../types/gaps'
import type { StoreIdea } from './storeIdeas'

const BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || 'https://niche-research-api-kqlt.onrender.com');
const USE_STATIC_DATA = !import.meta.env.DEV && import.meta.env.VITE_ALLOW_STATIC_DATA !== '0';
let lastBackendWake = 0;

// Static CDN data paths — instant, no backend needed for reads
const STATIC_MAP: Record<string, string> = {
  '/api/stats': '/data/stats.json',
  '/api/keywords/opportunities': '/data/opportunities.json',
  '/api/store-ideas/profitable': '/data/store-ideas.json',
  '/api/gaps': '/data/gaps.json',
  '/api/keywords': '/data/keywords.json',
  '/api/research/reports': '/data/reports.json',
  '/api/keywords/breakouts': '/data/breakouts.json',
};

// Try loading from static CDN JSON first (instant), fall back to API
async function fetchStatic(path: string): Promise<any | null> {
  if (!USE_STATIC_DATA) return null;
  const staticPath = STATIC_MAP[path] || (path.startsWith('/api/keywords?') ? '/data/keywords.json' : null);
  if (!staticPath) return null;
  try {
    const res = await fetch(staticPath);
    if (res.ok) return res.json();
  } catch {
    // Static data is an optional fast path; callers fall back to the API.
  }
  return null;
}

function wakeBackend() {
  if (!BASE_URL) return;
  const now = Date.now();
  if (now - lastBackendWake < 60_000) return;
  lastBackendWake = now;
  fetch(`${BASE_URL}/api/health?_t=${now}`, {
    headers: { 'Content-Type': 'application/json' },
  }).catch(() => {});
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isGet = !options?.method || options.method === 'GET';

  // Try live backend API first — returns fresh data on pull-to-refresh
  const sep = path.includes('?') ? '&' : '?';
  const url = `${BASE_URL}${path}${isGet ? `${sep}_t=${Date.now()}` : ''}`;

  if (isGet) {
    const staticData = await fetchStatic(path.split('?')[0]);
    if (staticData) {
      wakeBackend();
      return staticData as T;
    }

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) {
        const ct = res.headers.get('content-type') || '';
        if (ct.includes('application/json')) return res.json() as Promise<T>;
      }
    } catch {
      // Backend unreachable — fall back to static CDN
      if (!import.meta.env.DEV) {
        const staticData = await fetchStatic(path.split('?')[0]);
        if (staticData) return staticData as T;
      }
    }
  }

  // POST requests or backend-down fallback: use static CDN
  if (isGet && !import.meta.env.DEV) {
    const staticData = await fetchStatic(path.split('?')[0]);
    if (staticData) return staticData as T;
  }
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options,
    });
  } catch (err) {
    const error = new Error(`Network error: backend unreachable at ${url}`) as Error & { cause?: unknown };
    error.cause = err;
    throw error;
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

// ── Store Ideas ─────────────────────────────────────────────────────────

export function getProfitableStoreIdeas(limit = 12): Promise<StoreIdea[]> {
  return request(`/api/store-ideas/profitable?limit=${limit}`);
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

// ── Stores ─────────────────────────────────────────────────────────────

export interface StoreItem {
  slug: string; name: string; niche: string; niche_secondary: string[];
  target_audience: string; product_types: string[]; active: boolean;
  created_at: string; listing_target: number;
  brand_voice: string; aesthetic: string; pricing_strategy: string;
  research_snapshot?: Record<string, unknown>;
}

export interface CreateStorePayload {
  name: string;
  niche: string;
  niche_secondary?: string[];
  target_audience?: string;
  product_types?: string[];
  brand_voice?: string;
  aesthetic?: string;
  pricing_strategy?: string;
  listing_target?: number;
  research_snapshot?: Record<string, unknown>;
}

const SAMPLE_STORE_SLUGS = new Set([
  'botanical-bliss-prints',
  'dark-academia-decor',
  'minimalist-morning',
  'nurse-humor-gifts',
  'retro-wave-tees',
])

const SAMPLE_STORE_NAMES = new Set([
  'botanical bliss prints',
  'dark academia decor',
  'minimalist morning',
  'nurse humor gifts',
  'retro wave tees',
])

function isSampleStore(store: StoreItem): boolean {
  return SAMPLE_STORE_SLUGS.has((store.slug || '').toLowerCase())
    || SAMPLE_STORE_NAMES.has((store.name || '').toLowerCase())
}

export async function getStores(): Promise<StoreItem[]> {
  const stores = await request<StoreItem[]>('/api/stores');
  return stores.filter(store => !isSampleStore(store));
}

export function createStore(payload: CreateStorePayload): Promise<StoreItem> {
  return request('/api/stores', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
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

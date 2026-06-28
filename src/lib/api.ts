/// <reference types="vite/client" />

import type {
  NicheReport, ReportListItem,
} from '../types/research'
import type {
  StatsResponse, HealthResponse, KeywordItem,
} from '../types/api'
import type { GapReport } from '../types/gaps'
import type { StoreIdea } from './storeIdeas'

const PRIMARY_API_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '');
const BACKUP_API_URLS = import.meta.env.DEV
  ? []
  : parseApiUrls(import.meta.env.VITE_BACKUP_API_URLS || import.meta.env.VITE_BACKUP_API_URL || '');
const API_URLS = [PRIMARY_API_URL, ...BACKUP_API_URLS]
  .map((url) => url.trim().replace(/\/+$/, ''))
  .filter(Boolean);
const BASE_URL = API_URLS[0] || '';
const USE_STATIC_DATA = !import.meta.env.DEV && import.meta.env.VITE_ALLOW_STATIC_DATA !== '0';
const WAKE_BACKEND = import.meta.env.VITE_WAKE_BACKEND === '1';
let lastBackendWake = 0;

function parseApiUrls(value: string): string[] {
  return value
    .split(',')
    .map((url) => url.trim())
    .filter(Boolean);
}

// Static CDN data paths — instant, no backend needed for reads
const STATIC_MAP: Record<string, string> = {
  '/api/stats': '/data/stats.json',
  '/api/keywords/opportunities': '/data/opportunities.json',
  '/api/store-ideas/profitable': '/data/store-ideas.json',
  '/api/gaps': '/data/gaps.json',
  '/api/keywords': '/data/keywords.json',
  '/api/keywords/domains': '/data/keywords.json',
  '/api/research/reports': '/data/reports.json',
  '/api/keywords/breakouts': '/data/breakouts.json',
};

const LIVE_ONLY_GET_PATHS = new Set<string>();

// Try loading from static CDN JSON first (instant), fall back to API
async function fetchStatic(path: string): Promise<any | null> {
  if (!USE_STATIC_DATA) return null;
  const staticPath = STATIC_MAP[path] || (path.startsWith('/api/keywords?') ? '/data/keywords.json' : null);
  if (!staticPath) return null;
  try {
    const sep = staticPath.includes('?') ? '&' : '?';
    const res = await fetch(`${staticPath}${sep}_t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    const data = await res.json();
    if (path === '/api/keywords/domains' && Array.isArray(data)) {
      return Array.from(new Set(data.map((kw) => kw.domain).filter(Boolean))).sort();
    }
    return data;
  } catch {
    // Static data is an optional fast path; callers fall back to the API.
  }
  return null;
}

function wakeBackend() {
  if (!API_URLS.length || !WAKE_BACKEND) return;
  const now = Date.now();
  if (now - lastBackendWake < 60_000) return;
  lastBackendWake = now;
  for (const baseUrl of API_URLS) {
    fetch(`${baseUrl}/api/stats/health?_t=${now}`, { mode: 'no-cors' }).catch(() => {});
  }
}

function apiCandidates(): string[] {
  if (API_URLS.length > 0) return API_URLS;
  return import.meta.env.DEV ? [''] : [];
}

function tunnelBypassHeaders(baseUrl: string): Record<string, string> {
  try {
    return new URL(baseUrl).hostname.endsWith('.loca.lt')
      ? { 'bypass-tunnel-reminder': 'true' }
      : {};
  } catch {
    return {};
  }
}

async function fetchApi(path: string, options?: RequestInit, timeoutMs = 8000): Promise<Response | null> {
  const isGet = !options?.method || options.method === 'GET';
  const sep = path.includes('?') ? '&' : '?';
  for (const baseUrl of apiCandidates()) {
    const url = `${baseUrl}${path}${isGet ? `${sep}_t=${Date.now()}` : ''}`;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...tunnelBypassHeaders(baseUrl), ...options?.headers },
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (res.ok) return res;
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('text/html')) return res;
    } catch {
      // Try the next configured API before falling back to static data.
    }
  }
  return null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isGet = !options?.method || options.method === 'GET';
  const pathOnly = path.split('?')[0];
  const liveOnly = isGet && LIVE_ONLY_GET_PATHS.has(pathOnly);

  // Prefer live APIs in configured order: local-machine tunnel first, then backups
  // such as Render. Static snapshots are only the final read fallback.
  if (isGet) {
    const res = await fetchApi(path, options);
    if (res?.ok) {
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) return res.json() as Promise<T>;
    }

    // Backend unreachable or returned non-JSON HTML — fall back to static CDN.
    if (!liveOnly && !import.meta.env.DEV) {
      const staticData = await fetchStatic(pathOnly);
      if (staticData) {
        wakeBackend();
        return staticData as T;
      }
    }
  }

  // POST requests or backend-down fallback: use static CDN
  if (isGet && !liveOnly && !import.meta.env.DEV) {
    const staticData = await fetchStatic(pathOnly);
    if (staticData) return staticData as T;
  }
  const res = await fetchApi(path, options, path === '/api/designs/generate' ? 140000 : 8000);
  if (!res) {
    throw new Error(`Network error: backend unreachable for ${path}`);
  }
  const contentType = res.headers.get('content-type') || '';
  // If we got HTML instead of JSON, the backend is unreachable
  if (!res.ok || contentType.includes('text/html')) {
    throw new Error(contentType.includes('text/html')
      ? 'Backend offline - live research actions are unavailable'
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

// Design Providers

export interface DesignProviderInfo {
  id: string;
  label: string;
  configured: boolean;
  available: boolean;
  status: 'ready' | 'needs_key' | 'manual' | 'unsupported' | 'billing_locked';
  detail: string;
  env_vars: string[];
}

export interface GeneratedDesignAsset {
  provider: string;
  title: string;
  prompt: string;
  asset_url: string;
  content_type: string;
  type: 'image';
  meta: Record<string, unknown>;
}

export function getDesignProviders(): Promise<DesignProviderInfo[]> {
  return request('/api/designs/providers');
}

export function generateDesignAsset(payload: {
  provider: string;
  prompt: string;
  product_type?: string;
  aspect_ratio?: string;
}): Promise<GeneratedDesignAsset> {
  return request('/api/designs/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ── Stats ───────────────────────────────────────────────────────────────

export function getStats(): Promise<StatsResponse> {
  return request('/api/stats');
}

export function getHealth(): Promise<HealthResponse> {
  return request('/api/stats/health');
}

export function hasConfiguredBackend(): boolean {
  return import.meta.env.DEV || API_URLS.length > 0;
}

export function ensureScannerRunning(): Promise<Record<string, unknown>> {
  return request('/api/scheduler/start', {
    method: 'POST',
    body: JSON.stringify({ mode: 'performance', batch_size: 5 }),
  });
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

const LOCAL_STORES_KEY = 'niche-research-pwa:stores:v1'

function isSampleStore(store: StoreItem): boolean {
  return SAMPLE_STORE_SLUGS.has((store.slug || '').toLowerCase())
    || SAMPLE_STORE_NAMES.has((store.name || '').toLowerCase())
}

function hasBrowserStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function readLocalStores(): StoreItem[] {
  if (!hasBrowserStorage()) return []
  try {
    const raw = window.localStorage.getItem(LOCAL_STORES_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isValidStore) : []
  } catch {
    return []
  }
}

function writeLocalStores(stores: StoreItem[]): void {
  if (!hasBrowserStorage()) return
  window.localStorage.setItem(LOCAL_STORES_KEY, JSON.stringify(stores.filter(isValidStore)))
}

function isValidStore(store: unknown): store is StoreItem {
  if (!store || typeof store !== 'object') return false
  const item = store as Partial<StoreItem>
  return typeof item.slug === 'string' && typeof item.name === 'string' && typeof item.niche === 'string'
}

function slugifyStoreName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
    .replace(/-+$/g, '') || 'store'
}

function storeFromPayload(payload: CreateStorePayload, existing: StoreItem[] = []): StoreItem {
  const existingSlugs = new Set(existing.map(store => store.slug))
  const baseSlug = slugifyStoreName(payload.name)
  let slug = baseSlug
  let suffix = 2
  while (existingSlugs.has(slug)) {
    slug = `${baseSlug.slice(0, 56).replace(/-+$/g, '')}-${suffix}`
    suffix += 1
  }

  return {
    slug,
    name: payload.name.trim(),
    niche: payload.niche.trim(),
    niche_secondary: payload.niche_secondary || [],
    target_audience: payload.target_audience || '',
    product_types: payload.product_types?.length ? payload.product_types : ['digital_download'],
    active: true,
    created_at: new Date().toISOString(),
    listing_target: payload.listing_target || 50,
    brand_voice: payload.brand_voice || '',
    aesthetic: payload.aesthetic || '',
    pricing_strategy: payload.pricing_strategy || 'competitive',
    research_snapshot: {
      ...(payload.research_snapshot || {}),
      saved_offline: true,
    },
  }
}

function mergeStores(serverStores: StoreItem[], localStores: StoreItem[]): StoreItem[] {
  const bySlug = new Map<string, StoreItem>()
  for (const store of [...serverStores, ...localStores]) {
    if (!isValidStore(store) || isSampleStore(store)) continue
    bySlug.set(store.slug, store)
  }
  return Array.from(bySlug.values()).sort((a, b) => {
    const aTime = Date.parse(a.created_at || '')
    const bTime = Date.parse(b.created_at || '')
    return (Number.isFinite(bTime) ? bTime : 0) - (Number.isFinite(aTime) ? aTime : 0)
  })
}

function saveLocalStore(store: StoreItem): StoreItem {
  const stores = readLocalStores()
  const next = mergeStores([], [store, ...stores])
  writeLocalStores(next)
  return store
}

export async function getStores(): Promise<StoreItem[]> {
  const localStores = readLocalStores()
  try {
    const stores = await request<StoreItem[]>('/api/stores')
    return mergeStores(stores, localStores)
  } catch {
    return mergeStores([], localStores)
  }
}

export async function createStore(payload: CreateStorePayload): Promise<StoreItem> {
  try {
    const store = await request<StoreItem>('/api/stores', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    saveLocalStore(store)
    return store
  } catch {
    return saveLocalStore(storeFromPayload(payload, readLocalStores()))
  }
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

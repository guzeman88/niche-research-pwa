import { operatorRequest } from './operatorConnection'

export const sellingRequest = <T,>(path = '', body?: unknown) => operatorRequest<T>(`/api/selling-products${path}`, body)
export const families = ['planner', 'worksheet', 'wall_art', 'mug', 'apparel', 'other']
export const sources = ['manual', 'etsy_public', 'everbee', 'alura', 'erank', 'ehunt', 'seller_records', 'etsy_marketplace_insights', 'google_ads', 'other']
export const metrics = ['estimated_sales', 'seller_reported_sales', 'purchase_message', 'reviews', 'shop_reviews', 'views', 'favorites', 'shop_sales', 'carts', 'stock', 'price', 'keyword_searches', 'listing_count']
export const text = (value: string) => value.replace(/_/g, ' ')
export const number = (value: number | null | undefined) => value == null ? 'Unknown' : value.toLocaleString(undefined, { maximumFractionDigits: 2 })
export const localDay = (value = new Date()) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
export const localTime = () => `${localDay()}T${String(new Date().getHours()).padStart(2, '0')}:${String(new Date().getMinutes()).padStart(2, '0')}`
export const values = (form: HTMLFormElement) => Object.fromEntries(new FormData(form).entries()) as Record<string, string>
export function download(name: string, value: unknown, csv = false) {
  const blob = new Blob([csv ? String(value) : JSON.stringify(value, null, 2)], { type: csv ? 'text/csv;charset=utf-8' : 'application/json' })
  const url = URL.createObjectURL(blob), link = document.createElement('a')
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface Listing { listing_id: string; title: string; shop: string; url: string; tags: string[]; created_on: string | null; source: string; source_ref: string }
export interface Observation {
  listing_id: string; metric: string; value: number | null; basis: string; observed_at: string
  period_start: string | null; period_end: string | null; currency: string; keyword: string; geography: string
  source: string; source_ref: string; note: string
}
export interface Review { listing_id: string; review_id: string; rating: number; reviewed_on: string; text: string; source_ref: string }
export interface Pattern { listing_id: string; typography: string; layout: string; palette: string; features: string[]; readability: number | null; notes: string; source_ref: string; title?: string }
export interface CalibrationCase { case_id: string; listing_id: string; period_start: string; period_end: string; actual_purchases: number; source_ref: string; note: string }
export interface Packet { listings: Listing[]; observations: Observation[]; reviews: Review[]; patterns: Pattern[]; calibration?: CalibrationCase[]; schema_version?: number }
export interface Preview { added: number; changed: number; duplicates: number; total: number; fingerprint: string; packet: Packet }
export interface Brief { name: string; buyer: string; purpose: string; improvements: string[]; original_direction: string; family: string; notes: string; stale?: boolean }
export interface Summary { id: string; name: string; keyword: string; family: string; audience: string; stage: string; fingerprint: string; pending_sync: number; evidence_level: string; listing_count: number; selling_shops: number; has_brief: boolean; brief_stale: boolean }
export interface Theme { positive: number; concerns: number; independent_listings: number; independent_shops: number; review_ids: string[]; suggestion: string; repeated: boolean; scope: string }
export interface Momentum { listing_id: string; metric: string; source: string; basis: string; from: string; to: string; before: number; after: number; change: number | null; status: string; overlapping_windows: boolean; currency: string; scope: string }
export interface Analysis {
  sales_model: SalesModel
  evidence_level: string; listing_count: number; review_count: number; independent_selling_shops: number; recent_sales_listing_count: number
  improvement_suggestions: string[]; limitations: string[]; conflicts: Array<{listing_id: string; metric: string; source: string; status: string}>
  methods: {
    bestsellers: { status: string; recent: Observation[]; historical: Observation[] }
    momentum: { status: string; series: Momentum[] }
    reviews: { status: string; themes: Record<string, Theme>; recent_listing_count: number }
    keywords: { status: string; terms: Array<{ keyword: string; listings: number; shops: number; measurements: Observation[] }>; demand: Observation[] }
    patterns: { status: string; matrix: Pattern[]; features: Record<string, number> }
  }
}
export interface Detail { id: string; name: string; keyword: string; family: string; audience: string; buyer_task: string; notes: string; stage: string; fingerprint: string; evidence_fingerprint: string; evidence: Packet; analysis: Analysis; brief: Brief | null; record_count: number; revision_count: number; pending_sync: number }
export interface Overview { items: Summary[]; external_collection: boolean; data_access: string }

export interface SalesConfig {
  purchases_per_buyer: number | null; review_rate: number | null; view_conversion: number | null; baseline_daily: number | null
  review_delay_min: number; review_delay_max: number; seasonality: number[]; assumptions_note: string
}
export interface SalesWindow { days: number; estimate: number | null; low: number | null; high: number | null; supported_days: number; coverage_days: number; extrapolated_days: number; methods: string[]; status: string }
export interface SalesModel {
  version: string; as_of: string; status: string; config: SalesConfig; limits: string[]; factors: string[]
  opportunity: { score: number | null; components: Record<string, number | null>; missing: string[]; scope: string }
  trained_model: { present: boolean; active: boolean; stale: boolean; artifact_id: string | null; validation: { training_cases: number; test_cases: number; test_shops: number; mae_daily: number; baseline_mae_daily: number; beats_baseline: boolean; cutoff: string } | null }
  listings: Array<{ listing_id: string; title: string; shop: string; windows: Record<string, SalesWindow>; issues: string[]; review_rate: number | null; review_rate_basis: string
    purchase_evidence: Array<{ value: number; unit: string; precision: string; raw_message: string; window_start: string; window_end: string; source_ref: string }>
    shop_changes: Array<{ start: string; end: string; net_change: number }>; shop_checks: Array<{ status: string }> }>
}

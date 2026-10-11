import { operatorRequest } from './operatorConnection'

export const COST_FIELDS = ['production', 'shipping', 'packaging', 'fees', 'advertising', 'refunds', 'labor'] as const
export const COST_LABELS: Record<string, string> = {production: 'Production', shipping: 'Shipping', packaging: 'Packaging', fees: 'Marketplace and payment fees', advertising: 'Advertising', refunds: 'Refund allowance', labor: 'Variable labor', setup: 'Design and setup', fixed_monthly: 'Monthly fixed expenses', price: 'Sale price'}
export interface ValidationRecord {id: string; kind: string; fingerprint: string; payload: Record<string, unknown>; sync_status: string}
export interface Scenario {price: number; contribution_per_order: number | null; first_month_break_even_orders: number | null; missing: string[]}
export interface ValidationProject {
  id: string; name: string; product_type: string; keywords: string[]; status: string; sync_pending: number
  queue: Array<{keyword: string; status: string; sample_count: number; distinct_sample_shops: number; blockers: string[]; market: {searches: number; listings: number; period_start: string; period_end: string} | null}>
  economics: Record<string, Scenario> | null; economics_currency: string | null
  outcomes: {status: string; periods: number; contribution: number | null; net_profit: number | null; currencies: string[]; revenue: number | null; orders: number | null; visits: number | null; conversion_pct: number | null}
  records: ValidationRecord[]; input_fingerprint: string; model_version: string
}
export interface ValidationOverview {projects: ValidationProject[]; pending_sync: number; model_version: string}
export const validationRequest = <T,>(path = '', body?: unknown) => operatorRequest<T>(`/api/product-validation${path}`, body)
export function values(form: HTMLFormElement): Record<string, string> {
  return Object.fromEntries([...new FormData(form).entries()].map(([key, value]) => [key, String(value)]))
}
export function download(name: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], {type}))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export const label = (text: string) => text.replace(/_/g, ' ')
export const display = (value: number | null | undefined) => value == null ? 'Unknown' : value.toLocaleString(undefined, {maximumFractionDigits: 2})

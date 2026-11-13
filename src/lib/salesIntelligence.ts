import {operatorRequest} from './operatorConnection'

export const intelligenceRequest = <T,>(path = '', body?: unknown) => operatorRequest<T>(`/api/sales-intelligence${path}`, body)
export interface ShopAllocationWindow {start: string; end: string; days: number; counter_delta: number}
export interface ShopAllocationProduct {listing_id: string; title?: string; value: number | null; low: number | null; high: number | null; feasible_low?: number | null; feasible_high?: number | null; status: string; issues?: string[]; window?: ShopAllocationWindow | null}
export interface ShopAllocationReport {
  shop_id: string; shop?: string; shop_label?: string; status: string; as_of?: string;
  window?: ShopAllocationWindow | null;
  products: ShopAllocationProduct[];
  unobserved?: {value: number | null; low: number | null; high: number | null};
  issues?: string[]; assumptions?: string[] | string; validation?: string; catalog_complete?: boolean;
  priority?: Array<{listing_id: string; reason: string; score?: number}>;
}
export interface ShopAllocationOverview {
  status?: string; summary?: {at?: string; tracked?: number; shops?: number; anchored_shops?: number; allocated_products?: number; unknown_products?: number};
  shops: ShopAllocationReport[]; assumptions?: string[] | string; schedule?: string;
  validation?: {status: string; matched_cases?: number; mae?: number | null; within_5_percent?: number | null};
}
export interface AutomaticEstimate {listing_id: string; status: string; value: number | null; captured_at?: string; listing?: {title: string; shop: string}; collection?: {title: string; shop: string; check_status: string}; review_evidence?: {complete: boolean; observed_reviews: number}; review_scenarios?: Record<string, {value: number | null; low: number | null; high: number | null; review_count: number}>; shop_allocation?: ShopAllocationProduct | null}
export interface ReferenceComparison {automatic_estimate?: AutomaticEstimate; shop_allocation?: ShopAllocationProduct | null}
export interface ReferenceSource {id: string; name: string; disposition: string; group: string; reason: string; url: string; reviewed_on: string; paused: boolean; automation: string; capabilities: Record<string, boolean>; access_review_at: string | null; health: {status: string; retry_at?: string; last_success?: string; last_failure?: string}; allowance: {remaining: number; used: number; limit: number; period: string; next_reset: string | null} | null}
export interface ReferenceReading {id: string; listing_id: string; source_id: string; value: number | null; unit: string; basis: string; captured_at: string; available_at: string; period_start: string | null; period_end: string | null; source_ref: string; status: string; precision: string}
export interface ReferenceCohort {fingerprint: string; center: number; mean: number; median: number; minimum: number; maximum: number; source_count: number; group_count: number; unit: string; basis: string; period_start: string | null; period_end: string | null; status: string; readings: ReferenceReading[]}
export interface ReferenceListing {listing_id: string; title: string; shop: string; captured_at: string; price: number | null; currency: string}
export interface ReferenceOverview {items: ReferenceListing[]; total: number; page: number; limit: number; source_count: number; automated_provider_feeds: number; coverage: {observations: number; reference_listings: number; listings: number; outcomes: number; models: number; paused: boolean; worker: {status: string}; catalog: {status?: string}}}
export interface ReferenceComparison {listing_id: string; metadata: ReferenceListing | null; history: ReferenceReading[]; consensus: {cohorts: ReferenceCohort[]; excluded: Array<{id: string; source_id: string; reason: string}>}; student: {status: string; value: number | null; unit?: string; days?: number}; outcome_model: {status: string; value: number | null; unit?: string; days?: number}; independent_model: {status: string; value: number | null; days?: number; unit?: string}}
export interface ResearchJob {id: string; source_id: string; status: string; due_at: string; attempts: number; result: {status?: string; reason?: string; error?: string; cases?: number; shops?: number} | null}
export interface ReferenceModel {id: string; status: string; active: boolean; eligible: boolean; created_at: string; actual_evaluation: {status: string; cases: number; shops: number; mae: number | null; baseline_mae: number | null} | null; model: {lane: string; days: number; unit: string; training_cases: number; evaluation: {mae: number; baseline_mae: number; cases: number; shops: number}}}
export interface ImportPreview {fingerprint: string; accepted: number; rejected: Array<{row: number; reason: string}>; can_commit: boolean; blocker: string | null; sample: ReferenceReading[]}

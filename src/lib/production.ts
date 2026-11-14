import { operatorRequest, operatorFetch } from './operatorConnection'
import type { StoreProductIdea } from './storeWorkspace'
import { accountStorage } from './accountWorkspace'

export interface CostPlan {
  country:'US'; currency:'USD'; fee_schedule_id:'etsy-us-2026-11-13'
  support_contact_fraction:number; support_minutes_per_contact:number; hourly_labor_usd:number
  refund_revenue_fraction:number; offsite_fee_fraction:0|0.12|0.15
  buyer_tax_usd:number; tax_on_seller_fees_usd:number; other_variable_usd:number; assumptions_note:string
}
export interface CostSummary {
  selling_price:number
  total_variable_cost:number; contribution:number; platform_fees:number; support_labor:number
  refund_allowance:number; offsite_fee:number; assumptions:CostPlan; assumptions_note:string
  fee_schedule_id:string; fee_sources:string[]; actual_cost_verified:false
}

export interface ProductionSpec {
  name: string; keyword: string; buyer: string; purpose: string; family: string; content: string[]
  size: string; palette: string; layout: string; personalization: string; price: number | null; unit_cost: number | null
  delivery: string; materials: string; category_id: number | null; rights_note: string; tags: string[]
  supporting_keywords: string[]; provider: Record<string, unknown>; research: Record<string, unknown>
  artwork_id: string | null; concept_method: string; artwork_method: string; image_profile: string; schema_version?: number
  delivery_kind?: 'instant_download' | 'made_to_order_digital' | 'physical'
  product_data?: Record<string, unknown>; creative_note?: string; instructions?: string; compatibility?: string[]
  cost_plan?: CostPlan|null
}
export const productFamilies = ['planner', 'worksheet', 'wall_art', 'mug', 'apparel', 'birthday_magazine', 'birthday_newspaper', 'memory_book', 'party_set', 'wedding_workbook', 'wedding_binder', 'bundle', 'tote', 'pet_portrait', 'crochet_pattern']
export const physicalProduct = (spec: Pick<ProductionSpec, 'family' | 'delivery_kind'>) => spec.delivery_kind ? spec.delivery_kind === 'physical' : ['mug', 'apparel', 'tote'].includes(spec.family)
export interface RendererCapability {family: string; label?: string; implemented?: boolean; outputs?: string[]; prerequisite?: string; prerequisites?: string[]; [key: string]: unknown}
export interface LaunchRecipe {id: string; name: string; collection: string; spec: ProductionSpec}
export interface ProductionJob {
  id: string; product_id: string; revision: string; status: string; error: string | null; spec: ProductionSpec
  history: Array<{action: string; created_at: string}>
  steps?: Array<{stage?: string; step?: string; name?: string; status: string; attempt?: number}>
  result: null | {
    listing_images?: string[]
    manifest?: {artifact_fingerprint: string; files: Array<{name: string; bytes: number; role?: string}>; render: {preview_kind: string; previews?: string[]; customer_files?: string[]}}
    quality?: {status: string; checks: Array<{check: string; passed: boolean | null}>; manufacturing: string}
    listing?: {title: string; description: string; tags: string[]; blockers: string[]; demand_status: string;cost_basis?:string;cost_summary?:CostSummary|null}
    concepts?: {concepts: Array<{name: string; purpose: string; content: string[]; composition: string; differentiation: string}>}
  }
}
export interface ProductionOverview {
  engine: string; paused: boolean; jobs: ProductionJob[]
  capabilities: Record<string, {status?: string; models?: string[]} | boolean>
  models: {text: string; embedding: string; vision: string}
  profiles: Array<{id: string; enabled: boolean; spec: ProductionSpec}>
  renderer_capabilities?: RendererCapability[]
}
export const productionRequest = <T,>(path = '', body?: unknown) => operatorRequest<T>(`/api/production${path}`, body)

export async function artifactBlob(job: string, name: string) {
  const response = await operatorFetch(`/api/production/jobs/${encodeURIComponent(job)}/files/${encodeURIComponent(name)}`)
  if (!response.ok) throw new Error('This artifact is unavailable or failed integrity verification.')
  return response.blob()
}
export async function downloadArtifact(job: string, name: string) {
  const blob = await artifactBlob(job, name); const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const INTAKES = 'etgen:production-review-intakes'
export function preserveProductionIntake(product: StoreProductIdea) {
  const existing = JSON.parse(accountStorage.getItem(INTAKES) || '{}') as Record<string, StoreProductIdea>
  const context = {...product}; delete context.approvedDesign
  // Source artwork remains in its original account workspace, avoiding quota-sized copies.
  existing[`${product.storeSlug}:${product.id}`] = context
  accountStorage.setItem(INTAKES, JSON.stringify(existing))
}
export function productionIntakes(): StoreProductIdea[] {
  try {return Object.values(JSON.parse(accountStorage.getItem(INTAKES) || '{}'))} catch {return []}
}
export function intakeSpec(product: StoreProductIdea): ProductionSpec {
  return {name: product.title, keyword: product.keyword, buyer: product.targetBuyer, purpose: '',
    family: ['mug', 'apparel', 'wall_art'].includes(product.productType) ? product.productType : '',
    content: [], size: product.productType === 'wall_art' ? '8x10' : 'letter', palette: 'ink', layout: 'classic',
    personalization: '', price: null, unit_cost: null, delivery: '', materials: '', category_id: null,
    rights_note: '', tags: [], supporting_keywords: product.supportingKeywords, provider: {}, research: {},
    artwork_id: null, concept_method: 'authored', artwork_method: 'template', image_profile: ''}
}

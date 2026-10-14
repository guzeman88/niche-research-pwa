import { operatorRequest, operatorHeaders, readConnection } from './operatorConnection'
import type { StoreProductIdea } from './storeWorkspace'
import { accountStorage } from './accountWorkspace'

export interface ProductionSpec {
  name: string; keyword: string; buyer: string; purpose: string; family: string; content: string[]
  size: string; palette: string; layout: string; personalization: string; price: number | null; unit_cost: number | null
  delivery: string; materials: string; category_id: number | null; rights_note: string; tags: string[]
  supporting_keywords: string[]; provider: Record<string, unknown>; research: Record<string, unknown>
  artwork_id: string | null; concept_method: string; artwork_method: string; image_profile: string; schema_version?: number
}
export interface ProductionJob {
  id: string; product_id: string; revision: string; status: string; error: string | null; spec: ProductionSpec
  history: Array<{action: string; created_at: string}>
  result: null | {
    manifest?: {artifact_fingerprint: string; files: Array<{name: string; bytes: number}>; render: {preview_kind: string}}
    quality?: {status: string; checks: Array<{check: string; passed: boolean}>; manufacturing: string}
    listing?: {title: string; description: string; tags: string[]; blockers: string[]; demand_status: string}
    concepts?: {concepts: Array<{name: string; purpose: string; content: string[]; composition: string; differentiation: string}>}
  }
}
export interface ProductionOverview {
  engine: string; paused: boolean; jobs: ProductionJob[]
  capabilities: Record<string, {status?: string; models?: string[]} | boolean>
  models: {text: string; embedding: string; vision: string}
  profiles: Array<{id: string; enabled: boolean; spec: ProductionSpec}>
}
export const productionRequest = <T,>(path = '', body?: unknown) => operatorRequest<T>(`/api/production${path}`, body)

export async function artifactBlob(job: string, name: string) {
  const {url} = readConnection()
  const response = await fetch(`${url}/api/production/jobs/${encodeURIComponent(job)}/files/${encodeURIComponent(name)}`, {headers: operatorHeaders(url)})
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

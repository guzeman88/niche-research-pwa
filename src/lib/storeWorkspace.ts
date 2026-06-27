import type { StoreItem } from './api'
import type { StoreIdeaKeyword } from './storeIdeas'

export type ProductStatus = 'idea' | 'brief_ready' | 'design_approved' | 'mockup_selected' | 'sent_to_listing'
export type ListingStatus = 'draft' | 'needs_review' | 'ready'

export interface StoreKeywordCandidate extends StoreIdeaKeyword {
  strength: number | null
  source: string
}

export interface StoreProductIdea {
  id: string
  storeSlug: string
  keyword: string
  title: string
  productType: string
  targetBuyer: string
  designBrief: string
  mockupPrompt: string
  designProvider?: string
  designPrompt?: string
  approvedDesign?: StoreProductDesignAsset
  supportingKeywords: string[]
  evidence: {
    strength?: number | null
    opportunity?: number | null
    gap?: number | null
    buyerIntent?: number | null
  }
  status: ProductStatus
  createdAt: string
  updatedAt: string
}

export interface StoreProductDesignAsset {
  id: string
  provider: string
  type: 'svg' | 'image' | 'external'
  title: string
  prompt: string
  assetUrl: string
  svgMarkup?: string
  approvedAt: string
}

export interface StoreListingDraft {
  id: string
  storeSlug: string
  productId: string
  title: string
  productType: string
  primaryKeyword: string
  supportingKeywords: string[]
  tags: string[]
  description: string
  price: string
  status: ListingStatus
  createdAt: string
  updatedAt: string
}

export interface StoreWorkspace {
  products: StoreProductIdea[]
  listings: StoreListingDraft[]
}

type WorkspaceStore = Record<string, StoreWorkspace>

const WORKSPACE_KEY = 'niche-research-pwa:store-workspace:v1'

export function emptyWorkspace(): StoreWorkspace {
  return { products: [], listings: [] }
}

export function readStoreWorkspace(storeSlug: string): StoreWorkspace {
  return readWorkspaceStore()[storeSlug] || emptyWorkspace()
}

export function saveProductIdea(storeSlug: string, idea: StoreProductIdea): StoreWorkspace {
  const all = readWorkspaceStore()
  const workspace = all[storeSlug] || emptyWorkspace()
  const now = new Date().toISOString()
  const product = {
    ...idea,
    id: idea.id.startsWith('candidate-') ? uniqueId('product') : idea.id,
    storeSlug,
    updatedAt: now,
    createdAt: idea.createdAt || now,
  }
  const exists = workspace.products.some((item) => item.id === product.id)
  const products = exists
    ? workspace.products.map((item) => item.id === product.id ? product : item)
    : [product, ...workspace.products]
  all[storeSlug] = { ...workspace, products }
  writeWorkspaceStore(all)
  return all[storeSlug]
}

export function updateProductIdea(storeSlug: string, productId: string, patch: Partial<StoreProductIdea>): StoreWorkspace {
  const all = readWorkspaceStore()
  const workspace = all[storeSlug] || emptyWorkspace()
  const products = workspace.products.map((item) => (
    item.id === productId ? { ...item, ...patch, updatedAt: new Date().toISOString() } : item
  ))
  all[storeSlug] = { ...workspace, products }
  writeWorkspaceStore(all)
  return all[storeSlug]
}

export function saveListingDraft(storeSlug: string, listing: StoreListingDraft): StoreWorkspace {
  const all = readWorkspaceStore()
  const workspace = all[storeSlug] || emptyWorkspace()
  const now = new Date().toISOString()
  const draft = {
    ...listing,
    id: listing.id.startsWith('candidate-') ? uniqueId('listing') : listing.id,
    storeSlug,
    updatedAt: now,
    createdAt: listing.createdAt || now,
  }
  const exists = workspace.listings.some((item) => item.id === draft.id)
  const listings = exists
    ? workspace.listings.map((item) => item.id === draft.id ? draft : item)
    : [draft, ...workspace.listings]
  all[storeSlug] = { ...workspace, listings }
  writeWorkspaceStore(all)
  return all[storeSlug]
}

export function updateListingDraft(storeSlug: string, listingId: string, patch: Partial<StoreListingDraft>): StoreWorkspace {
  const all = readWorkspaceStore()
  const workspace = all[storeSlug] || emptyWorkspace()
  const listings = workspace.listings.map((item) => (
    item.id === listingId ? { ...item, ...patch, updatedAt: new Date().toISOString() } : item
  ))
  all[storeSlug] = { ...workspace, listings }
  writeWorkspaceStore(all)
  return all[storeSlug]
}

export function createProductIdeas(store: StoreItem, keyword: StoreKeywordCandidate, count = 6): StoreProductIdea[] {
  const snapshot = store.research_snapshot || {}
  const blueprints = arrayOfRecords(snapshot.listing_blueprints)
  const productTypes = store.product_types?.length ? store.product_types : ['digital_download']
  const relatedBlueprints = blueprints.filter((blueprint) => {
    const primary = String(blueprint.primaryKeyword || '').toLowerCase()
    const supporting = arrayOfStrings(blueprint.supportingKeywords).join(' ').toLowerCase()
    const selected = keyword.keyword.toLowerCase()
    return primary.includes(selected) || selected.includes(primary) || supporting.includes(selected)
  })
  const sourceBlueprints = relatedBlueprints.length ? relatedBlueprints : blueprints
  const now = new Date().toISOString()

  return productTypes.slice(0, count).map((productType, index) => {
    const blueprint = sourceBlueprints[index % Math.max(1, sourceBlueprints.length)]
    const title = buildProductTitle(keyword.keyword, productType, blueprint, index)
    const supportingKeywords = dedupe([
      ...arrayOfStrings(blueprint?.supportingKeywords),
      ...keywordsNear(store, keyword.keyword).map((item) => item.keyword),
    ]).filter((term) => term.toLowerCase() !== keyword.keyword.toLowerCase()).slice(0, 8)
    const targetBuyer = store.target_audience || `Etsy buyers searching for ${keyword.keyword}`
    const productLabel = productType.replace(/_/g, ' ')
    return {
      id: `candidate-${store.slug}-${slugify(keyword.keyword)}-${index}`,
      storeSlug: store.slug,
      keyword: keyword.keyword,
      title,
      productType,
      targetBuyer,
      designBrief: `Create a ${productLabel} concept for "${keyword.keyword}" that matches ${store.aesthetic || store.niche}. Keep the design specific enough to stand apart from broad generic Etsy listings.`,
      mockupPrompt: `Mock up "${title}" as a ${productLabel}. Use the store aesthetic (${store.aesthetic || 'cohesive Etsy-ready style'}) and make the primary keyword visually obvious without clutter.`,
      supportingKeywords,
      evidence: {
        strength: keyword.strength,
        opportunity: keyword.opportunity,
        gap: keyword.gap,
        buyerIntent: keyword.buyerIntent,
      },
      status: 'idea',
      createdAt: now,
      updatedAt: now,
    }
  })
}

export function createListingFromProduct(store: StoreItem, product: StoreProductIdea): StoreListingDraft {
  const now = new Date().toISOString()
  const tags = dedupe([
    product.keyword,
    ...product.supportingKeywords,
    product.productType.replace(/_/g, ' '),
    store.niche,
  ]).slice(0, 13)
  return {
    id: `candidate-listing-${product.id}`,
    storeSlug: store.slug,
    productId: product.id,
    title: product.title,
    productType: product.productType,
    primaryKeyword: product.keyword,
    supportingKeywords: product.supportingKeywords,
    tags,
    description: listingDescription(store, product),
    price: '',
    status: 'draft',
    createdAt: now,
    updatedAt: now,
  }
}

export function extractStoreKeywords(store: StoreItem): StoreKeywordCandidate[] {
  const byKeyword = new Map<string, StoreKeywordCandidate>()
  const addKeyword = (keyword: Partial<StoreIdeaKeyword> & { keyword?: string }, source: string) => {
    const name = String(keyword.keyword || '').trim()
    if (!name) return
    const key = name.toLowerCase()
    const current = byKeyword.get(key)
    const merged: StoreKeywordCandidate = {
      keyword: current?.keyword || name,
      product: current?.product || keyword.product || 'Keyword',
      opportunity: bestNumber(current?.opportunity, keyword.opportunity),
      gap: bestNumber(current?.gap, keyword.gap),
      demand: bestNumber(current?.demand, keyword.demand),
      margin: bestNumber(current?.margin, keyword.margin),
      estimatedRevenue: bestNumber(current?.estimatedRevenue, keyword.estimatedRevenue),
      revenuePerListing: bestNumber(current?.revenuePerListing, keyword.revenuePerListing),
      avgPrice: bestNumber(current?.avgPrice, keyword.avgPrice),
      competitionEase: bestNumber(current?.competitionEase, keyword.competitionEase),
      marketEvidenceScore: bestNumber(current?.marketEvidenceScore, keyword.marketEvidenceScore),
      profitabilityIndex: bestNumber(current?.profitabilityIndex, keyword.profitabilityIndex),
      avgFavorites: bestNumber(current?.avgFavorites, keyword.avgFavorites),
      buyerIntent: bestNumber(current?.buyerIntent, keyword.buyerIntent),
      profitGap: bestNumber(current?.profitGap, keyword.profitGap),
      sourceStrength: bestNumber(current?.sourceStrength, keyword.sourceStrength),
      specificityScore: bestNumber(current?.specificityScore, keyword.specificityScore),
      priceRange: current?.priceRange || keyword.priceRange || null,
      strength: null,
      source: current?.source ? `${current.source}, ${source}` : source,
    }
    merged.strength = keywordStrength(merged)
    byKeyword.set(key, merged)
  }

  const snapshot = store.research_snapshot || {}
  arrayOfRecords(snapshot.keywords).forEach((keyword) => addKeyword(keyword as Partial<StoreIdeaKeyword>, 'store'))
  arrayOfRecords(snapshot.keyword_clusters).forEach((cluster) => {
    arrayOfRecords(cluster.keywords).forEach((keyword) => addKeyword(keyword as Partial<StoreIdeaKeyword>, String(cluster.label || 'cluster')))
  })
  arrayOfRecords(snapshot.listing_blueprints).forEach((blueprint) => {
    const quality = numberOrNull(blueprint.profitabilityScore) ?? numberOrNull(blueprint.listingQualityScore)
    addKeyword({
      keyword: String(blueprint.primaryKeyword || ''),
      product: String(blueprint.productType || 'Keyword'),
      sourceStrength: quality,
      buyerIntent: numberOrNull(blueprint.buyerIntent) ?? undefined,
      priceRange: recordOrNull(blueprint.priceBand) as StoreIdeaKeyword['priceRange'],
    }, 'blueprint')
    arrayOfStrings(blueprint.supportingKeywords).forEach((keyword) => addKeyword({
      keyword,
      product: String(blueprint.productType || 'Keyword'),
      sourceStrength: quality,
      buyerIntent: numberOrNull(blueprint.buyerIntent) ?? undefined,
    }, 'blueprint'))
  })

  return Array.from(byKeyword.values()).sort((a, b) => {
    const aStrength = a.strength ?? -1
    const bStrength = b.strength ?? -1
    if (bStrength !== aStrength) return bStrength - aStrength
    return a.keyword.localeCompare(b.keyword)
  })
}

export function extractKeywordClusters(store: StoreItem): Array<{ id: string; label: string; keywords: StoreKeywordCandidate[] }> {
  return arrayOfRecords(store.research_snapshot?.keyword_clusters).map((cluster, index) => ({
    id: String(cluster.id || `cluster-${index}`),
    label: String(cluster.label || `Cluster ${index + 1}`),
    keywords: arrayOfRecords(cluster.keywords)
      .map((keyword) => {
        const item = keyword as Partial<StoreIdeaKeyword>
        return {
          ...item,
          keyword: String(item.keyword || ''),
          product: item.product || 'Keyword',
          strength: keywordStrength(item as StoreIdeaKeyword),
          source: String(cluster.label || 'cluster'),
        } as StoreKeywordCandidate
      })
      .filter((keyword) => keyword.keyword),
  }))
}

export function validationItems(store: StoreItem, workspace: StoreWorkspace): Array<{ label: string; complete: boolean; detail: string }> {
  const keywords = extractStoreKeywords(store)
  const clusters = extractKeywordClusters(store)
  const topKeywordCount = keywords.filter((keyword) => (keyword.strength || 0) >= 70).length
  return [
    {
      label: 'Keyword cluster selected',
      complete: clusters.length > 0,
      detail: clusters.length ? `${clusters.length} source-backed clusters saved` : 'No keyword clusters found in this store snapshot',
    },
    {
      label: 'Strong keyword base',
      complete: topKeywordCount >= 3,
      detail: topKeywordCount >= 3 ? `${topKeywordCount} keywords score 70+ strength` : `${topKeywordCount} keywords score 70+ strength`,
    },
    {
      label: 'Product ideas saved',
      complete: workspace.products.length >= 3,
      detail: `${workspace.products.length} product ideas saved`,
    },
    {
      label: 'Design approved',
      complete: workspace.products.some((product) => !!product.approvedDesign || product.status === 'design_approved' || product.status === 'mockup_selected' || product.status === 'sent_to_listing'),
      detail: workspace.products.some((product) => !!product.approvedDesign || product.status === 'design_approved' || product.status === 'mockup_selected' || product.status === 'sent_to_listing')
        ? 'At least one product has an approved design'
        : 'No product has an approved design yet',
    },
    {
      label: 'Mockup direction selected',
      complete: workspace.products.some((product) => product.status === 'mockup_selected' || product.status === 'sent_to_listing'),
      detail: workspace.products.some((product) => product.status === 'mockup_selected' || product.status === 'sent_to_listing')
        ? 'At least one product has a selected mockup direction'
        : 'No product has a selected mockup direction yet',
    },
    {
      label: 'Listing drafts created',
      complete: workspace.listings.length > 0,
      detail: `${workspace.listings.length} listing drafts created`,
    },
  ]
}

function readWorkspaceStore(): WorkspaceStore {
  if (typeof window === 'undefined' || !window.localStorage) return {}
  try {
    const raw = window.localStorage.getItem(WORKSPACE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as WorkspaceStore : {}
  } catch {
    return {}
  }
}

function writeWorkspaceStore(value: WorkspaceStore): void {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem(WORKSPACE_KEY, JSON.stringify(value))
}

function keywordsNear(store: StoreItem, keyword: string): StoreKeywordCandidate[] {
  const root = keyword.toLowerCase().split(/\s+/).filter(Boolean)
  return extractStoreKeywords(store)
    .filter((candidate) => candidate.keyword.toLowerCase() !== keyword.toLowerCase())
    .filter((candidate) => root.some((term) => candidate.keyword.toLowerCase().includes(term)))
    .slice(0, 8)
}

function buildProductTitle(keyword: string, productType: string, blueprint: Record<string, unknown> | undefined, index: number): string {
  if (blueprint?.title && index === 0) return String(blueprint.title)
  const productLabel = productType.replace(/_/g, ' ')
  const variants = [
    `${titleCase(keyword)} ${titleCase(productLabel)}`,
    `Personalized ${titleCase(keyword)} ${titleCase(productLabel)}`,
    `${titleCase(keyword)} Gift ${titleCase(productLabel)}`,
    `${titleCase(keyword)} Bundle for ${titleCase(productLabel)}`,
    `Minimal ${titleCase(keyword)} ${titleCase(productLabel)}`,
    `${titleCase(keyword)} Starter Set`,
  ]
  return variants[index % variants.length]
}

function listingDescription(store: StoreItem, product: StoreProductIdea): string {
  const keywordLine = product.supportingKeywords.length
    ? `Optimized around ${product.keyword} with supporting terms like ${product.supportingKeywords.slice(0, 4).join(', ')}.`
    : `Optimized around ${product.keyword}.`
  return [
    `${product.title} is designed for ${product.targetBuyer}.`,
    keywordLine,
    `Design direction: ${product.designBrief}`,
    `Store fit: ${store.brand_voice || 'focused, data-led'} with ${store.aesthetic || store.niche} styling.`,
  ].join('\n\n')
}

function keywordStrength(keyword: Partial<StoreIdeaKeyword>): number | null {
  const factors: Array<[number | null | undefined, number]> = [
    [keyword.profitabilityIndex, 1.35],
    [keyword.opportunity, 1.25],
    [keyword.gap, 1.2],
    [keyword.sourceStrength, 1.1],
    [keyword.specificityScore, 0.95],
    [keyword.marketEvidenceScore, 0.95],
    [keyword.buyerIntent, 0.85],
    [keyword.demand, 0.75],
    [keyword.margin, 0.65],
    [keyword.competitionEase, 0.6],
    [keyword.profitGap, 0.6],
  ]
  let weighted = 0
  let weight = 0
  for (const [value, factor] of factors) {
    if (!Number.isFinite(value)) continue
    weighted += Number(value) * factor
    weight += factor
  }
  if (weight === 0) return null
  const revenueBoost = keyword.estimatedRevenue
    ? Math.min(8, Math.log10(Math.max(10, keyword.estimatedRevenue)) * 2)
    : 0
  return Math.round(Math.min(100, weighted / weight + revenueBoost))
}

function bestNumber(a?: number | null, b?: number | null): number | undefined {
  const aOk = Number.isFinite(a)
  const bOk = Number.isFinite(b)
  if (aOk && bOk) return Math.max(Number(a), Number(b))
  if (aOk) return Number(a)
  if (bOk) return Number(b)
  return undefined
}

function numberOrNull(value: unknown): number | null {
  return Number.isFinite(value) ? Number(value) : null
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function arrayOfRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object' && !Array.isArray(item)) : []
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || '').trim()).filter(Boolean) : []
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values.map((item) => item.trim()).filter(Boolean)) {
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(value)
  }
  return result
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'keyword'
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
}

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

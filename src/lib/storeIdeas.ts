import type { GapReport } from '../types/gaps'

type OpportunityLike = Record<string, unknown>
type DimensionType = 'audience' | 'theme' | 'style' | 'occasion' | 'intent'

export interface StoreIdeaKeyword {
  keyword: string
  opportunity?: number | null
  gap?: number | null
  product: string
  demand?: number | null
  margin?: number | null
  estimatedRevenue?: number | null
  revenuePerListing?: number | null
  avgPrice?: number | null
  competitionEase?: number | null
  marketEvidenceScore?: number | null
  profitabilityIndex?: number | null
  avgFavorites?: number | null
  buyerIntent?: number | null
  profitGap?: number | null
  sourceStrength?: number | null
  specificityScore?: number | null
  priceRange?: { min: number; max: number } | null
  sources?: string[]
  scoreVersion?: string | null
  evidenceStatus?: string | null
}

export interface StoreIdeaEvidenceDepth {
  score: number | null
  level: string
  keywordSignals: number
  scoredKeywords: number
  pricedKeywords: number
  revenueSignals: number
  revenueDensitySignals?: number
  competitionSignals: number
  buyerTractionSignals?: number
  trendSignals: number
  productTypes: number
  missing: string[]
}

export interface StoreIdeaKeywordCluster {
  id: string
  label: string
  clusterType: 'product' | DimensionType | 'domain' | string
  keywords: StoreIdeaKeyword[]
  primaryProducts: string[]
  avgOpportunity: number | null
  avgGap: number | null
  avgDemand?: number | null
  competitionEase?: number | null
  buyerIntent?: number | null
  clusterQualityScore?: number | null
  specificityScore?: number | null
  sourceDiversityScore?: number | null
  productMixScore?: number | null
  keywordDepthScore?: number | null
  revenueDensityScore?: number | null
  avgRevenuePerListing?: number | null
  marketEvidenceScore?: number | null
  profitabilityScore?: number | null
}

export interface StoreIdeaListingBlueprint {
  id: string
  title: string
  primaryKeyword: string
  supportingKeywords: string[]
  sourceClusterId?: string | null
  sourceClusterLabel?: string | null
  productType: string
  buyerIntent?: number | null
  priceBand?: { min: number; max: number } | null
  tags: string[]
  profitabilityScore?: number | null
  listingQualityScore?: number | null
  profitInputs?: Record<string, unknown> | null
  qualityInputs?: Record<string, unknown> | null
  evidenceLevel: string
  profitRationale: string
}

export interface StoreIdeaRecommendation {
  positioning: string
  targetCustomer: string
  recommendedCollections: string[]
  launchListingIdeas: string[]
  listingGenerationInputs?: Array<Record<string, unknown>>
  keywordStrategy: {
    primaryKeywords: string[]
    expansionKeywords: string[]
    clusterCount: number
    listingBlueprintCount: number
  }
  storeQualityScore?: number | null
  qualityGrade?: string | null
  qualityInputs?: Record<string, unknown> | null
  qualityPriority?: string
  qualityOptimizationPlan?: string[]
  profitPriority: string
  profitOptimizationPlan?: string[]
  validationPriorities?: Array<{ evidenceGap: string; action: string; keywords: string[] }>
  nextValidationStep: string
}

export interface StoreIdeaProfitabilityEvidence {
  evidenceScore: number | null
  evidenceLevel: string
  observedPriceBand?: { p25?: number | null; median?: number | null; p75?: number | null; avg?: number | null } | null
  priceBasis?: 'observed' | string | null
  estimatedGrossMargin?: number | null
  sampledMonthlyRevenue?: number | null
  revenuePerListing?: number | null
  revenueDensityScore?: number | null
  marketTractionScore?: number | null
  sellerWeaknessScore?: number | null
  avgListingCount?: number | null
  avgFavorites?: number | null
  signalsWithDeepMarketData: number
  missing: string[]
}

export interface StoreIdea {
  id: string
  name: string
  focus: string
  anchorType: DimensionType
  keywords: StoreIdeaKeyword[]
  productTypes: string[]
  avgOpportunity: number | null
  avgGap?: number | null
  nicheScore: number | null
  storeQualityScore?: number | null
  recommendationScore?: number | null
  commercialPotentialScore?: number | null
  qualityGrade?: string | null
  specificityScore?: number | null
  sourceDiversityScore?: number | null
  productMixScore?: number | null
  keywordDepthScore?: number | null
  profitScore?: number | null
  rawProfitScore?: number | null
  profitGrade?: string | null
  cohesion: number | null
  trendLift: number | null
  demandScore?: number | null
  marginScore?: number | null
  competitionEase?: number | null
  buyerIntent?: number | null
  confidenceScore?: number | null
  avgPrice?: number | null
  priceRange?: { min: number; max: number } | null
  priceBasis?: 'observed' | string | null
  estimatedGrossMargin?: number | null
  estimatedMonthlyRevenue?: number | null
  profitabilityEvidence?: StoreIdeaProfitabilityEvidence
  scoreBreakdown?: Record<string, number> | null
  rationale: string
  evidence: string[]
  evidenceDepth?: StoreIdeaEvidenceDepth
  keywordClusters?: StoreIdeaKeywordCluster[]
  listingBlueprints?: StoreIdeaListingBlueprint[]
  storeRecommendation?: StoreIdeaRecommendation
  feeModel?: null
  listingIdeas: string[]
  risks: string[]
  profitDrivers?: string[]
  validationChecklist?: string[]
}

const PRODUCT_TERMS: Array<[string, string[]]> = [
  ['Wall art', ['wall art', 'print', 'poster', 'canvas', 'framed']],
  ['Apparel', ['shirt', 'tshirt', 'tee', 'hoodie', 'sweatshirt', 'crewneck']],
  ['Mugs', ['mug', 'coffee cup']],
  ['Stickers', ['sticker', 'decal']],
  ['Digital downloads', ['digital download', 'downloadable', 'printable', 'template', 'pdf']],
  ['Planners', ['planner', 'journal', 'notebook', 'tracker', 'worksheet']],
  ['Craft files', ['svg', 'sublimation', 'cricut', 'cut file']],
  ['Totes', ['tote', 'canvas bag']],
  ['Tumblers', ['tumbler', 'water bottle']],
  ['Invitations', ['invitation', 'invite', 'save the date']],
  ['Ornaments', ['ornament']],
]

/**
 * User imports are not promoted into store ideas until a versioned model has
 * explicitly marked each source row verified. Imported observations remain
 * visible elsewhere, but they are not converted into synthetic rankings.
 */
export function generateStoreIdeas(opportunities: OpportunityLike[] = [], gaps: GapReport[] = []): StoreIdea[] {
  void gaps
  const verified = opportunities.filter((row) => row.evidence_status === 'verified' && Boolean(row.score_version))
  if (verified.length === 0) return []

  const groups = new Map<string, OpportunityLike[]>()
  verified.forEach((row) => {
    const keyword = String(row.keyword || '').trim()
    if (!keyword) return
    const domain = String(row.domain || 'uncategorized').trim() || 'uncategorized'
    groups.set(domain, [...(groups.get(domain) || []), row])
  })

  return Array.from(groups.entries()).map(([domain, rows]) => toStoreIdea(domain, rows)).slice(0, 12)
}

function toStoreIdea(domain: string, rows: OpportunityLike[]): StoreIdea {
  const focus = domain === 'uncategorized' ? 'Verified keyword collection' : titleCase(domain.replace(/_/g, ' '))
  const keywords = rows.map(toKeyword)
  const products = observedProducts(keywords.map((item) => item.keyword))
  const missing = missingEvidence(rows)
  const clusterId = slug(focus)
  const blueprints = keywords.map((keyword) => ({
    id: slug(keyword.keyword),
    title: titleCase(keyword.keyword),
    primaryKeyword: keyword.keyword,
    supportingKeywords: [],
    productType: keyword.product,
    buyerIntent: null,
    priceBand: keyword.priceRange || null,
    tags: [keyword.keyword],
    profitabilityScore: null,
    listingQualityScore: null,
    profitInputs: null,
    qualityInputs: null,
    evidenceLevel: 'verified keyword; profitability TBD',
    profitRationale: 'No profitability claim until exact economics and listing outcomes are recorded.',
  }))

  return {
    id: slug(`${focus} store`),
    name: `${focus} Store`,
    focus,
    anchorType: 'theme',
    keywords,
    productTypes: products,
    avgOpportunity: average(rows.map((row) => number(row.opportunity_score))),
    avgGap: average(rows.map((row) => number(row.gap_score))),
    nicheScore: null,
    cohesion: null,
    trendLift: null,
    demandScore: average(rows.map((row) => number(row.demand_score))),
    marginScore: average(rows.map((row) => number(row.margin_score))),
    profitScore: null,
    confidenceScore: null,
    avgPrice: average(rows.map((row) => number(row.avg_price_usd))),
    estimatedGrossMargin: null,
    estimatedMonthlyRevenue: sum(rows.map((row) => number(row.monthly_revenue_usd))),
    rationale: `Grouped from ${rows.length} verified, versioned keyword record(s) in ${focus}.`,
    evidence: [`${rows.length} verified keyword record(s) with an explicit score version`],
    evidenceDepth: {
      score: null,
      level: 'TBD — evidence is counted, not heuristically scored',
      keywordSignals: rows.length,
      scoredKeywords: rows.filter((row) => number(row.opportunity_score) != null || number(row.gap_score) != null).length,
      pricedKeywords: rows.filter((row) => number(row.avg_price_usd) != null).length,
      revenueSignals: rows.filter((row) => number(row.monthly_revenue_usd) != null).length,
      competitionSignals: rows.filter((row) => number(row.competition_quality) != null).length,
      trendSignals: rows.filter((row) => number(row.trend_score) != null).length,
      productTypes: products.length,
      missing,
    },
    keywordClusters: [{
      id: clusterId,
      label: focus,
      clusterType: 'domain',
      keywords,
      primaryProducts: products,
      avgOpportunity: average(rows.map((row) => number(row.opportunity_score))),
      avgGap: average(rows.map((row) => number(row.gap_score))),
      avgDemand: average(rows.map((row) => number(row.demand_score))),
      competitionEase: null,
      buyerIntent: null,
      clusterQualityScore: null,
      profitabilityScore: null,
    }],
    listingBlueprints: blueprints,
    storeRecommendation: {
      positioning: `Use the verified ${focus} keywords as a research collection, not a profit claim.`,
      targetCustomer: 'TBD — validate with observed buyers and conversions',
      recommendedCollections: [focus],
      launchListingIdeas: blueprints.map((item) => item.title),
      keywordStrategy: {
        primaryKeywords: keywords.map((item) => item.keyword),
        expansionKeywords: [],
        clusterCount: 1,
        listingBlueprintCount: blueprints.length,
      },
      storeQualityScore: null,
      qualityGrade: null,
      profitPriority: 'TBD — record exact unit economics and outcomes first',
      nextValidationStep: 'Record exact unit economics, then run controlled listings and capture outcomes.',
    },
    feeModel: null,
    listingIdeas: blueprints.map((item) => item.title),
    risks: missing,
    validationChecklist: missing.map((item) => `Collect ${item}.`),
  }
}

function toKeyword(row: OpportunityLike): StoreIdeaKeyword {
  const keyword = String(row.keyword || '').trim()
  const products = observedProducts([keyword])
  return {
    keyword,
    product: products[0] || 'TBD',
    opportunity: number(row.opportunity_score),
    gap: number(row.gap_score),
    demand: number(row.demand_score),
    margin: number(row.margin_score),
    estimatedRevenue: number(row.monthly_revenue_usd),
    avgPrice: number(row.avg_price_usd),
    competitionEase: null,
    buyerIntent: null,
    sourceStrength: null,
    specificityScore: null,
    scoreVersion: String(row.score_version),
    evidenceStatus: 'verified',
  }
}

function observedProducts(keywords: string[]): string[] {
  const text = keywords.join(' ').toLowerCase()
  return PRODUCT_TERMS.filter(([, terms]) => terms.some((term) => text.includes(term))).map(([label]) => label)
}

function missingEvidence(rows: OpportunityLike[]): string[] {
  const fields: Array<[string, string]> = [
    ['observed price data', 'avg_price_usd'],
    ['observed revenue data', 'monthly_revenue_usd'],
    ['listing supply data', 'listing_count'],
    ['buyer traction data', 'avg_favorites'],
  ]
  const missing = fields.filter(([, field]) => !rows.some((row) => number(row[field]) != null)).map(([label]) => label)
  return [...missing, 'exact product costs and fees', 'actual listing outcomes']
}

function number(value: unknown): number | null {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function average(values: Array<number | null>): number | null {
  const usable = values.filter((value): value is number => value != null)
  return usable.length ? Math.round((usable.reduce((total, value) => total + value, 0) / usable.length) * 100) / 100 : null
}

function sum(values: Array<number | null>): number | null {
  const usable = values.filter((value): value is number => value != null)
  return usable.length ? Math.round(usable.reduce((total, value) => total + value, 0) * 100) / 100 : null
}

function titleCase(value: string): string {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'verified-keyword-collection'
}

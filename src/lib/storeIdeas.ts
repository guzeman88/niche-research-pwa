import type { GapReport } from '../types/gaps'

type OpportunityLike = Record<string, unknown>
type DimensionType = 'audience' | 'theme' | 'style' | 'occasion' | 'intent'

interface TaxonomyItem {
  id: string
  label: string
  terms: string[]
}

interface KeywordSignal {
  keyword: string
  domain: string
  opportunity: number
  gap: number
  demand?: number
  margin?: number
  competitionEase?: number
  buyerIntent?: number
  avgPrice?: number
  estimatedRevenue?: number
  priceRange?: { min: number; max: number }
  trajectory: string
  breakout: boolean
  products: string[]
  audience: TaxonomyItem[]
  theme: TaxonomyItem[]
  style: TaxonomyItem[]
  occasion: TaxonomyItem[]
  intent: TaxonomyItem[]
}

interface ClusterSeed {
  primary: TaxonomyItem
  primaryType: DimensionType
  secondary?: TaxonomyItem
  secondaryType?: DimensionType
  signals: KeywordSignal[]
}

export interface StoreIdeaKeyword {
  keyword: string
  opportunity: number
  gap: number
  product: string
  demand?: number
  margin?: number
  estimatedRevenue?: number
  avgPrice?: number
  competitionEase?: number
  priceRange?: { min: number; max: number } | null
}

export interface StoreIdeaEvidenceDepth {
  score: number
  level: 'thin' | 'developing' | 'solid' | 'deep' | string
  keywordSignals: number
  scoredKeywords: number
  pricedKeywords: number
  revenueSignals: number
  competitionSignals: number
  trendSignals: number
  productTypes: number
  missing: string[]
}

export interface StoreIdeaKeywordCluster {
  id: string
  label: string
  clusterType: 'product' | DimensionType | string
  keywords: StoreIdeaKeyword[]
  primaryProducts: string[]
  avgOpportunity: number
  avgGap: number
  avgDemand?: number
  competitionEase?: number
  buyerIntent?: number
  profitabilityScore: number
}

export interface StoreIdeaListingBlueprint {
  id: string
  title: string
  primaryKeyword: string
  supportingKeywords: string[]
  sourceClusterId?: string
  sourceClusterLabel?: string
  productType: string
  buyerIntent?: number
  priceBand?: { min: number; max: number } | null
  tags: string[]
  profitabilityScore: number
  evidenceLevel: string
  profitRationale: string
}

export interface StoreIdeaRecommendation {
  positioning: string
  targetCustomer: string
  recommendedCollections: string[]
  launchListingIdeas: string[]
  keywordStrategy: {
    primaryKeywords: string[]
    expansionKeywords: string[]
    clusterCount: number
    listingBlueprintCount: number
  }
  profitPriority: string
  nextValidationStep: string
}

export interface StoreIdeaFeeModel {
  currency: string
  listingFee: number
  transactionFeeRate: number
  estimatedPaymentProcessingRate?: number
  estimatedPaymentProcessingFixed?: number
  offsiteAdsRateRange?: { min: number; max: number }
  note: string
}

export interface StoreIdea {
  id: string
  name: string
  focus: string
  anchorType: DimensionType
  keywords: StoreIdeaKeyword[]
  productTypes: string[]
  avgOpportunity: number
  avgGap: number
  nicheScore: number
  profitScore?: number
  rawProfitScore?: number
  profitGrade?: string
  cohesion: number
  trendLift: number
  demandScore?: number
  marginScore?: number
  competitionEase?: number
  buyerIntent?: number
  confidenceScore?: number
  avgPrice?: number
  priceRange?: { min: number; max: number }
  estimatedGrossMargin?: number
  estimatedMonthlyRevenue?: number
  rationale: string
  evidence: string[]
  evidenceDepth?: StoreIdeaEvidenceDepth
  keywordClusters?: StoreIdeaKeywordCluster[]
  listingBlueprints?: StoreIdeaListingBlueprint[]
  storeRecommendation?: StoreIdeaRecommendation
  feeModel?: StoreIdeaFeeModel
  listingIdeas: string[]
  risks: string[]
  profitDrivers?: string[]
  validationChecklist?: string[]
}

const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'best', 'by', 'for', 'from', 'gift',
  'gifts', 'in', 'is', 'it', 'of', 'on', 'or', 'set', 'the', 'to', 'with', 'without',
])

const PRODUCT_TERMS: TaxonomyItem[] = [
  { id: 'wall_art', label: 'Wall art', terms: ['wall art', 'print', 'prints', 'poster', 'posters', 'canvas', 'decor', 'frame', 'framed'] },
  { id: 'apparel', label: 'Apparel', terms: ['shirt', 'shirts', 'tshirt', 'tee', 'tees', 'hoodie', 'sweatshirt', 'crewneck', 'apparel'] },
  { id: 'mug', label: 'Mugs', terms: ['mug', 'mugs', 'cup', 'coffee cup'] },
  { id: 'sticker', label: 'Stickers', terms: ['sticker', 'stickers', 'decal', 'decals'] },
  { id: 'digital_download', label: 'Digital downloads', terms: ['digital download', 'download', 'downloadable', 'printable', 'template', 'pdf'] },
  { id: 'planner', label: 'Planners', terms: ['planner', 'journal', 'notebook', 'tracker', 'worksheet'] },
  { id: 'svg', label: 'Craft files', terms: ['svg', 'png', 'sublimation', 'cricut', 'cut file'] },
  { id: 'tote', label: 'Totes', terms: ['tote', 'bag', 'canvas bag'] },
  { id: 'tumbler', label: 'Tumblers', terms: ['tumbler', 'water bottle'] },
  { id: 'invitation', label: 'Invitations', terms: ['invitation', 'invite', 'announcement', 'save the date'] },
  { id: 'ornament', label: 'Ornaments', terms: ['ornament', 'ornaments'] },
]

const AUDIENCES: TaxonomyItem[] = [
  { id: 'nurse', label: 'Nurses', terms: ['nurse', 'nurses', 'rn', 'nursing', 'icu', 'er nurse'] },
  { id: 'teacher', label: 'Teachers', terms: ['teacher', 'teachers', 'teaching', 'classroom', 'educator'] },
  { id: 'mom', label: 'Moms', terms: ['mom', 'mama', 'mother', 'mommy', 'new mom'] },
  { id: 'dad', label: 'Dads', terms: ['dad', 'daddy', 'father', 'papa'] },
  { id: 'book_lover', label: 'Book lovers', terms: ['book lover', 'bookish', 'reader', 'reading', 'library', 'book club'] },
  { id: 'bride', label: 'Brides', terms: ['bride', 'bridal', 'bridesmaid', 'maid of honor', 'bachelorette'] },
  { id: 'baby_family', label: 'New families', terms: ['baby', 'newborn', 'nursery', 'pregnancy', 'family'] },
  { id: 'pet_parent', label: 'Pet parents', terms: ['dog mom', 'cat mom', 'pet', 'dog lover', 'cat lover'] },
  { id: 'gamer', label: 'Gamers', terms: ['gamer', 'gaming', 'video game'] },
  { id: 'faith_buyer', label: 'Faith buyers', terms: ['christian', 'bible', 'faith', 'church', 'jesus'] },
  { id: 'small_business', label: 'Small business owners', terms: ['small business', 'boutique', 'salon', 'realtor', 'coach'] },
]

const THEMES: TaxonomyItem[] = [
  { id: 'botanical', label: 'Botanical', terms: ['flower', 'floral', 'botanical', 'plant', 'garden', 'wildflower'] },
  { id: 'celestial', label: 'Celestial', terms: ['moon', 'sun', 'stars', 'zodiac', 'astrology', 'celestial'] },
  { id: 'coffee', label: 'Coffee', terms: ['coffee', 'latte', 'espresso', 'cafe'] },
  { id: 'mental_health', label: 'Mental health', terms: ['mental health', 'therapy', 'self care', 'anxiety', 'affirmation'] },
  { id: 'fitness', label: 'Fitness', terms: ['gym', 'fitness', 'workout', 'pilates', 'yoga', 'running'] },
  { id: 'travel', label: 'Travel', terms: ['travel', 'vacation', 'camping', 'hiking', 'adventure'] },
  { id: 'western', label: 'Western', terms: ['western', 'cowgirl', 'cowboy', 'rodeo', 'country'] },
  { id: 'pickleball', label: 'Pickleball', terms: ['pickleball'] },
  { id: 'sports', label: 'Sports', terms: ['baseball', 'football', 'soccer', 'basketball', 'softball'] },
  { id: 'music', label: 'Music', terms: ['music', 'band', 'song', 'album', 'playlist'] },
]

const STYLES: TaxonomyItem[] = [
  { id: 'dark_academia', label: 'Dark academia', terms: ['dark academia', 'academia', 'gothic library'] },
  { id: 'cottagecore', label: 'Cottagecore', terms: ['cottagecore', 'cottage', 'fairycore'] },
  { id: 'boho', label: 'Boho', terms: ['boho', 'bohemian'] },
  { id: 'minimalist', label: 'Minimalist', terms: ['minimalist', 'minimal', 'simple', 'clean'] },
  { id: 'retro', label: 'Retro', terms: ['retro', 'vintage', '70s', '80s', '90s', 'groovy'] },
  { id: 'coastal', label: 'Coastal', terms: ['coastal', 'beach', 'ocean', 'seaside'] },
  { id: 'goth', label: 'Goth', terms: ['goth', 'gothic', 'witchy', 'spooky'] },
  { id: 'kawaii', label: 'Kawaii', terms: ['kawaii', 'cute', 'chibi'] },
  { id: 'y2k', label: 'Y2K', terms: ['y2k', '2000s'] },
  { id: 'farmhouse', label: 'Farmhouse', terms: ['farmhouse', 'rustic'] },
]

const OCCASIONS: TaxonomyItem[] = [
  { id: 'wedding', label: 'Wedding', terms: ['wedding', 'bridal shower', 'bachelorette', 'engagement'] },
  { id: 'birthday', label: 'Birthday', terms: ['birthday', 'birth year'] },
  { id: 'christmas', label: 'Christmas', terms: ['christmas', 'xmas', 'holiday', 'santa'] },
  { id: 'halloween', label: 'Halloween', terms: ['halloween', 'spooky'] },
  { id: 'valentine', label: 'Valentine', terms: ['valentine', 'galentine'] },
  { id: 'graduation', label: 'Graduation', terms: ['graduation', 'graduate', 'class of'] },
  { id: 'baby_shower', label: 'Baby shower', terms: ['baby shower', 'gender reveal'] },
  { id: 'mothers_day', label: "Mother's Day", terms: ['mothers day', "mother's day"] },
  { id: 'fathers_day', label: "Father's Day", terms: ['fathers day', "father's day"] },
]

const INTENTS: TaxonomyItem[] = [
  { id: 'funny', label: 'Humor', terms: ['funny', 'humor', 'sarcastic', 'snarky', 'meme'] },
  { id: 'personalized', label: 'Personalized', terms: ['personalized', 'custom', 'name', 'monogram', 'initial'] },
  { id: 'giftable', label: 'Giftable', terms: ['gift', 'gifts', 'present'] },
  { id: 'motivational', label: 'Motivational', terms: ['motivational', 'inspirational', 'affirmation', 'positive'] },
  { id: 'matching', label: 'Matching sets', terms: ['matching', 'couple', 'family matching', 'team'] },
]

export function generateStoreIdeas(opportunities: OpportunityLike[] = [], gaps: GapReport[] = []): StoreIdea[] {
  const gapReports = new Map<string, GapReport>()
  for (const gap of gaps) {
    gapReports.set(normalizeKeyword(gap.keyword), gap)
  }

  const signals = opportunities
    .map((item) => toKeywordSignal(item, gapReports))
    .filter((signal): signal is KeywordSignal => Boolean(signal))
    .filter((signal) => signal.opportunity > 0 || signal.gap > 0)
    .sort((a, b) => weightedKeywordScore(b) - weightedKeywordScore(a))
    .slice(0, 180)

  if (signals.length === 0) return []

  return mergeSmallClusters(seedClusters(signals))
    .map(toStoreIdea)
    .filter((idea): idea is StoreIdea => Boolean(idea))
    .sort((a, b) => b.nicheScore - a.nicheScore)
    .slice(0, 12)
}

function toKeywordSignal(item: OpportunityLike, gapReports: Map<string, GapReport>): KeywordSignal | null {
  const keyword = String(item.keyword || '').trim()
  if (!keyword) return null

  const normalized = normalizeKeyword(keyword)
  const domain = String(item.domain || 'discovered').replace(/_/g, ' ')
  const gapReport = gapReports.get(normalized)
  const competition = firstFinite(item.competition_score, item.competition_quality)
  const recommendedMin = positiveNumber(gapReport?.recommended_price_min)
  const recommendedMax = positiveNumber(gapReport?.recommended_price_max)
  const priceRange = recommendedMin && recommendedMax && recommendedMax >= recommendedMin
    ? { min: recommendedMin, max: recommendedMax }
    : undefined

  return {
    keyword,
    domain,
    opportunity: toScore(item.opportunity_score),
    gap: toScore(item.gap_score ?? gapReport?.composite_gap_score),
    demand: optionalScore(item.demand_score),
    margin: optionalScore(item.margin_score),
    competitionEase: competition == null ? undefined : clampScore(100 - competition),
    buyerIntent: optionalScore(gapReport?.buyer_intent_score),
    avgPrice: positiveNumber(item.avg_price_usd),
    estimatedRevenue: positiveNumber(item.monthly_revenue_usd),
    priceRange,
    trajectory: String(item.trajectory || ''),
    breakout: Boolean(item.breakout || item.breakout_flag),
    products: matchProducts(normalized, domain),
    audience: matchTaxonomy(normalized, AUDIENCES),
    theme: matchTaxonomy(normalized, THEMES),
    style: matchTaxonomy(normalized, STYLES),
    occasion: matchTaxonomy(normalized, OCCASIONS),
    intent: matchTaxonomy(normalized, INTENTS),
  }
}

function seedClusters(signals: KeywordSignal[]): ClusterSeed[] {
  const byComposite = new Map<string, ClusterSeed>()

  for (const signal of signals) {
    const primaryMatch = choosePrimary(signal)
    if (!primaryMatch) continue

    const secondaryMatch = chooseSecondary(signal, primaryMatch.item.id)
    const key = secondaryMatch
      ? `${primaryMatch.type}:${primaryMatch.item.id}/${secondaryMatch.type}:${secondaryMatch.item.id}`
      : `${primaryMatch.type}:${primaryMatch.item.id}`

    const existing = byComposite.get(key)
    if (existing) {
      existing.signals.push(signal)
    } else {
      byComposite.set(key, {
        primary: primaryMatch.item,
        primaryType: primaryMatch.type,
        secondary: secondaryMatch?.item,
        secondaryType: secondaryMatch?.type,
        signals: [signal],
      })
    }
  }

  return Array.from(byComposite.values())
}

function mergeSmallClusters(clusters: ClusterSeed[]): ClusterSeed[] {
  const result: ClusterSeed[] = []
  const byPrimary = new Map<string, ClusterSeed>()

  for (const cluster of clusters) {
    const strongEnough = cluster.signals.length >= 3 || cluster.signals.some((signal) => weightedKeywordScore(signal) >= 78)
    if (strongEnough) {
      result.push(cluster)
      continue
    }

    const key = `${cluster.primaryType}:${cluster.primary.id}`
    const existing = byPrimary.get(key)
    if (existing) {
      existing.signals.push(...cluster.signals)
    } else {
      byPrimary.set(key, {
        primary: cluster.primary,
        primaryType: cluster.primaryType,
        signals: [...cluster.signals],
      })
    }
  }

  return [...result, ...byPrimary.values()]
}

function toStoreIdea(cluster: ClusterSeed): StoreIdea | null {
  const signals = uniqueByKeyword(cluster.signals)
    .sort((a, b) => weightedKeywordScore(b) - weightedKeywordScore(a))

  if (signals.length < 2) return null

  const avgOpportunity = average(signals.map((signal) => signal.opportunity))
  const avgGap = average(signals.map((signal) => signal.gap))
  const avgDemand = optionalAverage(signals.map((signal) => signal.demand))
  const avgMargin = optionalAverage(signals.map((signal) => signal.margin))
  const avgCompetitionEase = optionalAverage(signals.map((signal) => signal.competitionEase))
  const avgBuyerIntent = optionalAverage(signals.map((signal) => signal.buyerIntent))
  const avgPrice = positiveAverage(signals.map((signal) => signal.avgPrice))
  const revenueSignals = signals.map((signal) => signal.estimatedRevenue).filter(isPositiveNumber)
  const priceRanges = signals.map((signal) => signal.priceRange).filter((range): range is { min: number; max: number } => Boolean(range))
  const productTypes = rankProducts(signals)
  const cohesion = calculateCohesion(signals, cluster)
  const trendLift = calculateTrendLift(signals)
  const diversityLift = Math.min(10, Math.max(0, productTypes.length - 1) * 3)
  const keywordLift = Math.min(12, signals.length * 1.8)
  const nicheScore = clampScore(
    avgOpportunity * 0.48
    + avgGap * 0.26
    + cohesion * 0.12
    + keywordLift
    + diversityLift
    + trendLift,
  )

  const name = makeStoreName(cluster, productTypes)
  const focus = formatFocus(cluster)

  return {
    id: makeId(name),
    name,
    focus,
    anchorType: cluster.primaryType,
    keywords: signals.slice(0, 7).map((signal) => ({
      keyword: signal.keyword,
      opportunity: Math.round(signal.opportunity),
      gap: Math.round(signal.gap),
      product: formatProduct(signal.products[0] || productTypes[0] || 'digital_download'),
      demand: maybeRound(signal.demand),
      margin: maybeRound(signal.margin),
      estimatedRevenue: signal.estimatedRevenue,
      avgPrice: signal.avgPrice,
      competitionEase: maybeRound(signal.competitionEase),
    })),
    productTypes: productTypes.map(formatProduct),
    avgOpportunity: Math.round(avgOpportunity),
    avgGap: Math.round(avgGap),
    nicheScore: Math.round(nicheScore),
    cohesion: Math.round(cohesion),
    trendLift: Math.round(trendLift),
    demandScore: maybeRound(avgDemand),
    marginScore: maybeRound(avgMargin),
    competitionEase: maybeRound(avgCompetitionEase),
    buyerIntent: maybeRound(avgBuyerIntent),
    confidenceScore: Math.round(calculateConfidence(signals, cohesion)),
    avgPrice,
    priceRange: priceRanges.length > 0
      ? {
          min: Math.min(...priceRanges.map((range) => range.min)),
          max: Math.max(...priceRanges.map((range) => range.max)),
        }
      : undefined,
    estimatedMonthlyRevenue: revenueSignals.length > 0
      ? Math.round(revenueSignals.reduce((sum, value) => sum + value, 0))
      : undefined,
    rationale: makeRationale(signals, focus, productTypes),
    evidence: makeEvidence(signals, cluster, productTypes),
    listingIdeas: makeListingIdeas(cluster, productTypes),
    risks: makeRisks(signals, avgGap, cohesion, productTypes),
  }
}

function choosePrimary(signal: KeywordSignal): { type: DimensionType; item: TaxonomyItem } | null {
  const dimensions: Array<[DimensionType, TaxonomyItem[]]> = [
    ['audience', signal.audience],
    ['theme', signal.theme],
    ['style', signal.style],
    ['occasion', signal.occasion],
  ]

  for (const [type, matches] of dimensions) {
    if (matches.length > 0) return { type, item: matches[0] }
  }

  const domainItem = domainToItem(signal.domain)
  return domainItem ? { type: 'theme', item: domainItem } : null
}

function chooseSecondary(signal: KeywordSignal, primaryId: string): { type: DimensionType; item: TaxonomyItem } | null {
  const dimensions: Array<[DimensionType, TaxonomyItem[]]> = [
    ['intent', signal.intent.filter((item) => item.id !== 'giftable')],
    ['style', signal.style],
    ['theme', signal.theme],
    ['occasion', signal.occasion],
    ['audience', signal.audience],
  ]

  for (const [type, matches] of dimensions) {
    const match = matches.find((item) => item.id !== primaryId)
    if (match) return { type, item: match }
  }

  return null
}

function matchTaxonomy(text: string, taxonomy: TaxonomyItem[]): TaxonomyItem[] {
  return taxonomy.filter((item) => item.terms.some((term) => containsTerm(text, term)))
}

function matchProducts(keyword: string, domain: string): string[] {
  const haystack = `${keyword} ${domain}`.toLowerCase()
  const products = PRODUCT_TERMS
    .filter((item) => item.terms.some((term) => containsTerm(haystack, term)))
    .map((item) => item.id)

  if (products.length > 0) return [...new Set(products)]
  if (/decor|home|aesthetic|art/.test(domain)) return ['wall_art', 'digital_download']
  return ['digital_download']
}

function containsTerm(text: string, term: string): boolean {
  const normalizedTerm = normalizeKeyword(term)
  if (normalizedTerm.includes(' ')) return text.includes(normalizedTerm)
  return new RegExp(`(^|\\s)${escapeRegExp(normalizedTerm)}(\\s|$)`).test(text)
}

function domainToItem(domain: string): TaxonomyItem | null {
  const cleaned = normalizeKeyword(domain)
    .split(' ')
    .filter((part) => !STOP_WORDS.has(part))
    .slice(0, 3)
    .join(' ')

  if (!cleaned) return null

  return {
    id: makeId(cleaned),
    label: titleCase(cleaned),
    terms: [cleaned],
  }
}

function rankProducts(signals: KeywordSignal[]): string[] {
  const counts = new Map<string, number>()
  for (const signal of signals) {
    for (const product of signal.products) {
      counts.set(product, (counts.get(product) || 0) + weightedKeywordScore(signal))
    }
  }

  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([product]) => product)
    .slice(0, 5)
}

function calculateCohesion(signals: KeywordSignal[], cluster: ClusterSeed): number {
  const coverage = signals.filter((signal) => {
    const dimensions = [
      ...signal.audience,
      ...signal.theme,
      ...signal.style,
      ...signal.occasion,
      ...signal.intent,
    ].map((item) => item.id)

    return dimensions.includes(cluster.primary.id)
      || Boolean(cluster.secondary && dimensions.includes(cluster.secondary.id))
      || normalizeKeyword(signal.domain).includes(cluster.primary.id.replace(/_/g, ' '))
  }).length / signals.length

  return clampScore((coverage * 75) + (Math.min(1, signals.length / 6) * 25))
}

function calculateTrendLift(signals: KeywordSignal[]): number {
  const lift = signals.reduce((sum, signal) => {
    const trajectory = signal.trajectory.toLowerCase()
    if (signal.breakout) return sum + 4
    if (trajectory.includes('rising') || trajectory.includes('up')) return sum + 3
    if (trajectory.includes('stable')) return sum + 1
    return sum
  }, 0)

  return Math.min(10, lift)
}

function calculateConfidence(signals: KeywordSignal[], cohesion: number): number {
  const scanDepth = Math.min(100, signals.length * 14)
  const coreFields = signals.reduce((sum, signal) => (
    sum
    + (signal.demand == null ? 0 : 1)
    + (signal.margin == null ? 0 : 1)
    + (signal.competitionEase == null ? 0 : 1)
    + (signal.gap > 0 ? 1 : 0)
  ), 0)
  const marketFields = signals.reduce((sum, signal) => (
    sum
    + (signal.buyerIntent == null ? 0 : 1)
    + (signal.avgPrice == null ? 0 : 1)
    + (signal.estimatedRevenue == null ? 0 : 1)
  ), 0)
  const coreCompleteness = signals.length > 0 ? (coreFields / (signals.length * 4)) * 100 : 0
  const marketCompleteness = signals.length > 0 ? (marketFields / (signals.length * 3)) * 100 : 0
  const confidence = clampScore(
    cohesion * 0.35
    + coreCompleteness * 0.35
    + marketCompleteness * 0.15
    + scanDepth * 0.15,
  )
  return marketCompleteness === 0 ? Math.min(confidence, 82) : confidence
}

function makeRationale(signals: KeywordSignal[], focus: string, products: string[]): string {
  const avgOpp = Math.round(average(signals.map((signal) => signal.opportunity)))
  const avgGap = Math.round(average(signals.map((signal) => signal.gap)))
  const productText = products.slice(0, 3).map(formatProduct).join(', ')
  return `${signals.length} high-performing keywords cluster around ${focus}, with ${avgOpp} avg opportunity and ${avgGap} avg gap across ${productText}.`
}

function makeEvidence(signals: KeywordSignal[], cluster: ClusterSeed, products: string[]): string[] {
  const best = signals[0]
  const strongestGap = [...signals].sort((a, b) => b.gap - a.gap)[0]
  const productText = products.slice(0, 3).map(formatProduct).join(', ')

  return [
    `${best.keyword} is the strongest keyword signal at ${Math.round(weightedKeywordScore(best))}/100.`,
    `${strongestGap.keyword} has the clearest opening with ${Math.round(strongestGap.gap)} gap score.`,
    `${cluster.secondary ? `${cluster.primary.label} plus ${cluster.secondary.label}` : cluster.primary.label} can support ${productText} without becoming product-only.`,
  ]
}

function makeListingIdeas(cluster: ClusterSeed, products: string[]): string[] {
  const focus = cluster.secondary
    ? `${cluster.secondary.label} ${cluster.primary.label}`
    : cluster.primary.label

  return products.slice(0, 4).map((product) => `${focus} ${formatProduct(product)}`)
}

function makeRisks(signals: KeywordSignal[], avgGap: number, cohesion: number, products: string[]): string[] {
  const risks: string[] = []
  if (signals.length < 4) risks.push('Thin cluster: validate with more keyword scans before building a full store.')
  if (avgGap < 45) risks.push('Competition gap is modest, so the offer needs a sharper angle.')
  if (cohesion < 65) risks.push('Theme is loose; keep the first collection tightly edited.')
  if (products.length < 2) risks.push('Product mix is narrow; test one adjacent product type before scaling.')
  return risks.length > 0 ? risks : ['No major data warning from the current keyword set.']
}

function makeStoreName(cluster: ClusterSeed, products: string[]): string {
  const primary = cluster.primary.label
  const secondary = cluster.secondary?.label
  const productHint = products.includes('wall_art')
    ? 'Print Studio'
    : products.includes('apparel')
      ? 'Goods Co.'
      : products.includes('mug')
        ? 'Gift Studio'
        : products.includes('sticker')
          ? 'Sticker Shop'
          : 'Market'

  return secondary ? `${secondary} ${primary} ${productHint}` : `${primary} ${productHint}`
}

function formatFocus(cluster: ClusterSeed): string {
  return cluster.secondary
    ? `${cluster.primary.label} / ${cluster.secondary.label}`
    : cluster.primary.label
}

function uniqueByKeyword(signals: KeywordSignal[]): KeywordSignal[] {
  const seen = new Set<string>()
  const unique: KeywordSignal[] = []
  for (const signal of signals) {
    const key = normalizeKeyword(signal.keyword)
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(signal)
  }
  return unique
}

function weightedKeywordScore(signal: KeywordSignal): number {
  return signal.opportunity * 0.62 + signal.gap * 0.32 + (signal.breakout ? 6 : 0)
}

function average(values: Array<number | null | undefined>): number {
  const usable = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (usable.length === 0) return 0
  return usable.reduce((sum, value) => sum + value, 0) / usable.length
}

function positiveAverage(values: Array<number | null | undefined>): number | undefined {
  const usable = values.filter(isPositiveNumber)
  if (usable.length === 0) return undefined
  return usable.reduce((sum, value) => sum + value, 0) / usable.length
}

function optionalAverage(values: Array<number | null | undefined>): number | undefined {
  const usable = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (usable.length === 0) return undefined
  return usable.reduce((sum, value) => sum + value, 0) / usable.length
}

function firstFinite(...values: unknown[]): number | undefined {
  for (const value of values) {
    const numeric = typeof value === 'number' ? value : Number(value)
    if (Number.isFinite(numeric)) return numeric
  }
  return undefined
}

function toScore(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? clampScore(numeric) : 0
}

function optionalScore(value: unknown): number | undefined {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? clampScore(numeric) : undefined
}

function positiveNumber(value: unknown): number | undefined {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined
}

function isPositiveNumber(value: number | null | undefined): value is number {
  return Number.isFinite(value) && Number(value) > 0
}

function maybeRound(value: number | null | undefined): number | undefined {
  return Number.isFinite(value) ? Math.round(Number(value)) : undefined
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, value))
}

function normalizeKeyword(value: string): string {
  return value
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9\s']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function formatProduct(product: string): string {
  return product.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function titleCase(value: string): string {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function makeId(value: string): string {
  return normalizeKeyword(value).replace(/\s+/g, '-')
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

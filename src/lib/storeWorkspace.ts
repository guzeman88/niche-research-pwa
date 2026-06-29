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
  creativeBrief?: StoreProductCreativeBrief
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

export interface StoreProductCreativeBrief {
  productName: string
  exactPhrase: string
  visualSubject: string
  composition: string
  palette: string
  typography: string
  styleDirection: string
  avoid: string[]
  buyer: string
  listingAngle: string
  mockupDirection: string
  seoSource: {
    primaryKeyword: string
    supportingKeywords: string[]
    productType: string
  }
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

export function createSpecificProductIdeas(store: StoreItem, keyword: StoreKeywordCandidate, productType: string, count = 6): StoreProductIdea[] {
  const now = new Date().toISOString()
  const supportingKeywords = relatedKeywordNames(store, keyword, 8)
  const productLabel = titleCase(productType.replace(/_/g, ' '))
  return Array.from({ length: count }, (_, index) => {
    const creativeBrief = createCreativeBrief(store, keyword, productType, supportingKeywords, index)
    return {
      id: `candidate-${store.slug}-${slugify(keyword.keyword)}-${slugify(productType)}-${index}`,
      storeSlug: store.slug,
      keyword: keyword.keyword,
      title: creativeBrief.productName,
      productType,
      targetBuyer: creativeBrief.buyer,
      creativeBrief,
      designBrief: [
        `${creativeBrief.productName}.`,
        `Exact words: "${creativeBrief.exactPhrase || 'no text'}".`,
        `Artwork: ${creativeBrief.visualSubject}`,
        `Composition: ${creativeBrief.composition}`,
        `Palette: ${creativeBrief.palette}`,
        `Typography: ${creativeBrief.typography}`,
        `Avoid: ${creativeBrief.avoid.join(', ')}.`,
      ].join(' '),
      mockupPrompt: `${creativeBrief.mockupDirection} Product type: ${productLabel}. Primary keyword: ${keyword.keyword}.`,
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
  const brief = product.creativeBrief
  if (brief) {
    return [
      `${product.title} is designed for ${brief.buyer}.`,
      keywordLine,
      `Artwork: ${brief.visualSubject}`,
      `Style: ${brief.styleDirection}. Palette: ${brief.palette}.`,
      `Listing angle: ${brief.listingAngle}`,
      `Details: ${brief.composition}`,
      `Store fit: ${store.brand_voice || 'focused, data-led'} with ${store.aesthetic || store.niche} styling.`,
    ].join('\n\n')
  }
  return [
    `${product.title} is designed for ${product.targetBuyer}.`,
    keywordLine,
    `Design direction: ${product.designBrief}`,
    `Store fit: ${store.brand_voice || 'focused, data-led'} with ${store.aesthetic || store.niche} styling.`,
  ].join('\n\n')
}

function createCreativeBrief(
  store: StoreItem,
  keyword: StoreKeywordCandidate,
  productType: string,
  supportingKeywords: string[],
  index: number,
): StoreProductCreativeBrief {
  const normalized = `${store.niche} ${store.aesthetic} ${store.target_audience} ${keyword.keyword} ${supportingKeywords.join(' ')}`.toLowerCase()
  const productLabel = titleCase(productType.replace(/_/g, ' '))
  const motif = conceptMotif(normalized)
  const phrase = phraseFor(keyword.keyword, motif, index)
  const hasText = allowsText(productType)
  const productName = `${hasText && phrase ? phrase : motif.title} ${productLabel}`
  return {
    productName,
    exactPhrase: hasText ? phrase : '',
    visualSubject: visualSubjectFor(keyword.keyword, motif, index),
    composition: compositionFor(productType, motif, index),
    palette: paletteFor(motif, index),
    typography: hasText ? typographyFor(motif, index) : 'No typography; make the image carry the keyword intent.',
    styleDirection: styleDirectionFor(store, motif),
    avoid: avoidListFor(motif),
    buyer: store.target_audience || buyerFor(keyword.keyword, motif),
    listingAngle: listingAngleFor(keyword, productType, motif, supportingKeywords),
    mockupDirection: mockupDirectionFor(productType, motif),
    seoSource: {
      primaryKeyword: keyword.keyword,
      supportingKeywords,
      productType,
    },
  }
}

interface ConceptMotif {
  id: string
  title: string
  objects: string[]
  setting: string
  avoid: string[]
}

function conceptMotif(context: string): ConceptMotif {
  if (/\b(dark academia|gothic|book|reader|library|literary|novel)\b/.test(context)) {
    return {
      id: 'gothic_library',
      title: 'Gothic Library',
      objects: ['arched library window', 'stacked antique books', 'raven bookend', 'ivy frame', 'brass reading lamp'],
      setting: 'moonlit Victorian reading room',
      avoid: ['skulls', 'generic candles', 'messy book piles', 'horror gore'],
    }
  }
  if (/\b(dog|cat|pet|puppy|kitten|breed|rescue)\b/.test(context)) {
    return {
      id: 'pet_portrait',
      title: 'Pet Keepsake',
      objects: ['clean pet silhouette', 'tiny paw detail', 'nameplate ribbon', 'soft collar charm', 'simple house plant'],
      setting: 'warm home entryway',
      avoid: ['cartoon clip art', 'busy paw-print backgrounds', 'generic bone icons'],
    }
  }
  if (/\b(teacher|classroom|school|educator)\b/.test(context)) {
    return {
      id: 'classroom',
      title: 'Classroom Keepsake',
      objects: ['vintage pencil cup', 'open gradebook', 'small apple stamp', 'lined paper border', 'chalk dust accent'],
      setting: 'calm after-school desk scene',
      avoid: ['rainbow overload', 'generic chalkboard clip art', 'crowded school icons'],
    }
  }
  if (/\b(wedding|bride|bridal|bridesmaid|bachelorette)\b/.test(context)) {
    return {
      id: 'bridal',
      title: 'Bridal Keepsake',
      objects: ['silk bow', 'pressed flower sprig', 'champagne coupe', 'pearl pin', 'folded note card'],
      setting: 'soft bridal suite flat lay',
      avoid: ['cheap ring clip art', 'overly pink backgrounds', 'crowded script text'],
    }
  }
  if (/\b(coffee|mug|latte|espresso|cafe)\b/.test(context)) {
    return {
      id: 'coffee',
      title: 'Coffee Ritual',
      objects: ['steaming ceramic cup', 'tiny spoon', 'coffee ring mark', 'folded napkin', 'small pastry crumb'],
      setting: 'quiet morning cafe table',
      avoid: ['generic beans pattern', 'messy splatter', 'stock cafe icons'],
    }
  }
  if (/\b(western|cowgirl|cowboy|rodeo|country)\b/.test(context)) {
    return {
      id: 'western',
      title: 'Western Keepsake',
      objects: ['tooled leather frame', 'desert wildflower', 'small horseshoe charm', 'stitched border', 'sunset ridge'],
      setting: 'warm desert ranch scene',
      avoid: ['overused cow skulls', 'muddy brown-only palette', 'cheap rodeo clip art'],
    }
  }
  if (/\b(botanical|flower|floral|plant|garden|wildflower)\b/.test(context)) {
    return {
      id: 'botanical',
      title: 'Botanical Study',
      objects: ['pressed wildflower', 'thin stem sketch', 'paper label', 'seed packet corner', 'soft leaf shadow'],
      setting: 'vintage herbarium sheet',
      avoid: ['generic floral wallpaper', 'overcrowded bouquets', 'neon colors'],
    }
  }
  return {
    id: 'quiet_gift',
    title: 'Quiet Gift',
    objects: ['small keepsake object', 'thin border frame', 'subtle symbol', 'soft paper texture', 'single accent mark'],
    setting: 'minimal gift-ready composition',
    avoid: ['generic icons', 'crowded text', 'stock-looking layout'],
  }
}

function phraseFor(keyword: string, motif: ConceptMotif, index: number): string {
  const key = titleCase(keyword).replace(/\bGift\b/g, '').trim()
  const phrases: Record<string, string[]> = {
    gothic_library: ['Booked for the Afterlife', 'The Midnight Reading Room', 'Shelf Indulgence Society', 'My Weekend Is Fully Booked', 'One More Chapter, Then Forever', 'Library After Dark'],
    pet_portrait: ['Home Is Where the Paws Are', 'Professional Treat Inspector', 'Rescue Is My Favorite Breed', 'Tiny Paws, Big Feelings', 'Walks Before Talks', 'Best Fur Friend'],
    classroom: ['Chaos Coordinator', 'Tiny Humans, Big Lessons', 'Fueled by Coffee and Sharp Pencils', 'Lesson Plans and Deep Breaths', 'Classroom Magic Maker', 'Teach Them Kindly'],
    bridal: ['Champagne Before Last Name', 'Soft Launch: Wife Era', 'Meet Me at the Chapel', 'Pearls, Promises, Party', 'Something Borrowed, Something Bold', 'Bride Energy'],
    coffee: ['Emotionally Attached to Coffee', 'First Coffee, Then Everything', 'Small Cup, Big Plans', 'Espresso Yourself Quietly', 'Morning Ritual Club', 'Fueled by Tiny Joys'],
    western: ['Desert Heart, Golden Hour', 'Rodeo Softie', 'Wildflower With Spurs', 'Country Roads and Pretty Things', 'Cowgirl State of Mind', 'Dusty Boots Club'],
    botanical: ['Bloom Where It Is Quiet', 'Pressed Petal Society', 'Soft Stems, Strong Roots', 'Garden Notes', 'Wildflower Archive', 'Tiny Bloom Club'],
    quiet_gift: [`${key} Club`, `${key} Era`, `Made for ${key}`, `${key} Keepsake`, `${key} Studio`, `${key} Mood`],
  }
  return phrases[motif.id]?.[index % phrases[motif.id].length] || phrases.quiet_gift[index % phrases.quiet_gift.length]
}

function visualSubjectFor(keyword: string, motif: ConceptMotif, index: number): string {
  const objectA = motif.objects[index % motif.objects.length]
  const objectB = motif.objects[(index + 2) % motif.objects.length]
  const objectC = motif.objects[(index + 4) % motif.objects.length]
  return `${objectA} as the hero element in a ${motif.setting}, with ${objectB} in the midground and ${objectC} as a small detail that ties back to "${keyword}".`
}

function compositionFor(productType: string, motif: ConceptMotif, index: number): string {
  const type = productType.toLowerCase()
  if (type.includes('mug') || type.includes('cup')) return `Centered wrap design: phrase arched above the ${motif.objects[0]}, artwork below, generous blank space on both sides for a clean mug preview.`
  if (type.includes('shirt') || type.includes('tee') || type.includes('apparel') || type.includes('hoodie')) return `Chest graphic layout: compact vertical stack, phrase on top, illustration centered below, no full-bleed background.`
  if (type.includes('wall') || type.includes('print') || type.includes('poster')) return index % 2 === 0
    ? `Vertical art print: large atmospheric scene, small caption near the bottom margin, museum-print spacing.`
    : `Gallery poster layout: central framed illustration with a thin border and quiet title treatment.`
  if (type.includes('sticker') || type.includes('decal')) return `Die-cut sticker layout: bold silhouette, thick clean edge, phrase tucked into the shape without tiny text.`
  if (type.includes('tote') || type.includes('bag')) return `Tall tote layout: large centered illustration, phrase beneath, strong contrast for canvas printing.`
  return `Square printable layout: balanced central illustration, phrase integrated as one readable focal point, no cluttered border.`
}

function paletteFor(motif: ConceptMotif, index: number): string {
  const palettes: Record<string, string[]> = {
    gothic_library: ['ink black, oxblood, antique gold, parchment cream', 'charcoal, forest green, brass, warm ivory'],
    pet_portrait: ['warm taupe, soft cream, muted sage, charcoal linework', 'sand, clay, deep brown, tiny sky-blue accent'],
    classroom: ['chalk green, pencil yellow, cream paper, graphite gray', 'navy, apple red, manila folder tan, clean white'],
    bridal: ['ivory, champagne, pearl gray, soft blush', 'cream, black satin, antique gold, dusty rose'],
    coffee: ['espresso brown, oat milk cream, copper, soft black', 'cafe mocha, linen, caramel, deep green'],
    western: ['sunbaked rust, denim blue, cream, antique tan', 'desert clay, faded turquoise, warm ivory, saddle brown'],
    botanical: ['sage, moss, cream, muted terracotta', 'olive, dusty rose, parchment, dark graphite'],
    quiet_gift: ['warm ivory, slate, muted blue, soft gold', 'cream, charcoal, pale green, clay accent'],
  }
  const options = palettes[motif.id] || palettes.quiet_gift
  return options[index % options.length]
}

function typographyFor(motif: ConceptMotif, index: number): string {
  const options: Record<string, string[]> = {
    gothic_library: ['engraved serif with small caps, like an old bookplate', 'thin gothic serif, readable and restrained'],
    pet_portrait: ['rounded handwritten serif, friendly but not childish', 'clean bold sans with tiny script accent'],
    classroom: ['soft chalk-style lettering, clean enough to read at thumbnail size', 'schoolbook serif paired with neat pencil-note script'],
    bridal: ['elegant high-contrast serif with minimal script accent', 'thin editorial serif, airy spacing'],
    coffee: ['casual cafe serif with compact lowercase rhythm', 'bold retro serif, slightly condensed'],
    western: ['vintage western serif without novelty spurs', 'tooled-leather inspired serif, clean and readable'],
    botanical: ['delicate botanical label serif', 'small archival serif with handwritten specimen-note accent'],
    quiet_gift: ['clean editorial serif, small caps', 'modern rounded serif with generous spacing'],
  }
  const list = options[motif.id] || options.quiet_gift
  return list[index % list.length]
}

function styleDirectionFor(store: StoreItem, motif: ConceptMotif): string {
  return `${store.aesthetic || motif.title} with premium Etsy-ready restraint, specific visual storytelling, and no generic clip-art feel`
}

function avoidListFor(motif: ConceptMotif): string[] {
  return [...motif.avoid, 'trademarked names', 'copyrighted characters', 'tiny unreadable text']
}

function buyerFor(keyword: string, motif: ConceptMotif): string {
  if (motif.id === 'gothic_library') return `book lovers searching for ${keyword} with moody literary taste`
  if (motif.id === 'pet_portrait') return `pet owners searching for ${keyword} who want a personal but polished gift`
  if (motif.id === 'classroom') return `teachers and school gift buyers searching for ${keyword}`
  return `Etsy buyers searching for ${keyword}`
}

function listingAngleFor(keyword: StoreKeywordCandidate, productType: string, motif: ConceptMotif, supportingKeywords: string[]): string {
  const supporting = supportingKeywords.slice(0, 3).join(', ')
  return `Lead with ${keyword.keyword} as the primary SEO phrase, position the ${titleCase(productType.replace(/_/g, ' '))} around ${motif.title.toLowerCase()} specificity, and use supporting keywords${supporting ? ` (${supporting})` : ''} without repeating generic broad terms.`
}

function mockupDirectionFor(productType: string, motif: ConceptMotif): string {
  const type = productType.toLowerCase()
  if (type.includes('mug') || type.includes('cup')) return `White ceramic mug on a clean desk with one ${motif.objects[1]} nearby, square Etsy thumbnail crop, readable front text.`
  if (type.includes('shirt') || type.includes('tee') || type.includes('apparel') || type.includes('hoodie')) return `Flat-lay apparel mockup with neutral fabric, centered artwork, no distracting props.`
  if (type.includes('wall') || type.includes('print') || type.includes('poster')) return `Framed print in a simple room that matches ${motif.setting}, straight-on crop, enough border for Etsy thumbnails.`
  if (type.includes('sticker') || type.includes('decal')) return `Sticker sheet or laptop mockup with white border visible and the main graphic large enough to read.`
  return `Clean product mockup with the design as the only artwork source and an Etsy-friendly square first image.`
}

function allowsText(productType: string): boolean {
  const type = productType.toLowerCase()
  return !type.includes('wall_art_no_text') && !type.includes('photo_print')
}

function relatedKeywordNames(store: StoreItem, keyword: StoreKeywordCandidate, limit = 6): string[] {
  const keywordWords = keyword.keyword.toLowerCase().split(/[^a-z0-9]+/).filter((word) => word.length > 2)
  const candidates = extractStoreKeywords(store)
    .filter((item) => item.keyword.toLowerCase() !== keyword.keyword.toLowerCase())
  const related = candidates.filter((item) => item.keyword.toLowerCase().split(/[^a-z0-9]+/).some((word) => keywordWords.includes(word)))
  return dedupe([...related, ...candidates].map((item) => item.keyword)).slice(0, limit)
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

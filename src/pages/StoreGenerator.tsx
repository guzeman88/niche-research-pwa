import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createStore, getProfitableStoreIdeas } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { fmtPrice, scoreColor } from '../lib/utils'
import type { StoreIdea, StoreIdeaKeyword } from '../lib/storeIdeas'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']

export default function StoreGenerator() {
  const queryClient = useQueryClient()
  const [savedConcepts, setSavedConcepts] = useState<Set<string>>(() => new Set())
  const [saveError, setSaveError] = useState<string>('')
  const [expandedConceptId, setExpandedConceptId] = useState<string | null>(null)

  const {
    data: profitableIdeas,
    isLoading: profitableLoading,
    error: profitableError,
  } = useQuery({
    queryKey: ['profitable-store-ideas', 12],
    queryFn: () => getProfitableStoreIdeas(12),
  })

  const concepts = useMemo(() => profitableIdeas || [], [profitableIdeas])
  const isLoading = profitableLoading
  const loadError = profitableError
  const bestConcept = concepts[0]
  const refresh = () => queryClient.invalidateQueries({ refetchType: 'active' })
  const saveStore = useMutation({
    mutationFn: (concept: StoreIdea) => createStore(toStorePayload(concept)),
    onMutate: () => setSaveError(''),
    onSuccess: (_store, concept) => {
      setSavedConcepts((current) => new Set(current).add(concept.id))
      queryClient.invalidateQueries({ queryKey: ['stores'] })
    },
    onError: (error) => {
      setSaveError(error instanceof Error ? error.message : 'Could not save this store idea.')
    },
  })

  return (
    <PullToRefresh onRefresh={refresh}>
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Store Idea Generator</h2>
          <p className="text-[13px] text-surface-200 mt-0.5">
            {concepts.length > 0
              ? `${concepts.length} source-backed store concepts with keyword clusters and listing blueprints`
              : 'Find storeable niches that can hold multiple related keywords'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {savedConcepts.size > 0 && (
            <span className="text-[11px] font-semibold text-accent-green">{savedConcepts.size} saved to My Stores</span>
          )}
        </div>
      </div>

      {saveError && (
        <div className="panel-soft mb-4 border-accent-amber/30 bg-accent-amber/10 p-3 text-[12px] font-medium text-accent-amber">
          {saveError}
        </div>
      )}

      {loadError ? (
        <div className="panel-soft p-12 text-center">
          <Icon name="wifi-off" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">Keyword data is unavailable</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">
            Connect the backend and run keyword scans before generating store ideas.
          </p>
        </div>
      ) : isLoading ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading store ideas">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="panel p-5">
              <div className="h-4 w-36 rounded bg-surface-500/40 animate-pulse" />
              <div className="mt-4 h-3 w-full max-w-xl rounded bg-surface-500/30 animate-pulse" />
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="h-16 rounded bg-surface-500/20 animate-pulse" />
                <div className="h-16 rounded bg-surface-500/20 animate-pulse" />
                <div className="h-16 rounded bg-surface-500/20 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : concepts.length > 0 ? (
        <div className="space-y-4">
          {concepts.map((concept, index) => {
            const color = COLORS[index % COLORS.length]
            const isSaved = savedConcepts.has(concept.id)
            const isSaving = saveStore.isPending && saveStore.variables?.id === concept.id
            const rankedKeywords = rankedStoreIdeaKeywords(concept)
            const keywordClusters = concept.keywordClusters || []
            const listingBlueprints = concept.listingBlueprints || []
            const recommendation = concept.storeRecommendation
            const isExpanded = expandedConceptId === concept.id
            const detailsId = `store-idea-details-${concept.id}`
            return (
              <div key={concept.id} className={`panel overflow-hidden ${isExpanded ? 'ring-1 ring-primary-300/30' : ''}`}>
                <div className="h-1" style={{ background: `linear-gradient(90deg, ${color}, ${color}80)` }} />
                <div className="min-w-0 p-4 space-y-3 sm:p-5">
                  <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                    <div className="min-w-0">
                      <h3 className="min-w-0 max-w-full break-words text-[15px] font-extrabold leading-snug text-surface-50 sm:text-[16px]">{concept.name}</h3>
                      <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-semibold text-surface-300">
                        <span className="min-w-0 break-words">{concept.focus}</span>
                        <span>{rankedKeywords.length} keywords</span>
                        <span>{concept.productTypes.slice(0, 3).join(', ')}</span>
                      </div>
                    </div>
                    <div className="flex min-w-0 flex-row flex-wrap items-center justify-end gap-2 sm:text-right lg:flex-col lg:items-end">
                        <button
                          type="button"
                          aria-label={`Add ${concept.name} to My Stores`}
                          onClick={() => saveStore.mutate(concept)}
                          disabled={isSaved || isSaving}
                          className={`mt-2 inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-[12px] font-bold transition-all duration-150 ${
                            isSaved
                              ? 'border-accent-green/25 bg-accent-green/10 text-accent-green'
                              : 'border-primary-300/30 bg-primary-400/15 text-primary-100 hover:bg-primary-400/25 disabled:cursor-wait disabled:opacity-70'
                          }`}
                        >
                          <Icon name={isSaved ? 'check-circle' : isSaving ? 'loader' : 'plus-circle'} size={14} />
                          {isSaved ? 'Added' : isSaving ? 'Saving' : 'Add to My Stores'}
                        </button>
                        <button
                          type="button"
                          aria-expanded={isExpanded}
                          aria-controls={detailsId}
                          onClick={() => setExpandedConceptId(isExpanded ? null : concept.id)}
                          className="mt-2 inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-surface-500/50 bg-surface-900/30 px-3 text-[12px] font-bold text-surface-100 transition-all duration-150 hover:bg-surface-700/45"
                        >
                          <Icon name={isExpanded ? 'arrow-up' : 'arrow-down'} size={14} />
                          {isExpanded ? 'Collapse' : 'Details'}
                        </button>
                    </div>
                  </div>

                  <RankedKeywordList keywords={rankedKeywords} totalCount={rankedKeywords.length} />

                  {isExpanded && (
                    <div id={detailsId} className="min-w-0 space-y-4 border-t border-surface-500/40 pt-4">
                      {recommendation && (
                        <div className="rounded-md border border-primary-300/20 bg-primary-400/5 p-4">
                          <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                            <div className="min-w-0">
                              <div className="section-label">Store recommendation</div>
                              <div className="mt-2 break-words text-[13px] font-semibold leading-relaxed text-surface-100">{recommendation.positioning}</div>
                              {(recommendation.qualityOptimizationPlan || recommendation.profitOptimizationPlan)?.length ? (
                                <div className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-surface-300">
                                  {(recommendation.qualityOptimizationPlan || recommendation.profitOptimizationPlan || []).slice(0, 3).map((item) => (
                                    <div key={item} className="flex min-w-0 gap-2">
                                      <Icon name="target" size={12} className="mt-0.5 flex-shrink-0 text-primary-100" />
                                      <span className="min-w-0 break-words">{item}</span>
                                    </div>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                            <div className="min-w-0 space-y-2">
                              <div className="section-label">Launch sequence</div>
                              <div className="space-y-1.5 text-[12px] text-surface-200">
                                {recommendation.launchListingIdeas.slice(0, 4).map((idea, ideaIndex) => (
                                  <div key={idea} className="flex min-w-0 items-start gap-2">
                                    <span className="w-5 flex-shrink-0 text-right text-[10px] font-extrabold tabular-nums text-primary-100">{ideaIndex + 1}</span>
                                    <span className="min-w-0 break-words">{idea}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="space-y-2">
                        <div className="section-label">Keyword clusters</div>
                        <div className="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                          {keywordClusters.slice(0, 6).map((cluster) => (
                            <div key={cluster.id} className="min-w-0 rounded-md border border-surface-500/40 bg-surface-900/15 px-3 py-2">
                              <div className="flex min-w-0 items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="break-words text-[12px] font-extrabold text-surface-100">{cluster.label}</div>
                                  <div className="mt-0.5 text-[10px] uppercase font-bold tracking-wider text-surface-400">
                                    {cluster.keywords.length} keywords
                                  </div>
                                </div>
                              </div>
                              <div className="mt-2 break-words text-[11px] text-surface-300">
                                {cluster.keywords.slice(0, 3).map((keyword) => keyword.keyword).join(' / ')}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                        <div className="min-w-0 space-y-3">
                          {listingBlueprints.length > 0 && (
                            <div className="space-y-2 pt-2">
                              <div className="section-label">Listing blueprints</div>
                              <div className="space-y-2">
                                {listingBlueprints.slice(0, 4).map((blueprint) => (
                                  <div key={blueprint.id} className="min-w-0 rounded-md border border-surface-500/40 bg-surface-900/15 px-3 py-2">
                                    <div className="flex min-w-0 items-start justify-between gap-3">
                                      <div className="min-w-0">
                                        <div className="break-words text-[12px] font-extrabold text-surface-100">{blueprint.title}</div>
                                        <div className="mt-0.5 break-words text-[11px] text-surface-300">
                                          primary: <span className="font-bold text-surface-100">{blueprint.primaryKeyword}</span>
                                        </div>
                                      </div>
                                    </div>
                                    {blueprint.supportingKeywords.length > 0 && (
                                      <div className="mt-2 break-words text-[11px] text-surface-400">
                                        supporting: {blueprint.supportingKeywords.slice(0, 4).join(', ')}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="min-w-0 space-y-3">
                          <div className="section-label">Store quality drivers</div>
                          <ul className="space-y-2 text-[12px] leading-relaxed text-surface-200">
                            {(concept.profitDrivers || concept.evidence).map((item) => (
                              <li key={item} className="flex min-w-0 gap-2">
                                <Icon name="check-circle" size={14} className="mt-0.5 flex-shrink-0 text-accent-green" />
                                <span className="min-w-0 break-words">{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      <div className="grid min-w-0 gap-5 border-t border-surface-500/40 pt-4 lg:grid-cols-3">
                        <div className="min-w-0 space-y-2">
                          <div className="section-label">First listing angles</div>
                          <div className="space-y-1.5 text-[12px] text-surface-300">
                            {concept.listingIdeas.map((idea) => (
                              <div key={idea} className="break-words">{idea}</div>
                            ))}
                          </div>
                        </div>
                        <div className="min-w-0 space-y-2">
                          <div className="section-label">Validation plan</div>
                          <div className="space-y-1.5 text-[12px] text-surface-300">
                            {recommendation?.nextValidationStep && <div className="break-words font-semibold text-surface-100">{recommendation.nextValidationStep}</div>}
                            {(concept.validationChecklist || concept.evidence).slice(0, 4).map((item) => <div key={item} className="break-words">{item}</div>)}
                          </div>
                        </div>
                        <div className="min-w-0 space-y-2">
                          <div className="section-label">Risk notes</div>
                          <div className="space-y-1.5 text-[12px] text-surface-300">
                            {concept.risks.map((risk) => <div key={risk} className="break-words">{risk}</div>)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="panel-soft p-12 text-center">
          <Icon name="layers" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">No store idea data yet</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">
            No source-backed store ideas are available from the current keyword data.
          </p>
        </div>
      )}

      {bestConcept && (
        <div className="panel-soft p-4 mt-4">
          <div className="flex items-start gap-3">
            <Icon name="target" size={18} className="mt-0.5 text-primary-200" />
            <div>
              <div className="text-[12px] font-bold text-surface-100">Best current direction: {bestConcept.name}</div>
              <div className="text-[12px] text-surface-300 mt-1">
                Start with {bestConcept.keywords.slice(0, 3).map((keyword) => keyword.keyword).join(', ')} and validate price, demand, and competition before expanding.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    </PullToRefresh>
  )
}

interface RankedKeyword extends StoreIdeaKeyword {
  strength: number | null
}

function RankedKeywordList({ keywords, totalCount }: { keywords: RankedKeyword[]; totalCount: number }) {
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="section-label">Keywords by strength</div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-surface-400">
          {keywords.length} of {totalCount}
        </div>
      </div>
      <div className="overflow-hidden rounded-md border border-surface-500/40 bg-surface-950/20">
        {keywords.map((keyword, index) => (
          <div
            key={`${keyword.keyword}-${index}`}
            className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)_3.25rem] items-center gap-3 border-b border-surface-500/30 px-3 py-2 last:border-b-0 sm:grid-cols-[2.5rem_minmax(0,1fr)_4rem_4rem_4rem]"
          >
            <div className="text-right text-[11px] font-extrabold tabular-nums text-surface-400">{index + 1}</div>
            <div className="min-w-0">
              <div className="break-words text-[12px] font-extrabold text-surface-100">{keyword.keyword}</div>
              <div className="mt-0.5 flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-surface-400">
                <span className="break-words">{keyword.product}</span>
                {keyword.estimatedRevenue ? <span>{fmtPrice(keyword.estimatedRevenue)}/mo</span> : null}
              </div>
            </div>
            <MetricValue label="strength" value={keyword.strength} />
            <MetricValue label="opp" value={keyword.opportunity} hideOnMobile />
            <MetricValue label="gap" value={keyword.gap} hideOnMobile />
          </div>
        ))}
      </div>
    </div>
  )
}

function MetricValue({ label, value, hideOnMobile = false }: { label: string; value?: number | null; hideOnMobile?: boolean }) {
  const hasValue = Number.isFinite(value)
  return (
    <div className={`text-right ${hideOnMobile ? 'hidden sm:block' : ''}`}>
      <div className={`text-[12px] font-extrabold tabular-nums ${hasValue ? scoreColor(value as number) : 'text-surface-500'}`}>
        {hasValue ? Math.round(value as number) : 'n/a'}
      </div>
      <div className="text-[9px] uppercase text-surface-500">{label}</div>
    </div>
  )
}

function rankedStoreIdeaKeywords(concept: StoreIdea): RankedKeyword[] {
  const byKeyword = new Map<string, RankedKeyword>()

  const addKeyword = (keyword: Partial<StoreIdeaKeyword> & { keyword?: string }) => {
    const name = String(keyword.keyword || '').trim()
    if (!name) return
    const key = name.toLowerCase()
    const existing = byKeyword.get(key)
    const merged: RankedKeyword = {
      keyword: existing?.keyword || name,
      product: existing?.product || keyword.product || 'Keyword',
      opportunity: bestNumber(existing?.opportunity, keyword.opportunity),
      gap: bestNumber(existing?.gap, keyword.gap),
      demand: bestNumber(existing?.demand, keyword.demand),
      margin: bestNumber(existing?.margin, keyword.margin),
      estimatedRevenue: bestNumber(existing?.estimatedRevenue, keyword.estimatedRevenue),
      revenuePerListing: bestNumber(existing?.revenuePerListing, keyword.revenuePerListing),
      avgPrice: bestNumber(existing?.avgPrice, keyword.avgPrice),
      competitionEase: bestNumber(existing?.competitionEase, keyword.competitionEase),
      marketEvidenceScore: bestNumber(existing?.marketEvidenceScore, keyword.marketEvidenceScore),
      profitabilityIndex: bestNumber(existing?.profitabilityIndex, keyword.profitabilityIndex),
      avgFavorites: bestNumber(existing?.avgFavorites, keyword.avgFavorites),
      buyerIntent: bestNumber(existing?.buyerIntent, keyword.buyerIntent),
      profitGap: bestNumber(existing?.profitGap, keyword.profitGap),
      sourceStrength: bestNumber(existing?.sourceStrength, keyword.sourceStrength),
      specificityScore: bestNumber(existing?.specificityScore, keyword.specificityScore),
      priceRange: existing?.priceRange || keyword.priceRange || null,
      strength: null,
    }
    merged.strength = keywordStrength(merged)
    byKeyword.set(key, merged)
  }

  concept.keywords.forEach(addKeyword)
  ;(concept.keywordClusters || []).forEach((cluster) => cluster.keywords.forEach(addKeyword))
  ;(concept.listingBlueprints || []).forEach((blueprint) => {
    const blueprintStrength = blueprint.profitabilityScore ?? blueprint.listingQualityScore ?? null
    addKeyword({
      keyword: blueprint.primaryKeyword,
      product: blueprint.productType,
      sourceStrength: blueprintStrength,
      buyerIntent: blueprint.buyerIntent,
      priceRange: blueprint.priceBand || null,
    })
    blueprint.supportingKeywords.forEach((keyword) => addKeyword({
      keyword,
      product: blueprint.productType,
      sourceStrength: blueprintStrength,
      buyerIntent: blueprint.buyerIntent,
    }))
  })

  return Array.from(byKeyword.values()).sort((a, b) => {
    const aStrength = a.strength ?? -1
    const bStrength = b.strength ?? -1
    if (bStrength !== aStrength) return bStrength - aStrength
    return a.keyword.localeCompare(b.keyword)
  })
}

function keywordStrength(keyword: StoreIdeaKeyword): number | null {
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

function toStorePayload(concept: StoreIdea) {
  const keywordNames = concept.keywords.map((keyword) => keyword.keyword)
  const secondary = [
    concept.focus,
    ...keywordNames.slice(0, 5),
    ...(concept.keywordClusters || []).slice(0, 4).map((cluster) => cluster.label),
  ].filter((item, index, list) => item && list.indexOf(item) === index)
  const profit = concept.profitScore ?? null
  const keywordFit = concept.storeQualityScore ?? primaryScore(concept)

  return {
    name: concept.name,
    niche: concept.focus,
    niche_secondary: secondary,
    target_audience: audienceFor(concept),
    product_types: concept.productTypes.map(toProductType),
    brand_voice: voiceFor(concept),
    aesthetic: aestheticFor(concept),
    pricing_strategy: profit && (profit >= 78 || (concept.estimatedGrossMargin || 0) >= 58) ? 'premium' : (concept.avgGap || 0) >= 60 ? 'competitive' : 'penetration',
    listing_target: profit && profit >= 78 ? 75 : 50,
    research_snapshot: {
      source: 'source_backed_store_quality_engine',
      profit_score: concept.profitScore,
      recommendation_score: concept.recommendationScore,
      store_quality_score: concept.storeQualityScore,
      commercial_potential_score: concept.commercialPotentialScore,
      keyword_fit_score: keywordFit,
      profit_grade: concept.profitGrade || null,
      quality_grade: concept.qualityGrade || null,
      niche_score: concept.nicheScore,
      specificity_score: concept.specificityScore,
      source_diversity_score: concept.sourceDiversityScore,
      product_mix_score: concept.productMixScore,
      keyword_depth_score: concept.keywordDepthScore,
      demand_score: concept.demandScore,
      margin_score: concept.marginScore,
      competition_ease: concept.competitionEase,
      confidence_score: concept.confidenceScore,
      estimated_gross_margin: concept.estimatedGrossMargin,
      estimated_monthly_revenue: concept.estimatedMonthlyRevenue,
      profitability_evidence: concept.profitabilityEvidence,
      score_breakdown: concept.scoreBreakdown,
      price_range: concept.priceRange,
      keywords: concept.keywords,
      keyword_clusters: concept.keywordClusters || [],
      listing_blueprints: concept.listingBlueprints || [],
      store_recommendation: concept.storeRecommendation,
      evidence_depth: concept.evidenceDepth,
      fee_model: concept.feeModel,
      profit_drivers: concept.profitDrivers || [],
      evidence: concept.evidence,
      risks: concept.risks,
      validation_checklist: concept.validationChecklist || [],
    },
  }
}

function toProductType(product: string): string {
  return product.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'digital_download'
}

function audienceFor(concept: StoreIdea): string {
  if (concept.anchorType === 'audience') return `${concept.focus} buyers searching for profitable ${concept.productTypes.slice(0, 3).join(', ')} collections`
  if (concept.anchorType === 'occasion') return `gift buyers and event planners looking for ${concept.focus} products`
  return `Etsy shoppers interested in ${concept.focus} across ${concept.productTypes.slice(0, 3).join(', ')}`
}

function voiceFor(concept: StoreIdea): string {
  const strength = (concept.profitScore || concept.storeQualityScore || 0) >= 72 ? 'premium' : 'focused'
  return [strength, 'data-led', 'commercial', 'giftable'].join(', ')
}

function aestheticFor(concept: StoreIdea): string {
  const focusTerms = concept.focus.split('/').map((term) => term.trim().toLowerCase()).filter(Boolean)
  return [...focusTerms, 'cohesive', 'etsy-ready'].slice(0, 5).join(', ')
}

function primaryScore(concept: StoreIdea): number {
  return Math.round(concept.profitScore ?? concept.recommendationScore ?? concept.storeQualityScore ?? concept.commercialPotentialScore ?? concept.nicheScore)
}

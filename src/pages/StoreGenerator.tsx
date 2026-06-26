import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createStore, getProfitableStoreIdeas } from '../lib/api'
import Icon, { type IconName } from '../components/Icon'
import { fmtPrice, scoreColor } from '../lib/utils'
import type { StoreIdea } from '../lib/storeIdeas'

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
  const hasAnyProfitEvidence = concepts.some((concept) => Number.isFinite(concept.profitScore))
  const isLoading = profitableLoading
  const loadError = profitableError
  const bestConcept = concepts[0]
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
          <span className="chip">{hasAnyProfitEvidence ? 'profit evidence' : concepts.length ? 'source-backed model' : 'no data'}</span>
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
            const displayScore = primaryScore(concept)
            const hasProfitEvidence = Number.isFinite(concept.profitScore)
            const scoreLabel = hasProfitEvidence ? 'profit' : 'store fit'
            const grade = hasProfitEvidence
              ? concept.profitGrade || gradeFor(displayScore)
              : concept.qualityGrade || gradeFor(displayScore)
            const evidenceDepth = concept.evidenceDepth
            const keywordClusters = concept.keywordClusters || []
            const listingBlueprints = concept.listingBlueprints || []
            const recommendation = concept.storeRecommendation
            const profitabilityEvidence = concept.profitabilityEvidence
            const isExpanded = expandedConceptId === concept.id
            const detailsId = `store-idea-details-${concept.id}`
            return (
              <div key={concept.id} className={`panel overflow-hidden ${isExpanded ? 'ring-1 ring-primary-300/30' : ''}`}>
                <div className="h-1" style={{ background: `linear-gradient(90deg, ${color}, ${color}80)` }} />
                <div className="min-w-0 p-4 space-y-3 sm:p-5">
                  <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="min-w-0 max-w-full break-words text-[15px] font-extrabold leading-snug text-surface-50 sm:text-[16px]">{concept.name}</h3>
                        {index === 0 && <span className="tag border-accent-gold/30 bg-accent-gold/10 text-accent-gold">top {scoreLabel}</span>}
                        {hasProfitEvidence || displayScore >= 62 ? (
                          <span className="tag border-primary-300/25 bg-primary-400/10 text-primary-100">
                            {hasProfitEvidence ? `grade ${grade}` : `quality ${grade}`}
                          </span>
                        ) : (
                          <span className="tag border-accent-amber/25 bg-accent-amber/10 text-accent-amber">needs validation</span>
                        )}
                        {evidenceDepth && (
                          <span className="tag border-surface-400/25 bg-surface-500/10 text-surface-200">
                            evidence {evidenceDepth.level} {evidenceDepth.score}/100
                          </span>
                        )}
                      </div>
                      <p className="mt-1 max-w-full break-words text-[11px] text-surface-300">{concept.focus}</p>
                      <p className={`mt-2 max-w-3xl break-words text-[12px] leading-relaxed text-surface-200 sm:text-[13px] ${isExpanded ? '' : 'overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]'}`}>{concept.rationale}</p>
                    </div>
                    <div className="flex min-w-0 flex-row flex-wrap items-center justify-between gap-3 lg:min-w-36 lg:flex-col lg:items-end">
                      <div className="flex shrink-0 items-baseline gap-2">
                        <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(displayScore)}`}>{displayScore}</div>
                        <div className="text-[11px] font-bold text-surface-300">{scoreLabel}</div>
                      </div>
                      <div className="flex min-w-0 flex-wrap items-center gap-2 sm:text-right lg:flex-col lg:items-end">
                        <div className="text-[10px] uppercase font-bold tracking-wider text-surface-400">
                          store quality {Math.round(concept.storeQualityScore ?? concept.nicheScore)}/100
                        </div>
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
                  </div>

                  <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
                    <Signal label="Store Fit" value={concept.storeQualityScore ?? concept.nicheScore} icon="award" />
                    <Signal label="Specificity" value={concept.specificityScore ?? concept.scoreBreakdown?.specificity} icon="target" />
                    <Signal label="Source" value={concept.sourceDiversityScore ?? concept.scoreBreakdown?.sourceDiversity ?? concept.scoreBreakdown?.keywordSourceStrength} icon="database" />
                    <Signal label="Product Fit" value={concept.productMixScore ?? concept.scoreBreakdown?.productMix} icon="package" />
                    <Signal label="Keyword Intent" value={concept.buyerIntent} icon="users" />
                    <Signal label="Evidence" value={concept.evidenceDepth?.score ?? concept.confidenceScore} icon="check-circle" />
                  </div>

                  <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,0.65fr)_minmax(0,1.35fr)]">
                    <div className="min-w-0 space-y-2">
                      <div className="section-label">Product mix</div>
                      <div className="flex min-w-0 flex-wrap gap-1.5">
                        {concept.productTypes.slice(0, isExpanded ? concept.productTypes.length : 4).map((product) => (
                          <span key={product} className="tag max-w-full whitespace-normal break-words text-left">{product}</span>
                        ))}
                      </div>
                    </div>
                    <div className="min-w-0 space-y-2">
                      <div className="section-label">Top keywords</div>
                      <div className="flex min-w-0 flex-wrap gap-1.5">
                        {concept.keywords.slice(0, isExpanded ? 8 : 4).map((keyword) => (
                          <span key={keyword.keyword} className="tag max-w-full whitespace-normal break-words text-left">{keyword.keyword}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div id={detailsId} className="min-w-0 space-y-4 border-t border-surface-500/40 pt-4">
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
                        <MarketMetric
                          label="Revenue signal"
                          value={formatRevenue(concept)}
                        />
                        <MarketMetric
                          label="Target price"
                          value={formatPriceRange(concept)}
                        />
                        <MarketMetric
                          label="Gross margin"
                          value={concept.estimatedGrossMargin ? `${concept.estimatedGrossMargin}% estimated` : 'not enough data'}
                        />
                        <MarketMetric
                          label="Evidence depth"
                          value={formatEvidenceDepth(concept)}
                        />
                        <MarketMetric
                          label="Revenue/listing"
                          value={profitabilityEvidence?.revenuePerListing ? fmtPrice(profitabilityEvidence.revenuePerListing) : 'not enough data'}
                        />
                        <MarketMetric
                          label="Profit evidence"
                          value={profitabilityEvidence ? `${profitabilityEvidence.evidenceLevel} ${profitabilityEvidence.evidenceScore}/100` : 'not enough data'}
                        />
                      </div>

                      {recommendation && (
                        <div className="rounded-md border border-primary-300/20 bg-primary-400/5 p-4">
                          <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                            <div className="min-w-0">
                              <div className="section-label">Store recommendation</div>
                              <p className="mt-2 break-words text-[13px] font-semibold leading-relaxed text-surface-100">{recommendation.positioning}</p>
                              <p className="mt-2 break-words text-[12px] leading-relaxed text-surface-300">{recommendation.qualityPriority || recommendation.profitPriority}</p>
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
                                <div className={`flex-shrink-0 text-[13px] font-extrabold tabular-nums ${metricClass(cluster.profitabilityScore ?? cluster.clusterQualityScore)}`}>
                                  {formatScore(cluster.profitabilityScore ?? cluster.clusterQualityScore)}
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
                          <div className="section-label">Keyword evidence</div>
                          <div className="space-y-2">
                            {concept.keywords.map((keyword) => (
                              <div key={keyword.keyword} className="grid min-w-0 grid-cols-[minmax(0,1fr)_2.75rem_2.75rem_2.75rem] items-center gap-2 text-[12px] sm:grid-cols-[minmax(0,1fr)_3.5rem_3.5rem_3.5rem] sm:gap-3">
                                <div className="min-w-0">
                                  <div className="break-words font-bold text-surface-100">{keyword.keyword}</div>
                                  <div className="break-words text-[10px] text-surface-400">
                                    {keyword.product}
                                    {keyword.estimatedRevenue ? ` - ${fmtPrice(keyword.estimatedRevenue)}/mo` : ''}
                                  </div>
                                </div>
                                <ScorePill label="opp" value={keyword.opportunity} />
                                <ScorePill label="gap" value={keyword.gap} />
                                <ScorePill label="margin" value={keyword.margin ?? concept.marginScore} />
                              </div>
                            ))}
                          </div>
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
                                      <div className={`flex-shrink-0 text-[13px] font-extrabold tabular-nums ${metricClass(blueprint.profitabilityScore ?? blueprint.listingQualityScore)}`}>
                                        {formatScore(blueprint.profitabilityScore ?? blueprint.listingQualityScore)}
                                      </div>
                                    </div>
                                    {blueprint.supportingKeywords.length > 0 && (
                                      <div className="mt-2 flex min-w-0 flex-wrap gap-1">
                                        {blueprint.supportingKeywords.slice(0, 4).map((keyword) => (
                                          <span key={keyword} className="tag max-w-full whitespace-normal break-words py-0.5 text-left text-[10px]">{keyword}</span>
                                        ))}
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
                          <div className="flex min-w-0 flex-wrap gap-1.5">
                            {concept.listingIdeas.map((idea) => (
                              <span key={idea} className="chip max-w-full whitespace-normal break-words py-1 text-left text-[10px]">{idea}</span>
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
  )
}

function Signal({ label, value, icon }: { label: string; value?: number | null; icon: IconName }) {
  const hasValue = Number.isFinite(value)
  return (
    <div className="min-w-0 rounded-md border border-surface-500/50 bg-surface-900/20 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <Icon name={icon} size={14} className="text-surface-300" />
        <div className={`text-[18px] font-extrabold tabular-nums ${hasValue ? scoreColor(value as number) : 'text-surface-400'}`}>
          {hasValue ? Math.round(value as number) : 'n/a'}{hasValue && <span className="text-[10px] text-surface-400">/100</span>}
        </div>
      </div>
      <div className="mt-1 break-words text-[10px] uppercase font-bold tracking-wider text-surface-400">{label}</div>
    </div>
  )
}

function MarketMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-surface-500/40 bg-surface-900/15 px-3 py-2">
      <div className="break-words text-[10px] uppercase font-bold tracking-wider text-surface-400">{label}</div>
      <div className="mt-1 break-words text-[13px] font-extrabold text-surface-50">{value}</div>
    </div>
  )
}

function ScorePill({ label, value }: { label: string; value?: number | null }) {
  const hasValue = Number.isFinite(value)
  return (
    <div className="w-11 text-right sm:w-14">
      <div className={`tabular-nums font-bold ${hasValue ? scoreColor(value as number) : 'text-surface-400'}`}>
        {hasValue ? Math.round(value as number) : 'n/a'}
      </div>
      <div className="text-[9px] uppercase text-surface-400">{label}</div>
    </div>
  )
}

function formatRevenue(concept: StoreIdea): string {
  return concept.estimatedMonthlyRevenue ? `${fmtPrice(concept.estimatedMonthlyRevenue)}/mo` : 'not enough data'
}

function formatPriceRange(concept: StoreIdea): string {
  if (concept.priceRange) {
    const suffix = concept.priceBasis === 'modeled' ? ' modeled' : ''
    return `${fmtPrice(concept.priceRange.min)}-${fmtPrice(concept.priceRange.max)}${suffix}`
  }
  return concept.avgPrice ? fmtPrice(concept.avgPrice) : 'not enough data'
}

function formatEvidenceDepth(concept: StoreIdea): string {
  if (!concept.evidenceDepth) return 'not enough data'
  const missing = concept.evidenceDepth.missing.length
  return missing > 0
    ? `${concept.evidenceDepth.level} ${concept.evidenceDepth.score}/100, ${missing} gaps`
    : `${concept.evidenceDepth.level} ${concept.evidenceDepth.score}/100`
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

function formatScore(value?: number | null): string {
  return Number.isFinite(value) ? String(Math.round(value as number)) : 'n/a'
}

function metricClass(value?: number | null): string {
  return Number.isFinite(value) ? scoreColor(value as number) : 'text-surface-400'
}

function gradeFor(score: number): string {
  if (score >= 82) return 'A'
  if (score >= 72) return 'B'
  if (score >= 62) return 'C'
  return 'D'
}

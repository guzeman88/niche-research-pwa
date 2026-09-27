import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { createStore, getProfitableStoreIdeas, getTestCandidatePortfolio } from '../lib/api'
import type { TestStoreCandidate } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { fmtPrice, scoreColor } from '../lib/utils'
import type { StoreIdea, StoreIdeaKeyword } from '../lib/storeIdeas'
import { useAppMode, type AppMode } from '../lib/appMode'
import { getUserStoreIdeas } from '../lib/userData'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']

export default function StoreGenerator() {
  const queryClient = useQueryClient()
  const { mode, isUserMode, userDataVersion } = useAppMode()
  const [savedConcepts, setSavedConcepts] = useState<Set<string>>(() => new Set())
  const [saveError, setSaveError] = useState<string>('')
  const [expandedConceptId, setExpandedConceptId] = useState<string | null>(null)
  const [expandedKeywordIds, setExpandedKeywordIds] = useState<Set<string>>(() => new Set())

  const {
    data: profitableIdeas,
    isLoading: profitableLoading,
    error: profitableError,
  } = useQuery({
    queryKey: ['profitable-store-ideas', mode, userDataVersion, 12],
    queryFn: () => isUserMode ? getUserStoreIdeas(12) : getProfitableStoreIdeas(12),
  })

  const {
    data: candidatePortfolio,
    isLoading: candidatesLoading,
    error: candidatesError,
  } = useQuery({
    queryKey: ['test-candidate-portfolio', mode, userDataVersion],
    queryFn: getTestCandidatePortfolio,
    enabled: !isUserMode,
  })

  const provisionalConcepts = useMemo(
    () => candidatePortfolio?.stores.map(testCandidateToStoreIdea) || [],
    [candidatePortfolio],
  )
  const concepts = useMemo(
    () => profitableIdeas?.length ? profitableIdeas : provisionalConcepts,
    [profitableIdeas, provisionalConcepts],
  )
  const showingTestCandidates = !isUserMode && !profitableIdeas?.length && provisionalConcepts.length > 0
  const isLoading = profitableLoading || (!isUserMode && candidatesLoading)
  const loadError = profitableError && (isUserMode || candidatesError)
  const bestConcept = concepts[0]
  const refresh = () => queryClient.refetchQueries({ type: 'active' })
  const toggleKeywordList = (conceptId: string) => {
    setExpandedKeywordIds((current) => {
      const next = new Set(current)
      if (next.has(conceptId)) next.delete(conceptId)
      else next.add(conceptId)
      return next
    })
  }
  const saveStore = useMutation({
    mutationFn: (concept: StoreIdea) => createStore(toStorePayload(concept, mode)),
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
              ? `${concepts.length} ${showingTestCandidates ? 'controlled-test' : isUserMode ? 'user-scan' : 'source-backed'} store concepts with keyword clusters`
              : isUserMode ? 'Import scored keyword scans before generating user store ideas' : 'Find storeable niches that can hold multiple related keywords'}
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

      {showingTestCandidates && candidatePortfolio && (
        <section className="panel overflow-hidden" aria-label="Candidate evidence status">
          <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="chip">Controlled tests</span>
                <span className="text-[11px] font-bold text-accent-amber">Marketplace evidence only</span>
              </div>
              <h3 className="mt-3 text-[15px] font-extrabold text-surface-50">Ranked experiments, not promised winners</h3>
              <p className="mt-1 max-w-[70ch] text-[12px] leading-relaxed text-surface-200">
                These candidates use verified Etsy supply, price, and sample depth. Scores are capped at {candidatePortfolio.score_semantics.provisional_cap}/100 until exact search volume clears the hard validation thresholds.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 lg:items-end">
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-surface-300 lg:justify-end">
                <span><strong className="text-surface-100">{candidatePortfolio.stores.length}</strong> store tests</span>
                <span><strong className="text-surface-100">{candidatePortfolio.test_plan.listing_count}</strong> listings each</span>
                <span><strong className="text-surface-100">{candidatePortfolio.test_plan.duration_days}</strong> days</span>
              </div>
              <Link className="btn-secondary min-h-9 px-3 py-2 text-[12px]" to="/evidence">
                <Icon name="database" size={14} />Connect volume and outcomes
              </Link>
            </div>
          </div>
        </section>
      )}

      {loadError ? (
        <div className="panel-soft p-12 text-center">
          <Icon name="wifi-off" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">Keyword data is unavailable</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">
            {isUserMode ? 'Import eRank, Semrush, or CSV rows with real keyword metrics first.' : 'Connect the backend and run keyword scans before generating store ideas.'}
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
            const areKeywordsExpanded = expandedKeywordIds.has(concept.id)
            const detailsId = `store-idea-details-${concept.id}`
            const keywordListId = `store-idea-keywords-${concept.id}`
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
                        {concept.validationState === 'provisional_marketplace' && (
                          <span className="text-accent-amber">Test priority {concept.testPriorityScore?.toFixed(1)}/{concept.scoreCap || 65}</span>
                        )}
                        {concept.safetyStatus && (
                          <span className={concept.safetyStatus === 'pass' ? 'text-accent-green' : 'text-accent-amber'}>
                            Safety {concept.safetyStatus}
                          </span>
                        )}
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

                  <RankedKeywordList
                    keywords={rankedKeywords}
                    totalCount={rankedKeywords.length}
                    isExpanded={areKeywordsExpanded}
                    listId={keywordListId}
                    conceptName={concept.name}
                    onToggle={() => toggleKeywordList(concept.id)}
                  />

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
            {isUserMode ? 'No user-scan store ideas are available yet.' : 'No source-backed store ideas are available from the current keyword data.'}
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
                Start with {bestConcept.keywords.slice(0, 3).map((keyword) => keyword.keyword).join(', ')}. Build the six-listing controlled test, then import 30-day Etsy outcomes before expanding.
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

function RankedKeywordList({
  keywords,
  totalCount,
  isExpanded,
  listId,
  conceptName,
  onToggle,
}: {
  keywords: RankedKeyword[]
  totalCount: number
  isExpanded: boolean
  listId: string
  conceptName: string
  onToggle: () => void
}) {
  const canToggle = totalCount > 0
  const visibleKeywords = isExpanded ? keywords : []
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="section-label">Keywords</div>
          <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-surface-400">
            {totalCount > 0
              ? (isExpanded ? `${visibleKeywords.length} shown` : `${totalCount} keywords`)
              : 'No keywords'}
          </div>
        </div>
        <button
          type="button"
          aria-expanded={isExpanded}
          aria-controls={listId}
          aria-label={`${isExpanded ? 'Collapse' : 'Show'} keywords for ${conceptName}`}
          onClick={onToggle}
          disabled={!canToggle}
          className="inline-flex min-h-8 flex-shrink-0 items-center justify-center gap-1.5 rounded-md border border-surface-500/50 bg-surface-900/30 px-2.5 text-[11px] font-bold text-surface-100 transition-all duration-150 hover:bg-surface-700/45 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Icon name={isExpanded ? 'arrow-up' : 'arrow-down'} size={13} />
          {isExpanded ? 'Hide keywords' : 'Show keywords'}
        </button>
      </div>
      {isExpanded && (
        <div id={listId} className="overflow-hidden rounded-md border border-surface-500/40 bg-surface-950/20">
          {visibleKeywords.map((keyword, index) => (
            <div
              key={`${keyword.keyword}-${index}`}
              className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)_3.25rem] items-center gap-3 border-b border-surface-500/30 px-3 py-2 last:border-b-0 sm:grid-cols-[2.5rem_minmax(0,1fr)_4rem_4rem_4rem]"
            >
              <div className="text-right text-[11px] font-extrabold tabular-nums text-surface-400">{index + 1}</div>
              <div className="min-w-0">
                <div className="break-words text-[12px] font-extrabold text-surface-100">{keyword.keyword}</div>
                <div className="mt-0.5 flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-surface-400">
                  <span className="break-words">{keyword.product}</span>
                  {keyword.estimatedRevenue != null ? <span>{fmtPrice(keyword.estimatedRevenue)}/mo</span> : null}
                </div>
              </div>
              <MetricValue label="strength" value={keyword.strength} />
              <MetricValue label="opp" value={keyword.opportunity} hideOnMobile />
              <MetricValue label="gap" value={keyword.gap} hideOnMobile />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MetricValue({ label, value, hideOnMobile = false }: { label: string; value?: number | null; hideOnMobile?: boolean }) {
  const hasValue = Number.isFinite(value)
  return (
    <div className={`text-right ${hideOnMobile ? 'hidden sm:block' : ''}`}>
      <div className={`text-[12px] font-extrabold tabular-nums ${hasValue ? scoreColor(value as number) : 'text-surface-500'}`}>
        {hasValue ? Math.round(value as number) : 'TBD'}
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
    addKeyword({
      keyword: blueprint.primaryKeyword,
      product: blueprint.productType,
      buyerIntent: blueprint.buyerIntent,
      priceRange: blueprint.priceBand || null,
    })
    blueprint.supportingKeywords.forEach((keyword) => addKeyword({
      keyword,
      product: blueprint.productType,
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
  for (const value of [keyword.profitabilityIndex, keyword.marketEvidenceScore, keyword.opportunity, keyword.gap]) {
    if (Number.isFinite(value)) return Number(value)
  }
  return null
}

function bestNumber(a?: number | null, b?: number | null): number | undefined {
  const aOk = Number.isFinite(a)
  const bOk = Number.isFinite(b)
  if (aOk && bOk) return Number(a) === Number(b) ? Number(a) : undefined
  if (aOk) return Number(a)
  if (bOk) return Number(b)
  return undefined
}

function testCandidateToStoreIdea(candidate: TestStoreCandidate): StoreIdea {
  const productsByKeyword = new Map(
    candidate.product_candidates.map((product) => [product.primary_keyword, product.product_type]),
  )
  const keywords: StoreIdeaKeyword[] = candidate.keywords.map((keyword) => ({
    keyword: keyword.keyword,
    product: productsByKeyword.get(keyword.keyword) || 'Controlled test product',
    opportunity: null,
    gap: null,
    demand: keyword.monthly_searches,
    avgPrice: keyword.avg_price_usd,
    marketEvidenceScore: keyword.test_priority_score,
    sourceStrength: null,
    scoreVersion: 'etgen-test-portfolio-v1.0.0',
    evidenceStatus: 'verified',
    sources: [keyword.source],
  }))
  const productTypes = Array.from(new Set(candidate.product_candidates.map((product) => product.product_type)))
  const clusterId = `${candidate.id}-marketplace-cluster`
  const price = candidate.evidence.median_observed_price_usd
  const listingBlueprints = candidate.product_candidates.map((product) => ({
    id: product.id,
    title: product.title,
    primaryKeyword: product.primary_keyword,
    supportingKeywords: product.supporting_keywords,
    sourceClusterId: clusterId,
    sourceClusterLabel: candidate.name,
    productType: product.product_type,
    buyerIntent: null,
    priceBand: { min: product.evidence.observed_average_price_usd, max: product.evidence.observed_average_price_usd },
    tags: [product.primary_keyword, ...product.supporting_keywords].slice(0, 13),
    profitabilityScore: null,
    listingQualityScore: null,
    profitInputs: null,
    qualityInputs: {
      etsyListingCount: product.evidence.etsy_listing_count,
      listingSamples: product.evidence.listing_samples,
      monthlySearches: product.evidence.monthly_searches,
    },
    evidenceLevel: 'Marketplace screened; demand and economics pending',
    profitRationale: 'Profitability remains TBD until exact costs, fees, and controlled-test outcomes are recorded.',
  }))
  const evidence = [
    `${candidate.evidence.keyword_count} related marketplace-evidence keywords`,
    `${candidate.evidence.median_etsy_listings.toLocaleString()} median Etsy listings`,
    `$${price.toFixed(2)} median observed price`,
    `${Math.round(candidate.evidence.average_listing_sample)} average listing samples per leading keyword`,
  ]
  return {
    id: candidate.id,
    name: candidate.name,
    focus: candidate.focus,
    anchorType: 'theme',
    keywords,
    productTypes,
    avgOpportunity: null,
    avgGap: null,
    nicheScore: null,
    storeQualityScore: null,
    recommendationScore: null,
    commercialPotentialScore: null,
    qualityGrade: null,
    specificityScore: null,
    sourceDiversityScore: null,
    productMixScore: null,
    keywordDepthScore: null,
    profitScore: null,
    rawProfitScore: null,
    profitGrade: null,
    cohesion: null,
    trendLift: null,
    demandScore: null,
    marginScore: null,
    competitionEase: null,
    buyerIntent: null,
    confidenceScore: candidate.evidence_confidence_pct,
    avgPrice: price,
    priceRange: null,
    priceBasis: 'observed',
    estimatedGrossMargin: null,
    estimatedMonthlyRevenue: null,
    profitabilityEvidence: {
      evidenceScore: candidate.evidence_confidence_pct,
      evidenceLevel: 'Controlled-test candidate; profitability not established',
      observedPriceBand: { median: price, avg: price },
      priceBasis: 'observed',
      estimatedGrossMargin: null,
      sampledMonthlyRevenue: null,
      revenuePerListing: null,
      revenueDensityScore: null,
      marketTractionScore: null,
      sellerWeaknessScore: null,
      avgListingCount: candidate.evidence.median_etsy_listings,
      avgFavorites: null,
      signalsWithDeepMarketData: candidate.keywords.filter((keyword) => keyword.sampled_listing_count >= 100).length,
      missing: candidate.blockers,
    },
    scoreBreakdown: { testPriority: candidate.test_priority_score, evidenceConfidence: candidate.evidence_confidence_pct },
    rationale: `Ranked as a ${candidate.validation_state.replace(/_/g, ' ')} experiment. The priority score is not a sales forecast.`,
    evidence,
    evidenceDepth: {
      score: candidate.evidence_confidence_pct,
      level: 'Marketplace evidence present; demand and outcomes pending',
      keywordSignals: candidate.evidence.keyword_count,
      scoredKeywords: 0,
      pricedKeywords: candidate.keywords.length,
      revenueSignals: 0,
      competitionSignals: candidate.keywords.length,
      trendSignals: 0,
      productTypes: productTypes.length,
      missing: candidate.blockers,
    },
    keywordClusters: [{
      id: clusterId,
      label: candidate.name,
      clusterType: 'theme',
      keywords,
      primaryProducts: productTypes,
      avgOpportunity: null,
      avgGap: null,
      avgDemand: candidate.evidence.combined_monthly_searches,
      competitionEase: null,
      buyerIntent: null,
      clusterQualityScore: candidate.test_priority_score,
      sourceDiversityScore: null,
      productMixScore: null,
      keywordDepthScore: null,
      marketEvidenceScore: candidate.evidence_confidence_pct,
      profitabilityScore: null,
    }],
    listingBlueprints,
    storeRecommendation: {
      positioning: `Test ${candidate.focus} for ${candidate.target_buyer}. Keep every listing inside one visual system so the experiment measures the niche rather than unrelated design styles.`,
      targetCustomer: candidate.target_buyer,
      recommendedCollections: [candidate.name],
      launchListingIdeas: candidate.product_candidates.map((product) => product.title),
      listingGenerationInputs: candidate.product_candidates.map((product) => ({
        primaryKeyword: product.primary_keyword,
        productType: product.product_type,
        evidence: product.evidence,
      })),
      keywordStrategy: {
        primaryKeywords: candidate.product_candidates.map((product) => product.primary_keyword),
        expansionKeywords: candidate.keywords.slice(6).map((keyword) => keyword.keyword),
        clusterCount: 1,
        listingBlueprintCount: listingBlueprints.length,
      },
      storeQualityScore: null,
      qualityGrade: null,
      qualityPriority: 'Keep the six listings visually consistent and vary one product or keyword angle at a time.',
      qualityOptimizationPlan: [
        `Publish exactly ${candidate.test_plan.listing_count} controlled listings.`,
        `Run the experiment for ${candidate.test_plan.duration_days} days.`,
        `Require ${candidate.test_plan.minimum_total_impressions.toLocaleString()} total impressions before judging the concept.`,
      ],
      profitPriority: 'Record exact contribution profit before approving production.',
      profitOptimizationPlan: ['Record production, shipping, Etsy fee, ad, and refund allowances for every format.'],
      validationPriorities: candidate.blockers.map((blocker) => ({ evidenceGap: blocker, action: blocker, keywords: candidate.keywords.slice(0, 6).map((keyword) => keyword.keyword) })),
      nextValidationStep: `Build the six-listing test, run it for ${candidate.test_plan.duration_days} days, then import Etsy Shop Stats.`,
    },
    feeModel: null,
    listingIdeas: candidate.product_candidates.map((product) => product.title),
    risks: [candidate.safety.note, ...candidate.blockers],
    profitDrivers: evidence,
    validationChecklist: candidate.blockers,
    validationState: candidate.validation_state,
    testPriorityScore: candidate.test_priority_score,
    scoreCap: candidate.score_cap,
    safetyStatus: candidate.safety.status,
    testPlan: candidate.test_plan,
  }
}

function toStorePayload(concept: StoreIdea, mode: AppMode) {
  const keywordNames = concept.keywords.map((keyword) => keyword.keyword)
  const secondary = [
    concept.focus,
    ...keywordNames.slice(0, 5),
    ...(concept.keywordClusters || []).slice(0, 4).map((cluster) => cluster.label),
  ].filter((item, index, list) => item && list.indexOf(item) === index)
  return {
    name: concept.name,
    niche: concept.focus,
    niche_secondary: secondary,
    target_audience: audienceFor(concept),
    product_types: concept.productTypes.map(toProductType),
    brand_voice: voiceFor(),
    aesthetic: aestheticFor(concept),
    research_snapshot: {
      app_mode: mode,
      source: mode === 'user' ? 'user_keyword_scan' : 'source_backed_store_quality_engine',
      profit_score: null,
      recommendation_score: null,
      store_quality_score: null,
      commercial_potential_score: null,
      keyword_fit_score: null,
      profit_grade: null,
      quality_grade: null,
      niche_score: null,
      specificity_score: null,
      source_diversity_score: null,
      product_mix_score: null,
      keyword_depth_score: null,
      demand_score: null,
      margin_score: null,
      competition_ease: null,
      confidence_score: null,
      estimated_gross_margin: null,
      estimated_monthly_revenue: null,
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
      validation_state: concept.validationState || null,
      test_priority_score: concept.testPriorityScore ?? null,
      score_cap: concept.scoreCap ?? null,
      safety_status: concept.safetyStatus || null,
      test_plan: concept.testPlan || null,
    },
  }
}

function toProductType(product: string): string {
  return product.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'unspecified'
}

function audienceFor(concept: StoreIdea): string {
  if (concept.anchorType === 'audience') return `${concept.focus} buyers searching for profitable ${concept.productTypes.slice(0, 3).join(', ')} collections`
  if (concept.anchorType === 'occasion') return `gift buyers and event planners looking for ${concept.focus} products`
  return `Etsy shoppers interested in ${concept.focus} across ${concept.productTypes.slice(0, 3).join(', ')}`
}

function voiceFor(): string {
  return ['focused', 'data-led'].join(', ')
}

function aestheticFor(concept: StoreIdea): string {
  const focusTerms = concept.focus.split('/').map((term) => term.trim().toLowerCase()).filter(Boolean)
  return [...focusTerms, 'cohesive', 'etsy-ready'].slice(0, 5).join(', ')
}

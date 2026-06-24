import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createStore, getOpportunities, getProfitableStoreIdeas, getTopGaps } from '../lib/api'
import Icon from '../components/Icon'
import { fmtPrice, scoreColor } from '../lib/utils'
import { generateStoreIdeas } from '../lib/storeIdeas'
import type { StoreIdea } from '../lib/storeIdeas'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']

export default function StoreGenerator() {
  const queryClient = useQueryClient()
  const [savedConcepts, setSavedConcepts] = useState<Set<string>>(() => new Set())
  const [saveError, setSaveError] = useState<string>('')

  const {
    data: profitableIdeas,
    isLoading: profitableLoading,
    error: profitableError,
  } = useQuery({
    queryKey: ['profitable-store-ideas', 12],
    queryFn: () => getProfitableStoreIdeas(12),
  })

  const { data: opps, isLoading: oppsLoading, error: oppsError } = useQuery({
    queryKey: ['opportunities', 300],
    queryFn: () => getOpportunities(undefined, 300),
    enabled: !profitableIdeas?.length,
  })
  const { data: gaps, isLoading: gapsLoading } = useQuery({
    queryKey: ['gaps', 250],
    queryFn: () => getTopGaps(250),
    enabled: !profitableIdeas?.length,
  })

  const fallbackConcepts = useMemo(() => generateStoreIdeas(opps || [], gaps || []), [opps, gaps])
  const concepts = profitableIdeas?.length ? profitableIdeas : fallbackConcepts
  const isProfitRanked = Boolean(profitableIdeas?.length)
  const isLoading = profitableLoading || (!profitableIdeas?.length && (oppsLoading || gapsLoading))
  const loadError = profitableError && oppsError
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
              ? `${concepts.length} ${isProfitRanked ? 'profit-ranked' : 'niche'} concepts built from keyword intelligence`
              : 'Find storeable niches that can hold multiple related keywords'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="chip">{isProfitRanked ? 'profit model' : 'fallback model'}</span>
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
            const profit = profitScore(concept)
            const grade = concept.profitGrade || gradeFor(profit)
            return (
              <div key={concept.id} className="panel overflow-hidden">
                <div className="h-1" style={{ background: `linear-gradient(90deg, ${color}, ${color}80)` }} />
                <div className="p-5 space-y-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-[16px] font-extrabold text-surface-50">{concept.name}</h3>
                        {index === 0 && <span className="tag border-accent-gold/30 bg-accent-gold/10 text-accent-gold">top profit fit</span>}
                        <span className="tag border-primary-300/25 bg-primary-400/10 text-primary-100">grade {grade}</span>
                      </div>
                      <p className="text-[11px] text-surface-300 mt-1">{concept.focus}</p>
                      <p className="text-[13px] text-surface-200 mt-3 max-w-3xl leading-relaxed">{concept.rationale}</p>
                    </div>
                    <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center lg:flex-col lg:items-end">
                      <div className="flex items-baseline gap-2">
                        <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(profit)}`}>{profit}</div>
                        <div className="text-[11px] font-bold text-surface-300">profit</div>
                      </div>
                      <div className="sm:text-right">
                        <div className="text-[10px] uppercase font-bold tracking-wider text-surface-400">
                          niche {concept.nicheScore}/100
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
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
                    <Signal label="Demand" value={concept.demandScore ?? concept.avgOpportunity} icon="trending-up" />
                    <Signal label="Margin" value={concept.marginScore ?? concept.estimatedGrossMargin ?? concept.avgOpportunity} icon="dollar-sign" />
                    <Signal label="Competition" value={concept.competitionEase ?? concept.avgGap} icon="target" />
                    <Signal label="Intent" value={concept.buyerIntent ?? concept.avgOpportunity} icon="users" />
                    <Signal label="Cohesion" value={concept.cohesion} icon="layers" />
                    <Signal label="Confidence" value={concept.confidenceScore ?? concept.avgGap} icon="check-circle" />
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    <MarketMetric
                      label="Revenue signal"
                      value={concept.estimatedMonthlyRevenue ? `${fmtPrice(concept.estimatedMonthlyRevenue)}/mo` : 'not enough data'}
                    />
                    <MarketMetric
                      label="Target price"
                      value={concept.priceRange ? `${fmtPrice(concept.priceRange.min)}-${fmtPrice(concept.priceRange.max)}` : fmtPrice(concept.avgPrice)}
                    />
                    <MarketMetric
                      label="Gross margin"
                      value={concept.estimatedGrossMargin ? `${concept.estimatedGrossMargin}% estimated` : `${concept.marginScore ?? concept.avgOpportunity}% proxy`}
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="section-label">Product mix</div>
                    <div className="flex flex-wrap gap-1.5">
                      {concept.productTypes.map((product) => (
                        <span key={product} className="tag">{product}</span>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(300px,0.95fr)]">
                    <div className="space-y-3">
                      <div className="section-label">Keyword evidence</div>
                      <div className="space-y-2">
                        {concept.keywords.map((keyword) => (
                          <div key={keyword.keyword} className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 text-[12px]">
                            <div className="min-w-0">
                              <div className="truncate font-bold text-surface-100">{keyword.keyword}</div>
                              <div className="text-[10px] text-surface-400">
                                {keyword.product}
                                {keyword.estimatedRevenue ? ` - ${fmtPrice(keyword.estimatedRevenue)}/mo` : ''}
                              </div>
                            </div>
                            <ScorePill label="opp" value={keyword.opportunity} />
                            <ScorePill label="gap" value={keyword.gap} />
                            <ScorePill label="margin" value={keyword.margin ?? concept.marginScore ?? 0} />
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-3">
                      <div className="section-label">Profit drivers</div>
                      <ul className="space-y-2 text-[12px] leading-relaxed text-surface-200">
                        {(concept.profitDrivers || concept.evidence).map((item) => (
                          <li key={item} className="flex gap-2">
                            <Icon name="check-circle" size={14} className="mt-0.5 flex-shrink-0 text-accent-green" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="grid gap-5 border-t border-surface-500/40 pt-4 lg:grid-cols-3">
                    <div className="space-y-2">
                      <div className="section-label">First listing angles</div>
                      <div className="flex flex-wrap gap-1.5">
                        {concept.listingIdeas.map((idea) => (
                          <span key={idea} className="chip text-[10px] py-1">{idea}</span>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="section-label">Validation plan</div>
                      <div className="space-y-1.5 text-[12px] text-surface-300">
                        {(concept.validationChecklist || concept.evidence).slice(0, 4).map((item) => <div key={item}>{item}</div>)}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="section-label">Risk notes</div>
                      <div className="space-y-1.5 text-[12px] text-surface-300">
                        {concept.risks.map((risk) => <div key={risk}>{risk}</div>)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="panel-soft p-12 text-center">
          <Icon name="layers" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">No store concepts yet</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">
            Run keyword scans to discover enough related opportunities for niche clustering.
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

function Signal({ label, value, icon }: { label: string; value: number; icon: 'trending-up' | 'dollar-sign' | 'target' | 'users' | 'layers' | 'check-circle' }) {
  return (
    <div className="rounded-md border border-surface-500/50 bg-surface-900/20 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <Icon name={icon} size={14} className="text-surface-300" />
        <div className={`text-[18px] font-extrabold tabular-nums ${scoreColor(value)}`}>
          {Math.round(value)}<span className="text-[10px] text-surface-400">/100</span>
        </div>
      </div>
      <div className="mt-1 text-[10px] uppercase font-bold tracking-wider text-surface-400">{label}</div>
    </div>
  )
}

function MarketMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-surface-500/40 bg-surface-900/15 px-3 py-2">
      <div className="text-[10px] uppercase font-bold tracking-wider text-surface-400">{label}</div>
      <div className="mt-1 text-[13px] font-extrabold text-surface-50">{value}</div>
    </div>
  )
}

function ScorePill({ label, value }: { label: string; value: number }) {
  return (
    <div className="w-14 text-right">
      <div className={`tabular-nums font-bold ${scoreColor(value)}`}>{Math.round(value)}</div>
      <div className="text-[9px] uppercase text-surface-400">{label}</div>
    </div>
  )
}

function toStorePayload(concept: StoreIdea) {
  const keywordNames = concept.keywords.map((keyword) => keyword.keyword)
  const secondary = [
    concept.focus,
    ...keywordNames.slice(0, 5),
  ].filter((item, index, list) => item && list.indexOf(item) === index)
  const profit = profitScore(concept)

  return {
    name: concept.name,
    niche: concept.focus,
    niche_secondary: secondary,
    target_audience: audienceFor(concept),
    product_types: concept.productTypes.map(toProductType),
    brand_voice: voiceFor(concept),
    aesthetic: aestheticFor(concept),
    pricing_strategy: profit >= 78 || (concept.estimatedGrossMargin || 0) >= 58 ? 'premium' : concept.avgGap >= 60 ? 'competitive' : 'penetration',
    listing_target: profit >= 78 ? 75 : 50,
    research_snapshot: {
      source: concept.profitScore ? 'profitability_engine' : 'niche_cluster_fallback',
      profit_score: profit,
      profit_grade: concept.profitGrade || gradeFor(profit),
      niche_score: concept.nicheScore,
      demand_score: concept.demandScore,
      margin_score: concept.marginScore,
      competition_ease: concept.competitionEase,
      confidence_score: concept.confidenceScore,
      estimated_gross_margin: concept.estimatedGrossMargin,
      estimated_monthly_revenue: concept.estimatedMonthlyRevenue,
      price_range: concept.priceRange,
      keywords: concept.keywords,
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
  const strength = profitScore(concept) >= 78 ? 'premium' : 'focused'
  return [strength, 'data-led', 'commercial', 'giftable'].join(', ')
}

function aestheticFor(concept: StoreIdea): string {
  const focusTerms = concept.focus.split('/').map((term) => term.trim().toLowerCase()).filter(Boolean)
  return [...focusTerms, 'cohesive', 'etsy-ready'].slice(0, 5).join(', ')
}

function profitScore(concept: StoreIdea): number {
  return Math.round(concept.profitScore ?? concept.nicheScore)
}

function gradeFor(score: number): string {
  if (score >= 82) return 'A'
  if (score >= 72) return 'B'
  if (score >= 62) return 'C'
  return 'D'
}

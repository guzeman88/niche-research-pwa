import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createStore, getOpportunities, getTopGaps } from '../lib/api'
import Icon from '../components/Icon'
import { scoreColor } from '../lib/utils'
import { generateStoreIdeas } from '../lib/storeIdeas'
import type { StoreIdea } from '../lib/storeIdeas'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']

export default function StoreGenerator() {
  const queryClient = useQueryClient()
  const [savedConcepts, setSavedConcepts] = useState<Set<string>>(() => new Set())
  const [saveError, setSaveError] = useState<string>('')
  const { data: opps, isLoading: oppsLoading, error: oppsError } = useQuery({
    queryKey: ['opportunities', 300],
    queryFn: () => getOpportunities(undefined, 300),
  })
  const { data: gaps, isLoading: gapsLoading } = useQuery({
    queryKey: ['gaps', 250],
    queryFn: () => getTopGaps(250),
  })

  const concepts = useMemo(() => generateStoreIdeas(opps || [], gaps || []), [opps, gaps])
  const isLoading = oppsLoading || gapsLoading
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
              ? `${concepts.length} niche clusters built from top keyword performance`
              : 'Find storeable niches that can hold multiple related keywords'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="chip">{concepts.length} concepts</span>
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

      {oppsError ? (
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
            return (
              <div key={concept.id} className="panel overflow-hidden">
                <div className="h-1" style={{ background: `linear-gradient(90deg, ${color}, ${color}80)` }} />
                <div className="p-5 space-y-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-[16px] font-extrabold text-surface-50">{concept.name}</h3>
                        {index === 0 && <span className="tag border-accent-gold/30 bg-accent-gold/10 text-accent-gold">best fit</span>}
                      </div>
                      <p className="text-[11px] text-surface-300 mt-1">{concept.focus}</p>
                      <p className="text-[13px] text-surface-200 mt-3 max-w-3xl leading-relaxed">{concept.rationale}</p>
                    </div>
                    <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center lg:flex-col lg:items-end">
                      <div className={`text-3xl font-extrabold tabular-nums ${scoreColor(concept.nicheScore)}`}>{concept.nicheScore}</div>
                      <div className="sm:text-right">
                        <div className="text-[10px] uppercase font-bold tracking-wider text-surface-400">niche score</div>
                        <button
                          type="button"
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

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Signal label="Opportunity" value={concept.avgOpportunity} />
                    <Signal label="Gap" value={concept.avgGap} />
                    <Signal label="Cohesion" value={concept.cohesion} />
                    <Signal label="Trend lift" value={concept.trendLift} suffix="/10" />
                  </div>

                  <div className="space-y-2">
                    <div className="section-label">Product mix</div>
                    <div className="flex flex-wrap gap-1.5">
                      {concept.productTypes.map((product) => (
                        <span key={product} className="tag">{product}</span>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
                    <div className="space-y-3">
                      <div className="section-label">Keyword evidence</div>
                      <div className="space-y-2">
                        {concept.keywords.map((keyword) => (
                          <div key={keyword.keyword} className="flex items-center gap-3 text-[12px]">
                            <div className="min-w-0 flex-1">
                              <div className="truncate font-bold text-surface-100">{keyword.keyword}</div>
                              <div className="text-[10px] text-surface-400">{keyword.product}</div>
                            </div>
                            <span className={`tabular-nums font-bold ${scoreColor(keyword.opportunity)}`}>{keyword.opportunity}</span>
                            <span className={`tabular-nums font-bold ${scoreColor(keyword.gap)}`}>{keyword.gap}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-3">
                      <div className="section-label">Why this works</div>
                      <ul className="space-y-2 text-[12px] leading-relaxed text-surface-200">
                        {concept.evidence.map((item) => (
                          <li key={item} className="flex gap-2">
                            <Icon name="check-circle" size={14} className="mt-0.5 flex-shrink-0 text-accent-green" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="grid gap-5 border-t border-surface-500/40 pt-4 lg:grid-cols-2">
                    <div className="space-y-2">
                      <div className="section-label">First listing angles</div>
                      <div className="flex flex-wrap gap-1.5">
                        {concept.listingIdeas.map((idea) => (
                          <span key={idea} className="chip text-[10px] py-1">{idea}</span>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="section-label">Validation notes</div>
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
                Start with {bestConcept.keywords.slice(0, 3).map((keyword) => keyword.keyword).join(', ')} and validate the first product collection before expanding.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Signal({ label, value, suffix = '/100' }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="rounded-md border border-surface-500/50 bg-surface-900/20 px-3 py-2">
      <div className={`text-[18px] font-extrabold tabular-nums ${scoreColor(value)}`}>
        {value}<span className="text-[10px] text-surface-400">{suffix}</span>
      </div>
      <div className="text-[10px] uppercase font-bold tracking-wider text-surface-400">{label}</div>
    </div>
  )
}

function toStorePayload(concept: StoreIdea) {
  const keywordNames = concept.keywords.map((keyword) => keyword.keyword)
  const secondary = [
    concept.focus,
    ...keywordNames.slice(0, 5),
  ].filter((item, index, list) => item && list.indexOf(item) === index)

  return {
    name: concept.name,
    niche: concept.focus,
    niche_secondary: secondary,
    target_audience: audienceFor(concept),
    product_types: concept.productTypes.map(toProductType),
    brand_voice: voiceFor(concept),
    aesthetic: aestheticFor(concept),
    pricing_strategy: concept.nicheScore >= 76 ? 'premium' : concept.avgGap >= 60 ? 'competitive' : 'penetration',
    listing_target: concept.nicheScore >= 78 ? 75 : 50,
  }
}

function toProductType(product: string): string {
  return product.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'digital_download'
}

function audienceFor(concept: StoreIdea): string {
  if (concept.anchorType === 'audience') return `${concept.focus} buyers searching for cohesive ${concept.productTypes.slice(0, 3).join(', ')} collections`
  if (concept.anchorType === 'occasion') return `gift buyers and event planners looking for ${concept.focus} products`
  return `Etsy shoppers interested in ${concept.focus} across ${concept.productTypes.slice(0, 3).join(', ')}`
}

function voiceFor(concept: StoreIdea): string {
  const strength = concept.nicheScore >= 76 ? 'premium' : 'approachable'
  return [strength, 'focused', 'data-led', 'giftable'].join(', ')
}

function aestheticFor(concept: StoreIdea): string {
  const focusTerms = concept.focus.split('/').map((term) => term.trim().toLowerCase()).filter(Boolean)
  return [...focusTerms, 'cohesive', 'etsy-ready'].slice(0, 5).join(', ')
}

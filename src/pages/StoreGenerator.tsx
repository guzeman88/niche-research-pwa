/** Store Generator — top opportunities grouped into store concepts for the PWA */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getOpportunities, getTopGaps } from '../lib/api'
import Icon from '../components/Icon'
import { scoreColor } from '../lib/utils'

const COLORS = ['#5e81ac','#a3be8c','#ebcb8b','#b48ead','#d08770','#b48ead','#14b8a6','#e11d48']

export default function StoreGenerator() {
  const { data: opps } = useQuery({ queryKey: ['opportunities', 200], queryFn: () => getOpportunities(undefined, 200) })
  const { data: gaps } = useQuery({ queryKey: ['gaps', 200], queryFn: () => getTopGaps(200) })

  // Group top opportunities by domain → store concept ideas
  const concepts = useMemo(() => {
    if (!opps || !Array.isArray(opps)) return []
    const byDomain: Record<string, any[]> = {}
    for (const o of opps.slice(0, 100)) {
      const domain = (o as any).domain || 'discovered'
      if (!byDomain[domain]) byDomain[domain] = []
      if (byDomain[domain].length < 5) byDomain[domain].push(o)
    }
    return Object.entries(byDomain)
      .filter(([_, kws]) => kws.length >= 2)
      .map(([domain, kws]) => {
        const avgOpp = kws.reduce((s: number, k: any) => s + (k.opportunity_score || 0), 0) / kws.length
        const avgGap = kws.reduce((s: number, k: any) => s + (k.gap_score || 0), 0) / kws.length
        const productTypes = inferProductTypes(domain, kws)
        return {
          name: `${domain.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())} Store`,
          domain,
          keywords: kws.map((k: any) => k.keyword),
          avgOpportunity: Math.round(avgOpp),
          avgGap: Math.round(avgGap),
          productTypes,
          rationale: `${kws.length} related keywords with ${avgOpp.toFixed(0)} avg opportunity in the ${domain.replace(/_/g, ' ')} niche`,
        }
      })
      .sort((a, b) => b.avgOpportunity - a.avgOpportunity)
  }, [opps])

  return (
    <div className="p-4 lg:p-6 space-y-5">
      <div>
        <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Store Generator</h2>
        <p className="text-[13px] text-surface-200 mt-0.5">
          {concepts.length} store concepts generated from top market opportunities
        </p>
      </div>

      {concepts.length > 0 ? (
        <div className="space-y-4">
          {concepts.map((c, i) => {
            const sc = scoreColor(c.avgOpportunity)
            const color = COLORS[i % COLORS.length]
            return (
              <div key={c.domain} className="bg-surface-700/80 border border-surface-500/60 rounded-2xl overflow-hidden">
                {/* Top accent */}
                <div className="h-1" style={{ background: `linear-gradient(90deg, ${color}, ${color}80)` }} />
                <div className="p-5 space-y-4">
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div className="min-w-0">
                      <h3 className="text-[16px] font-extrabold text-surface-50">{c.name}</h3>
                      <p className="text-[11px] text-surface-300 mt-0.5">{c.rationale}</p>
                    </div>
                    <div className={`text-2xl font-extrabold ${sc}`}>{c.avgOpportunity}</div>
                  </div>

                  {/* Keywords */}
                  <div className="flex flex-wrap gap-1.5">
                    {c.keywords.map((kw: string) => (
                      <span key={kw} className="text-[10px] px-2.5 py-1 rounded-full bg-primary-400/10 text-primary-200 font-medium border border-primary-400/15">
                        {kw}
                      </span>
                    ))}
                  </div>

                  {/* Product types */}
                  <div className="flex flex-wrap gap-1.5">
                    <span className="text-[9px] text-surface-300 uppercase font-bold tracking-wider">Suggested Products:</span>
                    {c.productTypes.map((pt: string) => (
                      <span key={pt} className="text-[10px] px-2.5 py-0.5 rounded-lg bg-surface-700/50 text-surface-200 border border-surface-500/30">
                        {pt.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>

                  {/* Gap indicator */}
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-surface-300 uppercase font-bold tracking-wider">Avg Gap:</span>
                    <div className="flex-1 h-1.5 bg-surface-700 rounded-full overflow-hidden max-w-[120px]">
                      <div className="h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-200" style={{ width: `${c.avgGap}%` }} />
                    </div>
                    <span className={`text-[11px] font-bold ${scoreColor(c.avgGap)}`}>{c.avgGap}/100</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-surface-700/40 border border-surface-500/30 rounded-2xl p-12 text-center">
          <Icon name="layers" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">No store concepts yet</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">
            Run keyword scans to discover opportunities. The generator groups related keywords into store concepts automatically.
          </p>
        </div>
      )}
    </div>
  )
}

function inferProductTypes(domain: string, keywords: any[]): string[] {
  const kwText = keywords.map((k: any) => k.keyword || '').join(' ').toLowerCase()
  const types: string[] = []
  if (/art|print|poster|wall|decor|frame|canvas/i.test(kwText) || /aesthetic|decor|home/i.test(domain)) types.push('wall_art')
  if (/shirt|tee|hoodie|sweatshirt|apparel|clothing/i.test(kwText)) types.push('apparel')
  if (/mug|cup|drink/i.test(kwText)) types.push('mug')
  if (/sticker|decal/i.test(kwText)) types.push('sticker')
  if (/tote|bag/i.test(kwText)) types.push('tote')
  if (/digital|download|printable|svg|pdf/i.test(kwText)) types.push('digital_download')
  if (/journal|notebook|planner/i.test(kwText)) types.push('journal')
  if (types.length === 0) types.push('wall_art', 'digital_download')
  return [...new Set(types || [])].slice(0, 5)
}

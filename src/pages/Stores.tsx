import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getStores } from '../lib/api'
import type { StoreItem } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { StoresSkeleton } from '../components/Skeleton'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']

export default function Stores() {
  const qc = useQueryClient()
  const { data: rawStores, isLoading, isError } = useQuery<StoreItem[]>({ queryKey: ['stores'], queryFn: getStores })
  const stores = rawStores || []
  const [selected, setSelected] = useState<string>('')
  const current = stores.find(s => s.slug === selected)
  const showDetail = !!current
  const refresh = () => { qc.invalidateQueries(); return Promise.resolve() }

  const colorFor = (slug: string) => COLORS[Math.max(0, stores.findIndex(s => s.slug === slug)) % COLORS.length]

  if (!rawStores && isLoading) return <StoresSkeleton />

  const masterList = (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-4 pb-3 border-b border-surface-600/60 bg-surface-900/45">
        <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">My Stores</h2>
        <p className="text-[12px] text-surface-300 mt-0.5">{stores.length} stores / {stores.filter(s => s.active).length} active</p>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {isLoading && <p className="text-xs text-surface-300 text-center py-12">Loading...</p>}
        {stores.map(s => {
          const color = colorFor(s.slug)
          return (
            <button
              key={s.slug}
              onClick={() => setSelected(s.slug)}
              className="w-full flex items-center gap-3.5 p-3.5 rounded-lg text-left transition-all duration-150 active:scale-[0.98]"
              style={{ backgroundColor: selected === s.slug ? color + '12' : '#303948', border: `1px solid ${selected === s.slug ? color + '38' : '#465365'}` }}
            >
              <span className="w-10 h-10 rounded-lg flex items-center justify-center text-[15px] font-extrabold flex-shrink-0"
                style={{ backgroundColor: color + '15', color, border: `1px solid ${color}30` }}>
                {s.name[0]}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[14px] font-semibold text-surface-50 truncate">{s.name}</div>
                <div className="text-[11px] text-surface-300 truncate mt-0.5">{s.niche}</div>
              </div>
              <Icon name="chevron-right" size={16} className="text-surface-400 flex-shrink-0" />
            </button>
          )
        })}
        {stores.length === 0 && !isLoading && (
          <div className="text-center py-12">
            <Icon name="package" size={40} className="text-surface-400 mx-auto mb-3" />
            <p className="text-[13px] text-surface-300">No stores yet</p>
            <p className="text-[11px] text-surface-400 mt-1">
              {isError ? 'Connect the backend to load saved stores.' : 'Saved stores will appear here.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )

  const detailView = current && (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-4 pb-4 border-b border-surface-600/60 bg-surface-900/45">
        <button onClick={() => setSelected('')} className="lg:hidden flex items-center gap-1.5 text-[13px] text-surface-200 font-medium mb-3">
          <Icon name="chevron-left" size={16} /> Back
        </button>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-extrabold text-surface-50 tracking-tight truncate">{current.name}</h2>
            <p className="text-[12px] text-surface-200 mt-0.5 line-clamp-2">{current.niche}</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <div className="flex flex-wrap gap-1.5">
          {(current.product_types || []).map(t => (
            <span key={t} className="tag py-1">
              {t.replace(/_/g, ' ')}
            </span>
          ))}
          <span className={`text-[10px] font-semibold px-2.5 py-1 rounded-md ${
            current.active ? 'bg-accent-green/10 text-accent-green border border-accent-green/20' : 'bg-accent-amber/10 text-accent-amber border border-accent-amber/20'
          }`}>
            {current.active ? 'Active' : 'Draft'}
          </span>
        </div>

        <div className="panel p-4">
          <div className="text-[10px] text-surface-300 uppercase font-bold tracking-wider mb-3">Store Details</div>
          <div className="space-y-2.5">
            <DetailRow label="Target Audience" value={current.target_audience || 'Not specified'} />
            <DetailRow label="Brand Voice" value={current.brand_voice || 'Not specified'} />
            <DetailRow label="Aesthetic Style" value={current.aesthetic || 'Not specified'} />
            <DetailRow label="Pricing Strategy" value={(current.pricing_strategy || 'competitive').replace(/^\w/, c => c.toUpperCase())} />
            <DetailRow label="Listing Target" value={`${current.listing_target} listings`} />
            <DetailRow label="Created" value={current.created_at ? new Date(current.created_at).toLocaleDateString() : 'Unknown'} />
          </div>
        </div>

        {current.niche_secondary?.length > 0 && (
          <div>
            <div className="text-[10px] text-surface-300 uppercase font-bold tracking-wider mb-2">Secondary Niches</div>
            <div className="flex flex-wrap gap-2">
              {current.niche_secondary.map(n => (
                <span key={n} className="chip bg-accent-violet/10 text-accent-violet border-accent-violet/20">
                  {n}
                </span>
              ))}
            </div>
          </div>
        )}

        <button onClick={() => setSelected('')} className="hidden lg:flex items-center gap-1.5 text-[13px] text-surface-200 font-medium">
          <Icon name="chevron-left" size={16} /> Back to stores
        </button>
      </div>
    </div>
  )

  return (
    <PullToRefresh onRefresh={refresh}>
    <>
      <div className="hidden lg:flex h-full">
        <div className="w-80 flex-shrink-0 border-r border-surface-600/60 bg-surface-900/45">
          {masterList}
        </div>
        <div className="flex-1">
          {detailView || (
            <div className="flex items-center justify-center h-full text-center px-8">
              <div className="space-y-3">
                <Icon name="package" size={48} className="text-surface-400 mx-auto" />
                <h3 className="text-[15px] font-bold text-surface-200">Select a store</h3>
                <p className="text-[13px] text-surface-400">Choose a store from the sidebar to see its details</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="lg:hidden h-full">
        {showDetail ? (
          <div className="h-full">{detailView}</div>
        ) : (
          <div className="h-full">{masterList}</div>
        )}
      </div>
    </>
    </PullToRefresh>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-start gap-4">
      <span className="text-[11px] text-surface-300 flex-shrink-0">{label}</span>
      <span className="text-[13px] text-surface-50 text-right font-medium">{value}</span>
    </div>
  )
}

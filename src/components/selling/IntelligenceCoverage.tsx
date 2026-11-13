import {useQuery} from '@tanstack/react-query'
import {intelligenceRequest as request, type ReferenceListing} from '../../lib/salesIntelligence'
import {number, text} from '../../lib/sellingProducts'

interface Coverage {
  listings: number; metadata: number; reference_listings: number; observations: number; outcomes: number; canonical_shops: number
  sample_scope: string; history: {status?: string; cursor?: number; maximum?: number}
  cohorts: Array<{source_id: string; basis: string; unit: string; listings: number; readings: number; latest_capture: string}>
  catalog_types: Array<{product_type: string; listings: number; canonical_shops_known: number}>
}
interface Ranked {
  items: Array<{listing_id: string; metadata: ReferenceListing | null; score: number; center: number; groups: number; period_end: string; factors: Record<string, number>}>
  formula: string; basis: string; limitations: string
}

export function IntelligenceCoverage() {
  const result = useQuery({queryKey: ['intelligence-coverage'], queryFn: () => request<Coverage>('/coverage'), retry: false, refetchInterval: 30000})
  if (result.isPending) return <p role="status" className="text-sm">Loading research coverage…</p>
  if (result.error) return <p role="alert" className="text-sm text-accent-amber">{result.error.message}</p>
  const data = result.data
  return <div className="space-y-5 text-sm">
    <div><h3 className="text-base font-semibold">What the collected evidence covers</h3><p className="mt-2 max-w-3xl leading-relaxed text-surface-200">{data.sample_scope}. Readings are not unique listings, and saved catalog records do not establish sales.</p></div>
    <p className="tabular-nums">{number(data.listings)} catalog listings · {number(data.metadata)} historical metadata records · {number(data.canonical_shops)} identified shops</p>
    <p className="tabular-nums">{number(data.reference_listings)} listings with provider references · {number(data.observations)} reference readings · {number(data.outcomes)} actual outcome records</p>
    <p className="text-surface-200">Historical catch-up: {text(data.history.status || 'not started')}{data.history.cursor !== undefined ? ` · ${number(data.history.cursor)} / ${number(data.history.maximum ?? 0)} source observation IDs` : ''}. Gaps between IDs are not collected-row counts.</p>
    <ul className="divide-y divide-surface-700">{data.catalog_types.map(row => <li className="py-3" key={row.product_type}>{text(row.product_type)} · {number(row.listings)} listings · {number(row.canonical_shops_known)} with a canonical shop ID</li>)}</ul>
    <h4 className="font-semibold">Reference coverage by source and reporting basis</h4>
    {data.cohorts.length === 0 && <p className="text-surface-200">No provider reference measurements have been acquired.</p>}
    <ul className="divide-y divide-surface-700">{data.cohorts.map(row => <li className="py-3" key={`${row.source_id}-${row.basis}-${row.unit}`}>{row.source_id} · {text(row.basis)} · {row.unit}<p className="mt-1 text-surface-200">{number(row.listings)} listings / {number(row.readings)} readings · latest capture {new Date(row.latest_capture).toLocaleString()}</p></li>)}</ul>
  </div>
}

export function IntelligenceOpportunities({onSelect}: {onSelect: (id: string) => void}) {
  const result = useQuery({queryKey: ['intelligence-ranking'], queryFn: () => request<Ranked>('/opportunities'), retry: false})
  if (result.isPending) return <p role="status" className="text-sm">Comparing recent reference opportunities…</p>
  if (result.error) return <p role="alert" className="text-sm text-accent-amber">{result.error.message}</p>
  const data = result.data
  return <div className="space-y-4 text-sm">
    <h3 className="text-base font-semibold">Opportunities supported by reference estimates</h3>
    <p className="max-w-3xl leading-relaxed text-surface-200">{data.basis}. {data.limitations}</p>
    <details><summary className="cursor-pointer font-semibold">How this provisional ranking works</summary><p className="mt-3 max-w-3xl leading-relaxed text-surface-200">{data.formula}. Source diversity and agreement are evidence descriptors, not proof of accuracy. Customer needs and original improvements are evaluated in the opportunity workspace.</p></details>
    {data.items.length === 0 && <p className="py-4 text-surface-200">No compatible recent 30-day purchase estimates are available to rank. Collect references or import a permitted export first.</p>}
    <ol className="divide-y divide-surface-700">{data.items.map(item => <li className="py-5" key={item.listing_id}><button className="text-left font-semibold underline underline-offset-4" onClick={() => onSelect(item.listing_id)}>{item.metadata?.title || `Listing ${item.listing_id}`}</button><p className="mt-2">Provider center {number(item.center)} purchases / 30 days · {item.groups} method groups · provisional score {number(item.score)}</p><p className="mt-2 text-xs text-surface-300">Period ended {new Date(item.period_end).toLocaleString()} · estimated demand, not verified orders</p><details className="mt-3"><summary className="cursor-pointer">Score factors</summary><ul className="mt-2 space-y-1 text-surface-200">{Object.entries(item.factors).map(([key, value]) => <li key={key}>{text(key)}: {number(value)}</li>)}</ul></details></li>)}</ol>
  </div>
}

import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {intelligenceRequest as request, type AutomaticEstimate} from '../../lib/salesIntelligence'
import {number, text} from '../../lib/sellingProducts'
import ShopAllocations from './ShopAllocations'

interface Result {items: AutomaticEstimate[]; summary: {tracked?: number; estimated?: number; at?: string}; assumptions: string; schedule: string; panel_limit: number}
const date = (value?: string) => value ? new Date(value).toLocaleString() : 'Not yet captured'

export default function AutomaticEstimates({onSelect}: {onSelect: (id: string) => void}) {
  const [method, setMethod] = useState('reviews')
  const [onlyEstimates, setOnlyEstimates] = useState(false)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('')
  const query = useQuery({queryKey: ['automatic-sales-estimates'], queryFn: () => request<Result>('/estimates'), retry: false, refetchInterval: 30000})
  const action = async (path: string) => {
    setBusy(true); setError(''); setMessage('')
    try {const result = await request<{reason?: string}>(path, {}); setMessage(result.reason || 'Calculation queued. Results update automatically; Etsy requests keep their normal schedule.'); await query.refetch()}
    catch (cause) {setError(cause instanceof Error ? cause.message : 'Request failed. Try again.')} finally {setBusy(false)}
  }
  const data = query.data
  const items = (data?.items || []).filter(item => !onlyEstimates || item.value != null).sort((a, b) => (b.value ?? -1) - (a.value ?? -1) || a.listing_id.localeCompare(b.listing_id))
  return <section aria-label="Automatic EtGen estimates">
    <h3 className="text-base font-semibold">Our automatic sales estimates</h3>
    <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">EtGen tracks a focused panel and runs its own estimator. Provider feeds are optional comparisons. Estimates are unvalidated; review scenarios use review dates, so purchases may have happened earlier.</p>
    <div role="group" aria-label="Estimation method" className="mt-4 flex flex-wrap gap-3">
      <button className={method === 'reviews' ? 'btn-primary' : 'btn-secondary'} aria-pressed={method === 'reviews'} aria-controls="review-estimates" onClick={() => setMethod('reviews')}>Review scenarios</button>
      <button className={method === 'shop' ? 'btn-primary' : 'btn-secondary'} aria-pressed={method === 'shop'} aria-controls="shop-allocation-estimates" onClick={() => setMethod('shop')}>Shop-anchored allocations</button>
    </div>
    {method === 'reviews' && data && <p className="mt-3 text-sm tabular-nums text-surface-200">{number(data.summary.estimated)} products with estimates · {number(data.summary.tracked)} tracked · calculated {date(data.summary.at)}</p>}
    <div className="my-5 flex flex-wrap items-end gap-4">
      <form className="flex min-w-0 flex-wrap items-end gap-3" onSubmit={event => {event.preventDefault(); const id = String(new FormData(event.currentTarget).get('listing_id') || ''); void action(`/listings/${id}/track`)}}>
        <label className="text-sm">Track a discovered Etsy listing<input className="input mt-2 block w-full" name="listing_id" required inputMode="numeric" pattern="[0-9]{1,30}" /></label>
        <button className="btn-secondary" disabled={busy}>Track product</button>
      </form>
      <button className="btn-secondary" disabled={busy} onClick={() => void action('/estimates/refresh')}>Recalculate estimates</button>
      {method === 'reviews' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyEstimates} onChange={event => setOnlyEstimates(event.target.checked)} />With estimates only</label>}
    </div>
    {message && <p role="status" className="my-4 text-sm text-surface-200">{message}</p>}
    {(error || query.error) && <div role="alert" className="my-4 text-sm text-accent-amber"><p>{error || query.error?.message}</p><button className="btn-secondary mt-3" onClick={() => void query.refetch()}>Retry estimates</button></div>}
    <div id="shop-allocation-estimates" hidden={method !== 'shop'}>{method === 'shop' && <ShopAllocations onSelect={onSelect} />}</div>
    <div id="review-estimates" hidden={method !== 'reviews'}>
    {query.isPending && <p role="status" className="py-4 text-sm">Loading our estimates…</p>}
    {data && items.length === 0 && <p className="py-4 text-sm text-surface-200">{onlyEstimates ? 'No tracked product has enough usable evidence yet. Show all products to inspect collection status.' : 'The backend will select a 30-product panel from discovery. You can also track a discovered product above. Collection uses the existing free allowance.'}</p>}
    <ul className="divide-y divide-surface-700">{items.map(item => <li key={item.listing_id} className="py-5">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-3">
        <button className="min-w-0 flex-1 break-words text-left text-sm font-semibold underline-offset-4 hover:underline" onClick={() => onSelect(item.listing_id)}>{item.listing?.title || item.collection?.title || `Listing ${item.listing_id}`}</button>
        <a className="text-sm underline underline-offset-4" href={`https://www.etsy.com/listing/${item.listing_id}`} target="_blank" rel="noreferrer">View listing</a>
      </div>
      <p className="mt-2 text-sm text-surface-200">{item.value == null ? `Sales unknown · ${text(item.status)}` : `${number(item.value)} estimated purchases / 30 days · ${item.status === 'uncalibrated_review_scenario' ? 'uncalibrated review scenario' : 'provisional model'}`}</p>
      {item.listing && !item.listing.title && <p className="mt-2 text-sm text-surface-200">Listing details are pending the next permitted API check. The review evidence identifies this product by its Etsy listing ID.</p>}
      {item.review_scenarios && Object.entries(item.review_scenarios).map(([days, scenario]) => <p key={days} className="mt-2 text-sm tabular-nums text-surface-200">{days}-day review activity: {number(scenario.review_count)} reviews · {scenario.value == null ? 'purchase estimate unknown' : `${number(scenario.value)} central scenario; ${number(scenario.low)}–${number(scenario.high)} under different review-rate assumptions`}</p>)}
      {item.review_evidence && !item.review_evidence.complete && <p className="mt-2 text-sm text-surface-200">{number(item.review_evidence.observed_reviews)} reviews observed in a partial or unverified response. A complete-window estimate is unavailable.</p>}
      {item.review_evidence?.complete && item.review_evidence.observed_reviews === 0 && <p className="mt-2 text-sm text-surface-200">No reviews observed in the requested 30-day API window. Purchases remain unknown.</p>}
      <p className="mt-2 text-xs text-surface-300">{item.listing?.shop || item.collection?.shop || 'Shop unknown'} · captured {date(item.captured_at)} · {text(item.collection?.check_status || 'not_checked')}</p>
    </li>)}</ul>
    {data && <details className="mt-5"><summary className="cursor-pointer text-sm font-semibold">How these estimates work</summary><p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">{data.assumptions} A missing review response or no recent reviews does not establish zero purchases. The panel includes popular and quieter products from a bounded saved-catalog sample; its rankings do not represent the whole market.</p><p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">{data.schedule} Up to {data.panel_limit} products can be tracked. Errors, quota limits and pauses can delay refreshes.</p></details>}
    </div>
  </section>
}

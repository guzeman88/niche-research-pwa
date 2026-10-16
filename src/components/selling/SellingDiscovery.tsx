import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { sellingRequest, number, type Detail } from '../../lib/sellingProducts'
import KeywordRightsFlag from '../KeywordRightsFlag'

interface Candidate {
  listing_id: string; title: string; shop: string; url: string; image_url?: string
  keyword: string; observed_at: string; signal: string; fingerprint: string
  opportunity_id: string | null; favorites: number | null; check_status: string
  purchase_report: { raw_message: string; observed_at: string; window_hours: number; unit: string } | null
  price: {value: number | null; currency: string} | null
}
interface Discovery {
  items: Candidate[]; total: number; page: number; limit: number
  counts: { indexed: number; purchase_reports: number; review_activity: number }
  access: {status: string; scopes: string[]}; catalog: Record<string, string>
  last_run: {status: string; completed_at: string | null} | null
}
const date = (value: string) => new Date(value).toLocaleString()

export default function SellingDiscovery({ onInvestigate }: {onInvestigate: (id: string) => void}) {
  const [search, setSearch] = useState(''), [q, setQ] = useState('')
  const [signal, setSignal] = useState('all'), [page, setPage] = useState(0)
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const query = useQuery({queryKey: ['selling-discovery', q, signal, page],
    queryFn: () => sellingRequest<Discovery>(`/discovery?${new URLSearchParams({q, signal, page: String(page)})}`),
    retry: false, refetchInterval: 15000})
  useEffect(() => {
    const timer = setTimeout(() => {setQ(search); setPage(0)}, 300)
    return () => clearTimeout(timer)
  }, [search])
  const refresh = async () => {
    setError(''); setRefreshing(true); setNotice('Refreshing saved catalog…')
    try {
      await sellingRequest('/discovery/refresh', {})
      await query.refetch()
      setNotice('Refresh queued. Results update automatically as collection finishes.')
    } catch (cause) {setError(cause instanceof Error ? cause.message : 'Refresh failed. Try again.')}
    finally {setRefreshing(false)}
  }
  const investigate = async (item: Candidate) => {
    setBusy(item.listing_id); setError('')
    try {
      const result = await sellingRequest<Detail>(`/discovery/${item.listing_id}/investigate`, {expected_fingerprint: item.fingerprint})
      onInvestigate(result.id)
      setNotice(`Opened ${item.title} in your opportunity watchlist below.`)
      await query.refetch()
      document.getElementById('opportunity-workspace')?.scrollIntoView({behavior: 'instant', block: 'start'})
      document.getElementById('opportunity-workspace')?.focus({preventScroll: true})
    } catch (cause) {setError(cause instanceof Error ? cause.message : 'Could not investigate this listing. Refresh and try again.')}
    finally {setBusy('')}
  }
  const data = query.data
  return <section aria-label="Product discovery" className="my-8 border-b border-surface-600 pb-8">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h2 className="text-lg font-semibold">Discover products</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">Browse real listings from your collected keywords. Investigate a product to compare its evidence and develop an original improvement.</p></div>
      <button type="button" className="btn-secondary" disabled={refreshing} onClick={() => void refresh()}>{refreshing ? 'Refreshing catalog…' : 'Refresh discovery'}</button>
    </div>
    {data && <>
      <p className="mt-4 text-sm tabular-nums text-surface-200">{number(data.counts.indexed)} indexed listings · {number(data.counts.purchase_reports)} recent purchase reports · {number(data.counts.review_activity)} with recent reviews</p>
      {data.access.status !== 'recorded' && <details className="mt-4 max-w-3xl text-sm text-surface-200">
        <summary className="cursor-pointer font-semibold text-surface-100">Purchase collection needs verified Etsy access</summary>
        <p className="mt-3 leading-relaxed">Saved catalog refresh is automatic. New Etsy analytics and listing-page collection are waiting for written authorization. A working API key does not establish that permission. Listings with no purchase report have unknown sales.</p>
        <a href="https://www.etsy.com/legal/api/" target="_blank" rel="noreferrer" className="mt-2 inline-block underline underline-offset-4">Etsy API terms</a>
      </details>}
    </>}
    <div className="my-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
      <label className="min-w-0 text-sm">Search products, shops or keywords<input className="input mt-2 w-full" type="search" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /></label>
      <label className="text-sm">Activity evidence<select className="input mt-2 w-full" value={signal} onChange={event => {setSignal(event.target.value); setPage(0)}}>
        <option value="all">All discovered listings</option><option value="purchase_report">Recent purchase reports</option><option value="review_activity">Reviews in the past 30 days</option><option value="unknown">Sales unknown</option>
      </select></label>
    </div>
    {notice && <p role="status" className="mb-4 text-sm text-surface-200">{notice}</p>}
    {(error || query.error) && <div role="alert" className="my-4 text-sm text-accent-amber"><p>{error || query.error?.message}</p><button type="button" className="btn-secondary mt-3" onClick={() => void query.refetch()}>Retry discovery</button></div>}
    {query.isPending && <p role="status" className="py-6 text-sm text-surface-200">Loading discovered products…</p>}
    {data && !data.items.length && <div className="max-w-2xl py-6"><h3 className="font-semibold">{signal === 'purchase_report' ? 'No recent purchase reports' : 'No products match this view'}</h3><p className="mt-3 text-sm leading-relaxed text-surface-200">{signal === 'purchase_report' ? 'Current purchase evidence has not been collected for these listings. Choose All discovered listings to explore the catalog; their sales remain unknown.' : data.counts.indexed ? 'Change the search or activity filter to see more listings.' : 'Refresh discovery to read your saved keyword catalog. If the catalog is unavailable, check the local collector installation.'}</p></div>}
    {data && !!data.items.length && <ul className="divide-y divide-surface-700 border-y border-surface-600" aria-label="Discovered listings">
      {data.items.map(item => <li key={item.listing_id} className="flex flex-wrap items-start gap-4 py-5 sm:flex-nowrap">
        {item.image_url && <img src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-20 w-20 shrink-0 rounded-sm object-cover" />}
        <div className="min-w-0 flex-1 basis-48">
          <a href={item.url} target="_blank" rel="noreferrer" className="break-words text-base font-semibold text-surface-50 hover:underline focus-visible:outline-2 focus-visible:outline-primary-200">{item.title}</a>
          <p className="mt-2 break-words text-sm text-surface-200">{item.shop || 'Shop not recorded'} · {item.keyword}{item.price && ` · ${number(item.price.value)} ${item.price.currency}`}</p>
          <p className="mt-3 text-sm font-semibold">{item.signal === 'purchase_report' ? 'Recent purchase report' : item.signal === 'review_activity' ? 'Recent review activity · purchase timing unknown' : 'Sales unknown'}</p>
          {item.purchase_report && <p className="mt-2 text-sm leading-relaxed text-surface-200">“{item.purchase_report.raw_message}” · captured {date(item.purchase_report.observed_at)}{item.signal !== 'purchase_report' && ' · historical report'}</p>}
          <p className="mt-2 text-xs leading-relaxed text-surface-300">Observed {date(item.observed_at)} · {item.favorites == null ? 'Favorites unknown' : `${number(item.favorites)} favorites`}</p>
          {item.check_status !== 'not_checked' && <p className="mt-1 text-xs text-surface-300">Source check: {item.check_status.replace(/_/g, ' ')}</p>}
          <KeywordRightsFlag keyword={`${item.title} ${item.keyword}`.slice(0, 1000)} />
        </div>
        <button type="button" className="btn-primary text-surface-950! hover:bg-primary-400!" disabled={!!busy} onClick={() => void investigate(item)} aria-label={`${item.opportunity_id ? 'Open research for' : 'Investigate'} ${item.title}`}>{busy === item.listing_id ? 'Opening…' : item.opportunity_id ? 'Open research' : 'Investigate'}</button>
      </li>)}
    </ul>}
    {data && <div className="mt-4 flex flex-wrap items-center justify-between gap-4 text-sm">
      <p className="text-surface-200">{data.total ? `${number(page * data.limit + 1)}–${number(Math.min((page + 1) * data.limit, data.total))} of ${number(data.total)}` : '0 matching listings'}{data.catalog.catalog_synced_at && ` · refreshed ${date(data.catalog.catalog_synced_at)}`}</p>
      <div className="flex gap-3"><button type="button" className="btn-secondary" disabled={!page} onClick={() => setPage(value => value - 1)}>Previous products</button><button type="button" className="btn-secondary" disabled={(page + 1) * data.limit >= data.total} onClick={() => setPage(value => value + 1)}>Next products</button></div>
    </div>}
    <p className="mt-4 max-w-3xl text-xs leading-relaxed text-surface-300">Purchase reports retain the source’s rolling window and buyer units; they are not independently verified orders. Reviews and favorites support research but do not prove current sales. Missing evidence stays unknown.</p>
  </section>
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { readConnection, saveConnection } from '../lib/operatorConnection'
import { sellingRequest, text, families, values, type Overview, type Detail } from '../lib/sellingProducts'
import SellingOpportunity from '../components/selling/SellingOpportunity'
import KeywordRightsFlag from '../components/KeywordRightsFlag'
import SellingDiscovery from '../components/selling/SellingDiscovery'
import SalesIntelligence from '../components/selling/SalesIntelligence'

export default function SellingProducts() {
  const initial = readConnection()
  const [url, setUrl] = useState(initial.url || (['localhost', '127.0.0.1'].includes(location.hostname) ? 'http://127.0.0.1:18020' : ''))
  const [token, setToken] = useState(initial.token), [connected, setConnected] = useState(Boolean(initial.url))
  const [version, setVersion] = useState(0), [selected, setSelected] = useState('')
  const [create, setCreate] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [search, setSearch] = useState(''), [stage, setStage] = useState('')
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['selling-products', version], queryFn: () => sellingRequest<Overview>(), enabled: connected, retry: false })
  const items = query.data?.items.filter(item => (!stage || item.stage === stage) && `${item.name} ${item.keyword} ${item.audience}`.toLowerCase().includes(search.toLowerCase())) || []
  const refresh = async () => { await query.refetch(); await client.invalidateQueries({ queryKey: ['selling-opportunity'] }) }
  return <main className="page min-h-screen bg-surface-950 text-surface-50">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold">Selling products</h1><p className="mt-3 max-w-2xl text-base leading-relaxed text-surface-200">Find commercial activity, understand what buyers need, and plan an original product that improves the offer.</p></div>
      <Link className="btn-secondary" to="/validation">Product validation</Link>
    </header>
    <details className="my-6 border-y border-surface-600 py-4" open={!connected}>
      <summary className="cursor-pointer text-sm font-semibold">Private research connection</summary>
      <form className="mt-4 grid max-w-3xl gap-4 sm:grid-cols-2" onSubmit={event => {
        event.preventDefault(); try { saveConnection({ url, token }); setConnected(true); setVersion(v => v + 1); setError('') } catch (cause) { setError(String(cause)) }
      }}><label className="text-sm">Research server address<input className="input mt-2 w-full" type="url" required value={url} onChange={event => setUrl(event.target.value)} /></label>
        <label className="text-sm">Operator token · remote access only<input className="input mt-2 w-full" type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
        <button className="btn-secondary w-fit">Connect workspace</button></form>
    </details>
    {error && <p role="alert" className="my-4 text-sm text-accent-amber">{error}</p>}
    {query.isFetching && !query.data && <div className="space-y-4 py-6" aria-busy="true" aria-label="Loading selling-product research"><div className="h-8 max-w-sm animate-pulse rounded-sm bg-surface-700" /><div className="h-32 animate-pulse rounded-sm bg-surface-800" /></div>}
    {query.error && <div role="alert" className="my-6 space-y-3"><p>{query.error.message}</p><button className="btn-secondary" onClick={() => void refresh()}>Retry connection</button></div>}
    {query.data && <>
      <SalesIntelligence key={`intelligence:${version}`} onInvestigate={id => {setSelected(id); void refresh()}} />
      <SellingDiscovery key={version} onInvestigate={id => {setSelected(id); void refresh()}} />
      <section id="opportunity-workspace" tabIndex={-1} aria-label="Opportunity workspace" className="outline-none">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h2 className="text-lg font-semibold">Opportunity watchlist</h2><p className="mt-2 text-sm text-surface-200">{query.data.items.length} saved opportunities · ranked by evidence type and independent selling shops</p></div>
        <div className="flex flex-wrap gap-3"><button className="btn-secondary" onClick={() => void refresh()} disabled={query.isFetching}>Refresh analysis</button><button className="btn-primary" onClick={() => setCreate(!create)}>New opportunity</button></div>
      </div>
      {create && <form aria-label="New selling-product opportunity" className="my-6 max-w-3xl space-y-4 border-y border-surface-600 py-6" onSubmit={async event => {
        event.preventDefault(); setBusy(true); setError('')
        try { const item = await sellingRequest<Detail>('/opportunities', values(event.currentTarget)); setSelected(item.id); setCreate(false); await refresh() }
        catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the opportunity.') } finally { setBusy(false) }
      }}><h3 className="text-base font-semibold">What product market do you want to investigate?</h3>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Opportunity name<input className="input mt-2 w-full" name="name" required minLength={3} maxLength={140} /></label><label className="text-sm">Buyer keyword<input className="input mt-2 w-full" name="keyword" required minLength={3} maxLength={160} /></label>
          <label className="text-sm">Product family<select className="input mt-2 w-full" name="family">{families.map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label><label className="text-sm">Audience · optional<input className="input mt-2 w-full" name="audience" maxLength={500} /></label></div>
        <label className="block text-sm">Buyer task · optional<textarea className="input mt-2 w-full" name="buyer_task" maxLength={1000} rows={2} /></label>
        <div className="flex gap-3"><button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save opportunity'}</button><button className="btn-secondary" type="button" onClick={() => setCreate(false)}>Cancel</button></div>
      </form>}
      <div className="my-5 flex flex-wrap gap-4"><label className="min-w-0 flex-1 text-sm">Find an opportunity<input className="input mt-2 w-full" type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><label className="text-sm">Stage<select className="input mt-2 w-full" value={stage} onChange={event => setStage(event.target.value)}><option value="">All stages</option>{['watching', 'shortlisted', 'archived'].map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label></div>
      <div className="grid items-start gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside aria-label="Saved opportunities" className="min-w-0 border-y border-surface-600">
          {!items.length && <p className="py-5 text-sm leading-relaxed text-surface-200">{query.data.items.length ? 'No opportunities match these filters.' : 'Start with a product market. Add saved listings and dated evidence to compare all five research methods.'}</p>}
          {items.map(item => <div className="border-b border-surface-700 py-4 last:border-0" key={item.id}>
            <button className="w-full break-words rounded-sm text-left focus-visible:outline-2 focus-visible:outline-primary-200" aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}><span className={`block font-semibold ${selected === item.id ? 'text-primary-100' : ''}`}>{item.name}</span><span className="mt-2 block text-sm text-surface-200">{text(item.evidence_level)} · {item.listing_count} listings</span><span className="mt-1 block text-xs text-surface-300">{text(item.stage)}{item.brief_stale ? ' · Brief needs review' : item.has_brief ? ' · Brief saved' : ''}</span></button>
            <KeywordRightsFlag keyword={item.keyword} />
          </div>)}
        </aside>
        <section className="min-w-0" aria-label="Selected opportunity">{selected ? <SellingOpportunity key={`${version}:${selected}`} id={selected} refreshList={() => void query.refetch()} /> : <div className="max-w-xl py-4"><h2 className="text-lg font-semibold">Build a case for a better product</h2><p className="mt-3 text-sm leading-relaxed text-surface-200">Select an opportunity to compare sales estimates, momentum, reviews, keywords and design attributes. Each method keeps its sources and uncertainties visible.</p><p className="mt-4 text-sm leading-relaxed text-surface-200">Choose Investigate on a discovered listing, or create an opportunity from saved evidence. Source access and sales uncertainty remain visible throughout the research.</p></div>}</section>
      </div>
      </section>
    </>}
  </main>
}

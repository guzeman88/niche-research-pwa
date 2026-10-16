import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { sellingRequest, text, number, values, download, families, type Detail } from '../../lib/sellingProducts'
import KeywordRightsFlag from '../KeywordRightsFlag'
import SellingImport from './SellingImport'
import SellingForms from './SellingForms'
import SellingAnalysis from './SellingAnalysis'
import SellingBrief from './SellingBrief'
import SellingModel from './SellingModel'

const tabs = ['analysis', 'sales model', 'evidence', 'improvement brief']
export default function SellingOpportunity({ id, refreshList }: { id: string; refreshList: () => void }) {
  const query = useQuery({ queryKey: ['selling-opportunity', id], queryFn: () => sellingRequest<Detail>(`/opportunities/${id}`), retry: false })
  const [tab, setTab] = useState('analysis'), [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('')
  const item = query.data
  const refresh = async () => { await query.refetch(); refreshList() }
  if (query.isPending) return <p role="status" className="py-5">Loading opportunity evidence…</p>
  if (query.error || !item) return <div role="alert"><p>{query.error?.message || 'Opportunity unavailable.'}</p><button className="btn-secondary mt-3" onClick={() => void query.refetch()}>Retry opportunity</button></div>
  return <>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="break-words text-xl font-semibold">{item.name}</h2><p className="mt-2 text-sm text-surface-200">{item.keyword} · {text(item.family)}</p><KeywordRightsFlag keyword={item.keyword} /></div><button className="btn-secondary" onClick={async () => {
      try { download(`selling-opportunity-${item.id}.json`, await sellingRequest(`/opportunities/${item.id}/export`)); setMessage('Private evidence package exported with its checksum. Source authenticity remains unverified.') } catch (cause) { setError(String(cause)) }
    }}>Export evidence</button></div>
    <p className="mt-4 text-sm"><strong>{text(item.analysis.evidence_level)}</strong> · {item.analysis.listing_count} comparable listings · {item.analysis.independent_selling_shops} shops with recent sales figures</p>
    <p className="mt-2 max-w-prose text-sm leading-relaxed text-surface-200">Estimates, seller-reported figures and recent reviews are different evidence. Favorites and shop totals do not establish listing sales.</p>
    <details className="my-4 border-b border-surface-600 pb-4"><summary className="cursor-pointer text-sm font-semibold">Opportunity notes and stage</summary>
      <form className="mt-4 space-y-4" onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try {
        const data = values(event.currentTarget); await sellingRequest(`/opportunities/${id}`, { opportunity: { name: item.name, keyword: item.keyword, family: item.family, ...data }, expected_fingerprint: item.fingerprint }); await refresh(); setMessage('Opportunity updated.')
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Save failed.') } finally { setBusy(false) } }}>
        <label className="block text-sm">Opportunity name<input className="input mt-2 w-full" name="name" defaultValue={item.name} required minLength={3} maxLength={140} /></label>
        <label className="block text-sm">Buyer keyword<input className="input mt-2 w-full" name="keyword" defaultValue={item.keyword} required minLength={3} maxLength={160} /></label>
        <label className="block text-sm">Product family<select className="input mt-2 w-full" name="family" defaultValue={item.family}>{families.map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
        <label className="block text-sm">Stage<select className="input mt-2 w-full" name="stage" defaultValue={item.stage}>{['watching', 'shortlisted', 'archived'].map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
        <label className="block text-sm">Audience<input className="input mt-2 w-full" name="audience" defaultValue={item.audience} maxLength={500} /></label>
        <label className="block text-sm">Buyer task<textarea className="input mt-2 w-full" name="buyer_task" defaultValue={item.buyer_task} maxLength={1000} rows={2} /></label>
        <label className="block text-sm">Research notes<textarea className="input mt-2 w-full" name="notes" defaultValue={item.notes} maxLength={2000} rows={3} /></label><button className="btn-secondary" disabled={busy}>Save notes and stage</button>
      </form>
    </details>
    <nav aria-label="Opportunity sections" className="my-5 flex flex-wrap gap-2 border-b border-surface-600 pb-4">{tabs.map(value => <button className={tab === value ? 'btn-primary' : 'btn-secondary'} key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{text(value)}</button>)}</nav>
    {error && <p className="my-4 text-sm text-accent-amber" role="alert">{error}</p>}{message && <p className="my-4 text-sm" role="status">{message}</p>}
    {tab === 'analysis' && <SellingAnalysis item={item} />}
    {tab === 'sales model' && <SellingModel item={item} refresh={refresh} />}
    {tab === 'evidence' && <div className="space-y-8"><SellingImport item={item} refresh={refresh} /><SellingForms item={item} refresh={refresh} />
      <details><summary className="cursor-pointer text-sm font-semibold">Saved source records · {number(item.record_count)} records / {number(item.revision_count)} retained revisions</summary>
        <p className="my-3 text-sm text-surface-200">{item.pending_sync} records awaiting the private database mirror. The authoritative local records remain saved.</p>
        {(['listings', 'observations', 'reviews', 'patterns', 'calibration'] as const).map(kind => { const rows = item.evidence[kind] || []; return <div className="mt-5" key={kind}><h3 className="text-sm font-semibold">{text(kind)} · {rows.length}</h3>{rows.map((row, index) => <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words bg-surface-900 p-3 text-xs leading-relaxed" key={index}>{JSON.stringify(row, null, 2)}</pre>)}</div> })}
      </details></div>}
    {tab === 'improvement brief' && <SellingBrief key={item.fingerprint} item={item} refresh={refresh} />}
  </>
}

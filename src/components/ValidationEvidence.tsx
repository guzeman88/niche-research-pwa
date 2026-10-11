import { useState } from 'react'
import { display, validationRequest } from '../lib/productValidation'
import type { ValidationProject, ValidationRecord } from '../lib/productValidation'

type Listing = {listing_id: string; shop_id: string; title: string; price: number; currency: string; shipping: number | null}
type Signal = {keyword: string; monthly_searches: number | null; geography?: string; metadata?: {period_start?: string; period_end?: string; competition_level?: string; close_variants?: string[]}}

function SampleReview({record, projectId, refresh}: {record: ValidationRecord; projectId: string; refresh: () => Promise<void>}) {
  const [note, setNote] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const samples = record.payload.listings as Listing[]
  return <details className="mt-4 border-t border-surface-600 py-4"><summary className="cursor-pointer text-sm font-semibold">{String(record.payload.keyword)} · {samples.length} samples · {String(record.payload.observed_at)} · {record.payload.relevance_reviewed ? 'Reviewed' : 'Review needed'}</summary>
    <p className="mt-3 text-sm text-surface-200">{String(record.payload.source)} · {String(record.payload.filters || 'No filters recorded')}. Sample prices preserve original currencies; shipping may be unknown.</p>
    <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Listing', 'Shop', 'Price', 'Shipping'].map(name => <th key={name} className="px-3 py-2 font-medium">{name}</th>)}</tr></thead><tbody>{samples.map(row => <tr key={row.listing_id}><td className="min-w-52 border-t border-surface-700 px-3 py-3"><a href={`https://www.etsy.com/listing/${encodeURIComponent(row.listing_id)}`} target="_blank" rel="noreferrer" className="underline">{row.title}</a><span className="block text-xs text-surface-200">{row.listing_id}</span></td><td className="border-t border-surface-700 px-3 py-3">{row.shop_id}</td><td className="whitespace-nowrap border-t border-surface-700 px-3 py-3">{display(row.price)} {row.currency}</td><td className="border-t border-surface-700 px-3 py-3">{display(row.shipping)}</td></tr>)}</tbody></table></div>
    {!record.payload.relevance_reviewed && <form className="mt-4 max-w-xl space-y-3" onSubmit={async event => {
      event.preventDefault(); setBusy(true)
      try {await validationRequest(`/projects/${projectId}/review-competitors`, {record_id: record.id, fingerprint: record.fingerprint, review_note: note}); await refresh(); setMessage('Relevance review saved.')}
      catch (error) {setMessage(error instanceof Error ? error.message : 'Review failed.')}
      finally {setBusy(false)}
    }}><p className="text-sm text-surface-200">Confirm only if this entire sample is comparable. Otherwise use the competitor CSV form to import a filtered sample with at least 20 relevant listings.</p><label className="block text-sm">Why these products are comparable<input required maxLength={300} value={note} onChange={event => setNote(event.target.value)} className="input mt-2 w-full" /></label><button className="btn-secondary" disabled={busy}>{busy ? 'Saving…' : 'Confirm sample relevance'}</button></form>}
    {message && <p role="status" className="mt-3 text-sm">{message}</p>}
  </details>
}

export default function ValidationEvidence({project, refresh}: {project: ValidationProject; refresh: () => Promise<void>}) {
  const samples = project.records.filter(row => row.kind === 'competitors')
  const google = project.records.filter(row => row.kind === 'google')
  return <section className="mt-8"><h2 className="text-lg font-semibold">Saved evidence</h2>
    {!samples.length && !google.length && <p className="mt-2 text-sm text-surface-200">Collected samples and Google demand packages will appear here for review.</p>}
    {samples.map(record => <SampleReview key={`${record.id}:${record.fingerprint}`} record={record} projectId={project.id} refresh={refresh} />)}
    {google.map(record => <details key={record.id} className="border-t border-surface-600 py-4"><summary className="cursor-pointer text-sm font-semibold">Google demand · {String(record.payload.collected_at || 'collection date unknown')} · {String(record.payload.geography || 'geography unknown')}</summary><p className="mt-3 text-sm text-surface-200">Search volume groups close variants. Advertiser competition measures Google ads, and does not measure Etsy seller competition.</p><div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Keyword group', 'Average monthly searches', 'Reporting months', 'Advertiser competition'].map(name => <th className="px-3 py-2 font-medium" key={name}>{name}</th>)}</tr></thead><tbody>{(record.payload.signals as Signal[]).map(row => <tr key={row.keyword}><td className="border-t border-surface-700 px-3 py-3">{row.keyword}<span className="block text-xs text-surface-200">{row.metadata?.close_variants?.join(', ')}</span></td><td className="border-t border-surface-700 px-3 py-3">{display(row.monthly_searches)}</td><td className="border-t border-surface-700 px-3 py-3">{row.metadata?.period_start || 'Unknown'}–{row.metadata?.period_end || 'Unknown'}</td><td className="border-t border-surface-700 px-3 py-3">{row.metadata?.competition_level || 'Unknown'}</td></tr>)}</tbody></table></div><p className="mt-3 break-all text-xs text-surface-200">Package SHA256 {String(record.payload.package_sha256)} · {String(record.payload.provenance)}</p></details>)}
  </section>
}

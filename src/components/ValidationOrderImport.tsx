import { useState } from 'react'
import { validationRequest, values } from '../lib/productValidation'
import type { FormEvent } from 'react'
import ValidationImportPreview from './ValidationImportPreview'

export default function ValidationOrderImport({projectId, refresh}: {projectId: string; refresh: () => Promise<void>}) {
  const [preview, setPreview] = useState<{rows: number; preview: Array<Record<string, unknown>>; data: unknown} | null>(null), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(''); setPreview(null)
    const fields = values(event.currentTarget)
    const columns = Object.fromEntries(['order_id', 'transaction_id', 'listing_id', 'date', 'currency', 'revenue'].map(name => [name, fields[name]]))
    const data = {shop_id: fields.shop_id, source: fields.source, text: fields.text, revenue_basis: fields.revenue_basis, columns}
    try {const result = await validationRequest<{rows: number; preview: Array<Record<string, unknown>>}>(`/projects/${projectId}/orders/import`, data); setPreview({...result, data})}
    catch (error) {setMessage(error instanceof Error ? error.message : 'Unable to preview order items.')}
    finally {setBusy(false)}
  }
  return <section className="my-8 border-t border-surface-600 pt-6"><h3 className="text-lg font-semibold">Reconcile order items</h3>
    <p className="mt-3 text-sm text-surface-200">Paste an order-item export and explicitly map its columns. Use verified listing IDs; if the export only has SKUs, map those to listing IDs before importing. Dates must use YYYY-MM-DD. Payment fees and refunds belong in the results worksheet.</p>
    <form className="mt-4 space-y-4" onSubmit={submit} onChange={() => setPreview(null)}>
      <div className="grid gap-4 sm:grid-cols-2">{['shop_id', 'source', 'order_id', 'transaction_id', 'listing_id', 'date', 'currency', 'revenue'].map(name => <label className="block text-sm" key={name}>{['shop_id', 'source'].includes(name) ? name.replace(/_/g, ' ') : `Column for ${name.replace(/_/g, ' ')}`}<input name={name} className="input mt-2 w-full" required /></label>)}</div>
      <label className="block text-sm">Revenue definition · specify discounts, shipping and taxes<input name="revenue_basis" className="input mt-2 w-full" required /></label>
      <label className="block text-sm">Order-item CSV<textarea name="text" className="input mt-2 min-h-36 w-full" required /></label>
      <button className="btn-secondary" disabled={busy}>{busy ? 'Checking…' : 'Preview order items'}</button>
    </form>
    {preview && <div className="mt-4 space-y-3"><p>{preview.rows} unique order items passed validation. They will be preserved as reconciliation evidence.</p><ValidationImportPreview rows={preview.preview} /><button className="btn-primary" disabled={busy} onClick={async () => {
      setBusy(true)
      try {await validationRequest(`/projects/${projectId}/orders/import?commit=true`, preview.data); setPreview(null); await refresh(); setMessage('Order items saved. Listing-period totals remain separate to prevent double-counting.')}
      catch (error) {setMessage(error instanceof Error ? error.message : 'Unable to import orders.')}
      finally {setBusy(false)}
    }}>Commit reviewed order items</button></div>}
    {message && <p className="mt-3 text-sm" role="status">{message}</p>}
  </section>
}

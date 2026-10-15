import { useState } from 'react'
import { sellingRequest, text, metrics, sources, localDay, localTime, values, type Detail } from '../../lib/sellingProducts'

export default function SellingForms({ item, refresh }: { item: Detail; refresh: () => Promise<void> }) {
  const [kind, setKind] = useState('listings'), [metric, setMetric] = useState('estimated_sales'), [basis, setBasis] = useState('period')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  const listingSelect = <label className="block text-sm">Listing<select className="input mt-2 w-full" name="listing_id" required>{item.evidence.listings.map(row => <option key={row.listing_id} value={row.listing_id}>{row.title} · {row.listing_id}</option>)}</select></label>
  return <section className="space-y-4" aria-labelledby="selling-record-heading">
    <h3 className="text-lg font-semibold" id="selling-record-heading">Record an observation</h3>
    <div className="flex flex-wrap gap-2">{['listings', 'observations', 'reviews', 'patterns'].map(value => <button key={value} className={kind === value ? 'btn-primary' : 'btn-secondary'} aria-pressed={kind === value} onClick={() => { setKind(value); setError(''); setMessage('') }}>{value === 'patterns' ? 'Design attributes' : text(value)}</button>)}</div>
    {kind !== 'listings' && !item.evidence.listings.length ? <p className="text-sm text-surface-200">Add a comparable listing first so every observation has an identifiable source product.</p> : <form key={kind} aria-label={`Record ${kind}`} className="max-w-3xl space-y-4" onSubmit={async event => {
      event.preventDefault(); const form = event.currentTarget; const data = values(form); setBusy(true); setError('')
      try {
        let payload: Record<string, unknown> = { ...data }
        if (kind === 'listings') payload = { ...data, tags: (data.tags || '').split('|').map(value => value.trim()).filter(Boolean), created_on: data.created_on || null }
        if (kind === 'observations') payload = { ...data, metric, basis, value: data.value === '' ? null : Number(data.value), observed_at: new Date(data.observed_at).toISOString(), period_start: basis === 'period' ? data.period_start : null, period_end: basis === 'period' ? data.period_end : null }
        if (kind === 'reviews') payload = { ...data, rating: Number(data.rating) }
        if (kind === 'patterns') payload = { ...data, features: (data.features || '').split('|').map(value => value.trim()).filter(Boolean), readability: data.readability ? Number(data.readability) : null }
        await sellingRequest(`/opportunities/${item.id}/import`, { packet: { [kind]: [payload] }, expected_fingerprint: item.fingerprint })
        form.reset(); await refresh(); setMessage('Source record saved. Repeating its identity updates a retained revision.')
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save this observation.') } finally { setBusy(false) }
    }}>
      {kind === 'listings' ? <>
        <div className="grid gap-4 sm:grid-cols-2"><Field name="listing_id" label="Etsy listing ID" required /><Field name="title" label="Observed listing title" required max={300} /><Field name="shop" label="Shop identity · leave blank if unknown" max={120} /><Field name="url" label="Etsy listing URL · optional" type="url" max={1000} /></div>
        <Field name="tags" label="Observed tags · optional, separated by |" max={3000} /><Field name="created_on" label="Original listing creation date · if known" type="date" />
      </> : listingSelect}
      {kind === 'observations' && <>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Metric<select className="input mt-2 w-full" value={metric} onChange={event => { const value = event.target.value; setMetric(value); setBasis(['reviews', 'favorites', 'shop_sales'].includes(value) ? 'lifetime' : value === 'price' || value === 'listing_count' ? 'point_in_time' : 'period') }}>{metrics.map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
          <label className="text-sm">Value · blank means unknown<input className="input mt-2 w-full" type="number" name="value" min={0} step="any" /></label>
          <label className="text-sm">Measurement basis<select className="input mt-2 w-full" value={basis} onChange={event => setBasis(event.target.value)}>{['period', 'lifetime', 'lifetime_average', 'point_in_time'].map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>
          <Field name="observed_at" label="Observed at · local time" type="datetime-local" defaultValue={localTime()} required /></div>
        {basis === 'period' && <div className="grid gap-4 sm:grid-cols-2"><Field name="period_start" label="Reporting period start" type="date" required /><Field name="period_end" label="Reporting period end" type="date" required /></div>}
        {metric === 'price' && <Field name="currency" label="Currency · three-letter code" defaultValue="USD" required max={3} />}
        {metric === 'keyword_searches' && <div className="grid gap-4 sm:grid-cols-2"><Field name="keyword" label="Measured keyword" defaultValue={item.keyword} required /><Field name="geography" label="Geography shown by the source" required /></div>}
        <label className="block text-sm">Evidence notes{metric === 'seller_reported_sales' && ' · required; explain the underlying seller records'}<textarea className="input mt-2 w-full" name="note" rows={2} maxLength={1500} required={metric === 'seller_reported_sales'} /></label>
        <p className="text-sm leading-relaxed text-surface-200">Seller-reported sales are not independently verified. Lifetime averages, shop totals and review counters keep their original scope and are never converted into listing orders.</p>
      </>}
      {kind === 'reviews' && <><div className="grid gap-4 sm:grid-cols-2"><Field name="review_id" label="Stable review ID or source reference" required /><Field name="reviewed_on" label="Review date" type="date" defaultValue={localDay()} required /><label className="text-sm">Rating<select className="input mt-2 w-full" name="rating" defaultValue="" required><option value="">Choose the recorded rating</option>{[1, 2, 3, 4, 5].map(value => <option key={value}>{value}</option>)}</select></label></div><label className="block text-sm">Buyer feedback<textarea className="input mt-2 w-full" name="text" rows={4} minLength={3} maxLength={5000} required /></label><p className="text-xs text-surface-200">Record feedback you are permitted to use. Buyer names and contact information are unnecessary.</p></>}
      {kind === 'patterns' && <><div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Typography<select className="input mt-2 w-full" name="typography">{['unknown', 'serif', 'sans_serif', 'handwritten', 'mixed'].map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label><label className="text-sm">Layout<select className="input mt-2 w-full" name="layout">{['unknown', 'minimal', 'structured', 'illustrated', 'text_led'].map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label><Field name="palette" label="Observed palette · optional" max={100} /><label className="text-sm">Readability · operator assessment<select className="input mt-2 w-full" name="readability"><option value="">Not assessed</option>{[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value}{value === 1 ? ' · difficult' : value === 5 ? ' · clear' : ''}</option>)}</select></label></div><Field name="features" label="Observed features · separated by |" max={2000} /><label className="block text-sm">Design observations<textarea className="input mt-2 w-full" name="notes" rows={3} maxLength={1000} /></label><p className="text-sm text-surface-200">Describe abstract traits and useful features. This does not extract, trace or regenerate the competitor’s artwork.</p></>}
      {(kind === 'listings' || kind === 'observations') && <label className="block text-sm">Source<select className="input mt-2 w-full" name="source">{sources.map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>}
      <Field name="source_ref" label="Saved report, source URL or inspection reference" required max={1000} />
      <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : kind === 'patterns' ? 'Save design attributes' : `Save ${kind === 'listings' ? 'listing' : kind === 'reviews' ? 'review' : 'observation'}`}</button>
    </form>}
    {error && <p role="alert" className="text-sm text-accent-amber">{error}</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>
}

function Field({ name, label, type = 'text', required = false, defaultValue, max = 160 }: { name: string; label: string; type?: string; required?: boolean; defaultValue?: string; max?: number }) {
  return <label className="block text-sm">{label}<input className="input mt-2 w-full" name={name} type={type} required={required} defaultValue={defaultValue} maxLength={max} /></label>
}

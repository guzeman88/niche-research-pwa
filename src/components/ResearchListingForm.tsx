import { useState } from 'react'
import { validationRequest, values } from '../lib/productValidation'
import type { SupportedKeyword } from '../lib/supportedKeywords'

export default function ResearchListingForm({keyword, onSaved}: {keyword: SupportedKeyword; onSaved: (project: string) => Promise<void>}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  return <form aria-label="Research listing product facts" className="mt-5 max-w-3xl space-y-4" onSubmit={async event => {
    event.preventDefault(); const data = values(event.currentTarget); setBusy(true); setError('')
    try {
      const result = await validationRequest<{project_id: string}>('/listing-drafts', {...data, keyword: keyword.keyword,
        product_matches_keyword: data.product_matches_keyword === 'on', price: data.price || null})
      await onSaved(result.project_id)
    } catch (cause) {setError(cause instanceof Error ? cause.message : 'The draft could not be saved.')}
    finally {setBusy(false)}
  }}>
    <h3 className="text-base font-semibold">Prepare a product for “{keyword.keyword}”</h3>
    <p className="text-sm leading-relaxed text-surface-200">Enter actual product facts. The draft retains its evidence and creates a product concept for costs, relevance review and sales tracking.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm">Descriptive product name<input className="input mt-2 w-full" name="product_name" maxLength={140} required /></label>
      <label className="text-sm">Product type<input className="input mt-2 w-full" name="product_type" placeholder="Ceramic mug, door hanger, printable…" maxLength={300} required /></label>
      {['material', 'color', 'size', 'personalization'].map(name => <label className="text-sm capitalize" key={name}>{name} · if applicable<input className="input mt-2 w-full" name={name} maxLength={300} /></label>)}
      <label className="text-sm">Etsy category · verify before launch<input className="input mt-2 w-full" name="category" maxLength={300} /></label>
      <label className="text-sm">Actual sale price · USD<input className="input mt-2 w-full" name="price" type="number" min="0.01" step="0.01" /></label>
    </div>
    <label className="block text-sm">Product details<textarea className="input mt-2 w-full" name="details" rows={3} maxLength={2000} required /></label>
    <label className="block text-sm">Processing, delivery and return terms<textarea className="input mt-2 w-full" name="delivery" rows={2} maxLength={300} /></label>
    <label className="block text-sm">Relevant tags · optional, comma-separated<input className="input mt-2 w-full" name="tags" maxLength={500} /><span className="mt-1 block text-surface-200">Leave blank for suggestions from your facts and research. Complete and review all 13 before launch.</span></label>
    <label className="flex items-start gap-3 text-sm"><input className="mt-1" name="product_matches_keyword" type="checkbox" required /><span>I checked that this actual product matches the selected buyer keyword.</span></label>
    {error && <p className="text-sm" role="alert">{error}</p>}
    <button className="btn-primary" disabled={busy}>{busy ? 'Saving draft…' : 'Save listing draft and product concept'}</button>
  </form>
}

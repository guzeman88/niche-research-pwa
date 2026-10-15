import { useState } from 'react'
import { Link } from 'react-router-dom'
import { sellingRequest, families, text, values, type Detail } from '../../lib/sellingProducts'

export default function SellingBrief({ item, refresh }: { item: Detail; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [project, setProject] = useState('')
  const brief = item.brief
  return <section className="max-w-3xl space-y-5" aria-labelledby="selling-brief-heading">
    <h3 id="selling-brief-heading" className="text-lg font-semibold">An original product with a reason to compete</h3>
    <p className="text-sm leading-relaxed text-surface-200">Use evidence to define a buyer task and testable improvements. Write a new product direction; competitor artwork, wording, prices and tags are not copied into production files.</p>
    {brief?.stale && <p className="text-sm text-accent-amber" role="status">Evidence changed after this brief was saved. Review it and save again before production intake.</p>}
    <details open={!brief}><summary className="cursor-pointer text-sm font-semibold">Suggested questions and improvements</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed">{item.analysis.improvement_suggestions.map(value => <li key={value}>{value}</li>)}</ul><p className="mt-3 text-xs text-surface-200">These are hypotheses from recorded feedback or operator assessments. They are not validated product capabilities.</p></details>
    <form className="space-y-4" aria-label="Original improvement brief" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(''); const data = values(event.currentTarget)
      try { await sellingRequest(`/opportunities/${item.id}/brief`, { expected_fingerprint: item.fingerprint, brief: { ...data, improvements: data.improvements.split('\n').map(value => value.trim()).filter(Boolean) } }); await refresh(); setMessage('Original brief saved with the exact research fingerprint.') }
      catch (cause) { setError(cause instanceof Error ? cause.message : 'Brief could not be saved.') } finally { setBusy(false) }
    }}>
      <label className="block text-sm">Original product name<input className="input mt-2 w-full" name="name" defaultValue={brief?.name || ''} required minLength={3} maxLength={120} /></label>
      <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Intended buyer<input className="input mt-2 w-full" name="buyer" defaultValue={brief?.buyer || item.audience} required minLength={3} maxLength={300} /></label><label className="text-sm">Product family<select className="input mt-2 w-full" name="family" defaultValue={brief?.family || item.family}>{families.map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label></div>
      <label className="block text-sm">Purpose and buyer task<textarea className="input mt-2 w-full" name="purpose" rows={3} required minLength={10} maxLength={2000} defaultValue={brief?.purpose || item.buyer_task} /></label>
      <label className="block text-sm">Specific improvements · one per line<textarea className="input mt-2 w-full" name="improvements" rows={4} required defaultValue={brief?.improvements.join('\n') || ''} maxLength={6000} /></label>
      <label className="block text-sm">Your original design direction<textarea className="input mt-2 w-full" name="original_direction" rows={4} required minLength={10} maxLength={2000} defaultValue={brief?.original_direction || ''} /></label>
      <label className="block text-sm">Development notes<textarea className="input mt-2 w-full" name="notes" rows={2} maxLength={2000} defaultValue={brief?.notes || ''} /></label>
      <button className="btn-primary" disabled={busy}>{busy ? 'Saving brief…' : 'Save original brief'}</button>
    </form>
    {brief && !brief.stale && <div className="space-y-3 border-t border-surface-600 pt-5"><h4 className="font-semibold">Continue with reviewed product development</h4><p className="text-sm leading-relaxed text-surface-200">Production opens a specification for review. Supply your original customer contents, costs and exact delivery facts there. No render, marketplace draft or publication starts from this brief.</p><div className="flex flex-wrap gap-3">{brief.family !== 'other' && <Link className="btn-secondary" to={`/validation?opportunity=${encodeURIComponent(item.id)}`}>Review in production</Link>}<button className="btn-secondary" disabled={busy} onClick={async () => {
      setBusy(true); setError(''); try { const result = await sellingRequest<{ project_id: string }>(`/opportunities/${item.id}/validation`, {}); setProject(result.project_id); setMessage('Validation concept linked. Demand, relevance, costs and outcomes still need their own evidence.') } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
    }}>Link to product validation</button></div>{brief.family === 'other' && <p className="text-sm text-surface-200">This family has no renderer. Export the evidence and brief for manual development.</p>}{project && <Link className="inline-block text-sm underline underline-offset-4" to={`/validation?project=${encodeURIComponent(project)}`}>Open linked validation concept</Link>}</div>}
    {error && <p role="alert" className="text-sm text-accent-amber">{error}</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>
}

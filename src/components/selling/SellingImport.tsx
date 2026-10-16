import { useState } from 'react'
import { sellingRequest, download, text, type Detail, type Preview, type Packet } from '../../lib/sellingProducts'

const templates: Record<string, string> = {
  listings: 'listing_id,title,shop,url,tags,created_on,source,source_ref\n',
  observations: 'listing_id,metric,value,basis,observed_at,period_start,period_end,currency,keyword,geography,source,source_ref,note\n',
  reviews: 'review_id,listing_id,reviewed_on,rating,text,source_ref\n',
  patterns: 'listing_id,typography,layout,palette,features,readability,notes,source_ref\n',
  calibration: 'case_id,listing_id,period_start,period_end,actual_purchases,source_ref,note\n',
}
export default function SellingImport({ item, refresh }: { item: Detail; refresh: () => Promise<void> }) {
  const [content, setContent] = useState(''), [format, setFormat] = useState('json'), [dataset, setDataset] = useState('listings')
  const [preview, setPreview] = useState<Preview | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  async function prepare(packet?: Packet) {
    setBusy(true); setError(''); setPreview(null)
    try {
      setPreview(await sellingRequest<Preview>(`/opportunities/${item.id}/preview`, packet ? { format: 'json', content: JSON.stringify(packet) } : { format, dataset, content }))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Preview failed.') } finally { setBusy(false) }
  }
  return <section aria-labelledby="selling-import-heading" className="space-y-4">
    <h3 id="selling-import-heading" className="text-lg font-semibold">Bring in evidence</h3>
    <p className="max-w-prose text-sm leading-relaxed text-surface-200">Reuse preserved listing observations or import research you are permitted to use. Preview adds, corrections and duplicates before saving. No external marketplace requests are made.</p>
    <button className="btn-secondary" disabled={busy} onClick={async () => {
      setBusy(true); setError(''); setPreview(null)
      try { const result = await sellingRequest<{ packet: Packet; status: string; skipped_rows: number }>(`/research?keyword=${encodeURIComponent(item.keyword)}`)
        if (!result.packet.listings.length) { setMessage('No saved listings match this exact keyword. Add a listing or import a permitted research file.'); return }
        await prepare(result.packet); setMessage(`Saved research found ${result.packet.listings.length} listings. This does not include competitor sales.${result.skipped_rows ? ` ${result.skipped_rows} incomplete source rows were skipped.` : ''}`)
      } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
    }}>Find “{item.keyword}” in saved research</button>
    <details className="border-y border-surface-600 py-4"><summary className="cursor-pointer text-sm font-semibold">Import a research file</summary>
      <div className="mt-4 space-y-4"><div className="flex flex-wrap gap-4"><label className="text-sm">File format<select className="input mt-2 w-full" value={format} onChange={event => { setFormat(event.target.value); setPreview(null) }}><option value="json">JSON evidence package</option><option value="csv">CSV</option></select></label>
        {format === 'csv' && <label className="text-sm">CSV record type<select className="input mt-2 w-full" value={dataset} onChange={event => { setDataset(event.target.value); setPreview(null) }}>{Object.keys(templates).map(value => <option key={value} value={value}>{text(value)}</option>)}</select></label>}</div>
        <div className="flex flex-wrap items-end gap-4"><label className="min-w-0 text-sm">Choose a file · maximum 2 MB<input className="mt-2 block w-full max-w-full text-sm" type="file" accept=".json,.csv,application/json,text/csv" onChange={async event => {
          const file = event.target.files?.[0]; setError(''); setPreview(null)
          if (!file) return
          if (file.size > 2000000) { setError('Choose a file no larger than 2 MB.'); return }
          try { setContent(await file.text()) } catch { setError('The file could not be read. Choose it again.') }
        }} /></label><button type="button" className="btn-secondary" onClick={() => format === 'csv' ? download(`selling-${dataset}-template.csv`, templates[dataset], true) : download('selling-evidence-template.json', { schema_version: 1, listings: [], observations: [], reviews: [], patterns: [] })}>Download template</button></div>
        <label className="block text-sm">Research data<textarea className="input mt-2 w-full font-mono text-xs" rows={8} value={content} maxLength={2000000} onChange={event => { setContent(event.target.value); setPreview(null) }} /></label>
        <p className="max-w-prose text-xs leading-relaxed text-surface-200">Use ISO timestamps with a timezone for observations, YYYY-MM-DD for dates and | between CSV tags or features. Sales must declare a period, lifetime or lifetime-average basis. Provider exports may need their columns mapped to the template.</p>
        <button className="btn-secondary" disabled={busy || !content.trim()} onClick={() => void prepare()}>{busy ? 'Reading evidence…' : 'Preview import'}</button>
      </div>
    </details>
    {error && <p role="alert" className="text-sm text-accent-amber">{error}</p>}{message && <p role="status" className="text-sm text-surface-200">{message}</p>}
    {preview && <div className="space-y-3 border-b border-surface-600 pb-5" aria-label="Research import preview">
      <h4 className="text-base font-semibold">Review this import</h4><p className="text-sm">{preview.added} new records · {preview.changed} corrections · {preview.duplicates} duplicates</p>
      <p className="text-sm text-surface-200">Corrections retain prior revisions. A checksum verifies file integrity, not the accuracy of a provider’s estimates.</p>
      <details><summary className="cursor-pointer text-sm">Inspect parsed records</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words bg-surface-900 p-3 text-xs">{JSON.stringify(preview.packet, null, 2)}</pre></details>
      <div className="flex flex-wrap gap-3"><button className="btn-primary" disabled={busy || !preview.total} onClick={async () => {
        setBusy(true); setError(''); try { await sellingRequest(`/opportunities/${item.id}/import`, { packet: preview.packet, expected_fingerprint: preview.fingerprint }); setPreview(null); setContent(''); await refresh(); setMessage('Evidence saved locally. Analysis updated; private mirror retries remain available.') }
        catch (cause) { setError(cause instanceof Error ? cause.message : 'Import failed; saved evidence was preserved.') } finally { setBusy(false) }
      }}>Import reviewed evidence</button><button className="btn-secondary" disabled={busy} onClick={() => setPreview(null)}>Discard preview</button></div>
    </div>}
  </section>
}

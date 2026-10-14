import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { productionRequest, type ProductionOverview } from '../lib/production'

export default function ProductionTools({overview, refresh, productId}: {overview: ProductionOverview; refresh: () => void; productId?: string}) {
  const [result, setResult] = useState('')
  const mutation = useMutation({mutationFn: ({path, body}: {path: string; body: unknown}) => productionRequest(path, body), onSuccess: data => {setResult(JSON.stringify(data, null, 2)); refresh()}})
  const run = (path: string, body: unknown) => mutation.mutate({path, body})
  const local = overview.capabilities.text; const models = typeof local === 'object' ? local.models || [] : []
  return <details className="mt-5 rounded border border-surface-600 p-4">
    <summary className="cursor-pointer text-sm">Local models, artwork import and quality feedback</summary>
    <ul className="mt-4 flex flex-wrap gap-4 text-xs text-surface-200">{Object.entries(overview.capabilities).map(([key, value]) => <li key={key}>{key.replace(/_/g, ' ')}: {typeof value === 'object' ? value.status : String(value)}</li>)}</ul>
    <div className="mt-4 space-y-3">{overview.profiles?.map(profile => <div key={profile.id} className="flex flex-wrap items-center gap-3 text-sm"><span>{profile.spec.name} · {profile.enabled ? 'Enabled' : 'Disabled'}</span><button className="btn-secondary" onClick={() => run(`/profiles/${profile.id}`, {enabled: !profile.enabled})}>{profile.enabled ? 'Disable recipe' : 'Enable reviewed recipe'}</button></div>)}</div>
    <p className="mt-3 max-w-prose text-xs text-surface-200">Enabled recipes can queue up to ten new qualified research groups per UTC day, with product-format checks and human concept selection. This does not create qualification credit or activate products.</p>
    <button className="btn-secondary mt-3" onClick={() => run('/training-dataset', undefined)}>Inspect approved training dataset</button>
    <form className="mt-4 max-w-2xl" onSubmit={event => {event.preventDefault(); const data = new FormData(event.currentTarget); run('/training', {profile: data.get('profile'), approved: data.has('approved')})}}>
      <label className="block text-sm">Reviewed local training profile<input name="profile" className="input mt-2 w-full" /></label>
      <label className="mt-3 flex items-center gap-3 text-sm"><input name="approved" type="checkbox" />I approve this local experiment and its reviewed source images.</label>
      <button className="btn-secondary mt-3">Start gated local training experiment</button><p className="mt-2 text-xs text-surface-200">Requires approved data, a fingerprinted local trainer/model and compatible GPU. No downloads, paid fallback or automatic model promotion.</p>
    </form>
    <form className="mt-5 max-w-2xl" onSubmit={event => {event.preventDefault(); run('/models', Object.fromEntries(new FormData(event.currentTarget)))}}>
      <div className="grid gap-4 sm:grid-cols-3">{(['text', 'embedding', 'vision'] as const).map(key => <label key={key} className="text-sm">{key} model<select className="input mt-2 w-full" name={key} defaultValue={overview.models[key]}><option value="">Unavailable / not selected</option>{models.map(name => <option key={name}>{name}</option>)}</select></label>)}</div>
      <button className="btn-secondary mt-3" disabled={mutation.isPending}>Save local model selection</button><p className="mt-2 text-xs text-surface-200">Installed models need a quality and latency benchmark. No paid fallback is enabled.</p>
    </form>
    <form className="mt-5 max-w-2xl" onSubmit={event => {
      event.preventDefault(); const data = new FormData(event.currentTarget); const file = data.get('art') as File
      if (!file?.size || file.size > 20_000_000) {setResult('Select an image of at most twenty MB.'); return}
      const reader = new FileReader(); reader.onload = () => run('/assets', {base64: String(reader.result).split(',')[1], license_note: data.get('license_note')}); reader.readAsDataURL(file)
    }}><label className="block text-sm">Owned or licensed source artwork<input name="art" type="file" accept="image/png,image/jpeg" className="mt-2 block max-w-full text-sm" required /></label><label className="mt-3 block text-sm">Ownership or license provenance<textarea className="input mt-2 w-full" name="license_note" required minLength={10} /></label><button className="btn-secondary mt-3" disabled={mutation.isPending}>Import and preserve artwork</button></form>
    {productId && <form className="mt-5 max-w-2xl" onSubmit={event => {event.preventDefault(); run(`/products/${productId}/feedback`, Object.fromEntries(new FormData(event.currentTarget)))}}><label className="block text-sm">Product quality or customer feedback<textarea className="input mt-2 w-full" name="note" required /></label><button className="btn-secondary mt-3">Save feedback</button></form>}
    <form className="mt-5 max-w-2xl" onSubmit={event => {event.preventDefault(); const data = new FormData(event.currentTarget); try {run('/benchmarks', JSON.parse(String(data.get('comparison'))))} catch {setResult('Enter valid comparison JSON.')}}}><label className="block text-sm">Held-out benchmark comparison · JSON<textarea className="input mt-2 w-full font-mono" name="comparison" placeholder={'{"candidate":"…","baseline":"…","fixture_ids":["…"],"metrics":{},"human_note":"…"}'} /></label><button className="btn-secondary mt-3">Record quality comparison</button></form>
    {mutation.error && <p className="mt-3 text-sm" role="alert">{(mutation.error as Error).message}</p>}
    {result && <pre className="mt-4 max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs">{result}</pre>}
  </details>
}

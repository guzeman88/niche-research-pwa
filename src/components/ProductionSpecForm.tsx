import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { productionRequest, type ProductionSpec } from '../lib/production'

export default function ProductionSpecForm({initial, productId, refresh, close}: {
  initial?: ProductionSpec; productId?: string; refresh: () => void; close: () => void
}) {
  const [family, setFamily] = useState(initial ? initial.family : 'planner')
  const physical = ['mug', 'apparel'].includes(family)
  const mutation = useMutation({mutationFn: ({path, body}: {path: string; body: unknown}) => productionRequest(path, body), onSuccess: () => {refresh(); close()}})
  const [error, setError] = useState('')
  function submit(form: HTMLFormElement, recipe = false) {
    setError(''); const data = Object.fromEntries(new FormData(form)) as Record<string, string>
    try {
      const spec = {...initial, ...data, family, size: physical ? 'provider' : data.size,
        content: data.content.split('\n').map(x => x.trim()).filter(Boolean),
        tags: data.tags.split(',').map(x => x.trim()).filter(Boolean),
        supporting_keywords: data.supporting_keywords.split(',').map(x => x.trim()).filter(Boolean),
        price: data.price ? Number(data.price) : null, unit_cost: data.unit_cost ? Number(data.unit_cost) : null,
        category_id: data.category_id ? Number(data.category_id) : null,
        provider: JSON.parse(data.provider || '{}'), artwork_id: data.artwork_id || null,
        research: {}, schema_version: 1}
      mutation.mutate({path: recipe ? '/profiles' : '/jobs', body: recipe ? {spec, enabled: false, facts_reviewed: true} : {spec, product_id: productId}})
    } catch {setError('Provider configuration must be valid JSON.')}
  }
  return <form aria-label="Production specification" className="mt-5 max-w-3xl space-y-5" onSubmit={event => {event.preventDefault(); submit(event.currentTarget)}}>
    <p className="max-w-prose text-sm text-surface-200">Enter actual product facts and original content. Research support is checked by the server. Unvalidated concepts stay labeled.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm">Product name<input name="name" className="input mt-2 w-full" required minLength={3} maxLength={120} defaultValue={initial?.name} /></label>
      <label className="text-sm">Buyer keyword<input name="keyword" className="input mt-2 w-full" required minLength={3} defaultValue={initial?.keyword} /></label>
      <label className="text-sm">Buyer<input name="buyer" className="input mt-2 w-full" required minLength={3} defaultValue={initial?.buyer} /></label>
      <label className="text-sm">Product family<select required className="input mt-2 w-full" value={family} onChange={e => setFamily(e.target.value)}><option value="">Choose the actual product format</option>{['planner', 'worksheet', 'wall_art', 'mug', 'apparel'].map(x => <option key={x} value={x}>{x.replace('_', ' ')}</option>)}</select></label>
    </div>
    <label className="block text-sm">Purpose and promised contents<textarea className="input mt-2 min-h-24 w-full" name="purpose" required minLength={10} defaultValue={initial?.purpose} /></label>
    <label className="block text-sm">Original content · one page heading, prompt, or artwork line per row<textarea className="input mt-2 min-h-24 w-full" name="content" required defaultValue={initial?.content.join('\n')} /></label>
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="text-sm">Size<select name="size" className="input mt-2 w-full" defaultValue={initial?.size || 'letter'}>{(physical ? ['provider'] : family === 'wall_art' ? ['8x10', '12x16'] : ['letter', 'a4']).map(x => <option key={x}>{x}</option>)}</select></label>
      <label className="text-sm">Palette<select name="palette" className="input mt-2 w-full" defaultValue={initial?.palette || 'ink'}>{['ink', 'sage', 'clay'].map(x => <option key={x}>{x}</option>)}</select></label>
      <label className="text-sm">Layout<select name="layout" className="input mt-2 w-full" defaultValue={initial?.layout || 'classic'}>{['classic', 'editorial', 'minimal'].map(x => <option key={x}>{x}</option>)}</select></label>
    </div>
    <label className="block text-sm">Personalized wording<input className="input mt-2 w-full" name="personalization" maxLength={80} defaultValue={initial?.personalization} /></label>
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="text-sm">Actual selling price · USD<input className="input mt-2 w-full" name="price" type="number" min="0.01" step="0.01" defaultValue={initial?.price ?? ''} /></label>
      <label className="text-sm">Total variable cost · USD<input className="input mt-2 w-full" name="unit_cost" type="number" min="0" step="0.01" defaultValue={initial?.unit_cost ?? ''} /></label>
      <label className="text-sm">Verified Etsy taxonomy ID<input className="input mt-2 w-full" name="category_id" type="number" min="1" defaultValue={initial?.category_id ?? ''} /></label>
    </div>
    <label className="block text-sm">Delivery, processing and return terms<textarea className="input mt-2 w-full" name="delivery" defaultValue={initial?.delivery} /></label>
    <label className="block text-sm">Artwork and content rights provenance<textarea className="input mt-2 w-full" name="rights_note" defaultValue={initial?.rights_note} /></label>
    <label className="block text-sm">Thirteen curated tags · comma separated<input className="input mt-2 w-full" name="tags" defaultValue={initial?.tags.join(', ')} /></label>
    <label className="block text-sm">Supporting buyer keywords · comma separated<input className="input mt-2 w-full" name="supporting_keywords" defaultValue={initial?.supporting_keywords.join(', ')} /></label>
    <details className="rounded border border-surface-600 p-4"><summary className="cursor-pointer text-sm">Generation and physical product settings</summary>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">Concept method<select className="input mt-2 w-full" name="concept_method" defaultValue={initial?.concept_method || 'authored'}><option value="authored">Use authored content</option><option value="local_model">Generate local model concepts for selection</option></select></label>
        <label className="text-sm">Artwork method<select className="input mt-2 w-full" name="artwork_method" defaultValue={initial?.artwork_method || 'template'}><option value="template">Production template</option><option value="comfy">Reviewed local ComfyUI workflow</option></select></label>
        <label className="text-sm">Reviewed local image profile<input className="input mt-2 w-full" name="image_profile" defaultValue={initial?.image_profile} /></label>
        <label className="text-sm">Imported artwork ID<input className="input mt-2 w-full" name="artwork_id" defaultValue={initial?.artwork_id || ''} /></label>
      </div>
      <label className="mt-4 block text-sm">Confirmed physical materials<input className="input mt-2 w-full" name="materials" defaultValue={initial?.materials} /></label>
      <label className="mt-4 block text-sm">Reviewed provider selection · JSON<textarea className="input mt-2 min-h-24 w-full font-mono" name="provider" defaultValue={JSON.stringify(initial?.provider || {})} /></label>
      <p className="mt-2 text-xs text-surface-200">Physical products require actual catalog dimensions, variants, placement and provider mockups. No production orders are placed.</p>
    </details>
    {(error || mutation.error) && <p role="alert" className="text-sm">{error || (mutation.error as Error).message}</p>}
    <p className="text-xs text-surface-200">An automatic recipe must use local-model concepts. Saving a recipe confirms you reviewed its factual inputs; it starts disabled until explicitly enabled.</p>
    <div className="flex flex-wrap gap-3"><button className="btn-primary" disabled={mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Queue product revision'}</button><button type="button" className="btn-secondary" disabled={mutation.isPending} onClick={event => {const form = event.currentTarget.form; if (form?.reportValidity()) submit(form, true)}}>Save reviewed automatic recipe</button><button type="button" className="btn-secondary" onClick={close}>Close specification</button></div>
  </form>
}

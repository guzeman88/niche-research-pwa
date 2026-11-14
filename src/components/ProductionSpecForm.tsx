import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { productionRequest, productFamilies, type ProductionSpec, type ProductionOverview } from '../lib/production'
import ProductionCostPlan from './ProductionCostPlan'
import {costPlanFromForm} from '../lib/costPlan'

export default function ProductionSpecForm({initial, productId, refresh, close}: {
  initial?: ProductionSpec; productId?: string; refresh: () => void; close: () => void
}) {
  const [family, setFamily] = useState(initial ? initial.family : 'planner')
  const v2 = !['planner', 'worksheet', 'wall_art', 'mug', 'apparel'].includes(family) || initial?.schema_version === 2
  const productData = initial?.product_data || {}
  const catalog = useQuery({queryKey: ['production-bundle-candidates'], queryFn: () => productionRequest<ProductionOverview>(), enabled: family === 'bundle'})
  const selling = (initial?.research?.selling_products || initial?.research || {}) as Record<string, unknown>
  const physical = ['mug', 'apparel', 'tote'].includes(family)
  const costPlanAllowed=v2&&!physical&&family!=='pet_portrait'
  const mutation = useMutation({mutationFn: ({path, body}: {path: string; body: unknown}) => productionRequest(path, body), onSuccess: () => {refresh(); close()}})
  const [error, setError] = useState('')
  const [patternFingerprint, setPatternFingerprint] = useState('')
  const [costPlanEnabled,setCostPlanEnabled]=useState(Boolean(initial?.cost_plan))
  async function submit(form: HTMLFormElement, recipe = false) {
    setError(''); const data = Object.fromEntries(new FormData(form)) as Record<string, string>
    try {
      const spec = {...initial, ...data, family, size: physical ? 'provider' : data.size,
        content: data.content.split('\n').map(x => x.trim()).filter(Boolean),
        tags: data.tags.split(',').map(x => x.trim()).filter(Boolean),
        supporting_keywords: data.supporting_keywords.split(',').map(x => x.trim()).filter(Boolean),
        price: data.price ? Number(data.price) : null, unit_cost: costPlanAllowed&&costPlanEnabled?null:data.unit_cost ? Number(data.unit_cost) : null,
        category_id: data.category_id ? Number(data.category_id) : null,
        provider: JSON.parse(data.provider || '{}'), artwork_id: data.artwork_id || null,
        research: selling.selling_opportunity ? {selling_opportunity: selling.selling_opportunity, evidence_fingerprint: selling.evidence_fingerprint} : {}, schema_version: v2 ? 2 : 1}
      for (const key of ['creative_note','instructions','recipient','occasion_date','page_bodies','capacity','currency','budget_rows','guest_rows','author','tester','test_notes','tested_revision','pattern_instructions','materials_list','pet_name','portrait_date','component','test_date','maker_attested','likeness_reviewed','gauge','dimensions','authored_chart']) delete (spec as Record<string, unknown>)[key]
      for(const key of Object.keys(spec))if(key.startsWith('cp_'))delete (spec as Record<string,unknown>)[key]
      delete spec.cost_plan
      if (v2) {
        const values = {...productData}
        if (['birthday_magazine','birthday_newspaper','memory_book','party_set','wedding_binder'].includes(family)) {
          values.recipient=data.recipient || ''; values.occasion_date=data.occasion_date || ''
          const bodies=(data.page_bodies || '').split(/\n\s*\n/)
          values.pages=spec.content.map((title, i) => ({title,body:bodies[i] || ''}))
        }
        if (family === 'wedding_workbook') {
          values.capacity=Number(data.capacity || 100); values.currency=data.currency || 'USD'
          values.budget=(data.budget_rows || '').split('\n').filter(x => x.trim()).map(line => {
            const [category,item,estimated,actual,paid]=line.split('|').map(x=>x.trim())
            if (![estimated || '0',actual || '0',paid || '0'].every(x=>Number.isFinite(Number(x)))) throw new Error('Budget amounts must be numbers.')
            return {category,item,estimated:estimated || '',actual:actual || '',paid:paid || ''}
          })
          values.guests=(data.guest_rows || '').split('\n').filter(x=>x.trim()).map(line=>{const [household,name,rsvp,meal]=line.split('|').map(x=>x.trim());return {household,name,rsvp:rsvp || 'Pending',meal:meal || '',notes:''}})
        }
        if (family === 'bundle') {
          const ids=new FormData(form).getAll('component').map(String)
          values.components=(catalog.data?.jobs || []).filter(job=>ids.includes(job.id)).map(job=>({job_id:job.id,revision:job.revision,artifact_fingerprint:job.result?.manifest?.artifact_fingerprint}))
        }
        if (family === 'pet_portrait') {values.pet_name=data.pet_name || ''; values.date=data.portrait_date || ''; values.likeness_reviewed=data.likeness_reviewed==='on'}
        if (family === 'crochet_pattern') {
          values.author=data.author; values.tested_revision=data.tested_revision
          values.materials=(data.materials_list || '').split('\n').filter(Boolean)
          values.instructions=(data.pattern_instructions || '').split('\n').filter(Boolean)
          values.gauge=data.gauge || '';values.dimensions=data.dimensions || ''
          values.chart=(data.authored_chart || '').split('\n').filter(line=>line.trim()).map(line=>line.split(',').map(symbol=>symbol.trim()))
          if (data.maker_attested !== 'on') throw new Error('Confirm that the documented maker test used these exact instructions and materials.')
          const source = await productionRequest<{fingerprint:string}>('/pattern-fingerprint', {product_data:values})
          setPatternFingerprint(source.fingerprint)
          values.maker_test={tester:data.tester,completed_at:data.test_date,notes:data.test_notes,source_fingerprint:source.fingerprint}
        }
        Object.assign(spec,{delivery_kind:physical ? 'physical' : family==='pet_portrait' ? 'made_to_order_digital' : 'instant_download',
          product_data:values,creative_note:data.creative_note,instructions:data.instructions,compatibility:initial?.compatibility || [],
          cost_plan:costPlanEnabled&&!physical&&family!=='pet_portrait'?costPlanFromForm(data):null})
      }
      mutation.mutate({path: recipe ? '/profiles' : '/jobs', body: recipe ? {spec, enabled: false, facts_reviewed: true} : {spec, product_id: productId}})
    } catch (problem) {setError(problem instanceof SyntaxError ? 'Provider configuration must be valid JSON.' : problem instanceof Error ? problem.message : 'Check the product fields before saving.')}
  }
  return <form aria-label="Production specification" className="mt-5 max-w-3xl space-y-5" onChange={event=>{
    const name=(event.target as HTMLInputElement).name
    if (['author','materials_list','pattern_instructions','tested_revision','artwork_id','gauge','dimensions','authored_chart'].includes(name)) {
      const check=event.currentTarget.elements.namedItem('maker_attested') as HTMLInputElement|null
      if(check) check.checked=false
      setPatternFingerprint('')
    }
    if(name==='artwork_id') {const check=event.currentTarget.elements.namedItem('likeness_reviewed') as HTMLInputElement|null;if(check)check.checked=false}
  }} onSubmit={event => {event.preventDefault(); void submit(event.currentTarget)}}>
    <p className="max-w-prose text-sm text-surface-200">Enter actual product facts and original content. Research support is checked by the server. Unvalidated concepts stay labeled.</p>
    {selling.original_direction != null && <aside className="space-y-3 border-l-2 border-surface-500 pl-4 text-sm"><p className="font-semibold">Saved original direction</p><p className="whitespace-pre-wrap leading-relaxed">{String(selling.original_direction)}</p>{Array.isArray(selling.improvements) && <ul className="list-disc space-y-2 pl-5">{selling.improvements.map((value, index) => <li key={index}>{String(value)}</li>)}</ul>}</aside>}
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm">Product name<input name="name" className="input mt-2 w-full" required minLength={3} maxLength={120} defaultValue={initial?.name} /></label>
      <label className="text-sm">Buyer keyword<input name="keyword" className="input mt-2 w-full" required minLength={3} defaultValue={initial?.keyword} /></label>
      <label className="text-sm">Buyer<input name="buyer" className="input mt-2 w-full" required minLength={3} defaultValue={initial?.buyer} /></label>
      <label className="text-sm">Product family<select required className="input mt-2 w-full" value={family} onChange={e => setFamily(e.target.value)}><option value="">Choose the actual product format</option>{productFamilies.map(x => <option key={x} value={x}>{x.replace(/_/g, ' ')}</option>)}</select></label>
    </div>
    <label className="block text-sm">Purpose and promised contents<textarea className="input mt-2 min-h-24 w-full" name="purpose" required minLength={10} defaultValue={initial?.purpose} /></label>
    <label className="block text-sm">Original content · one page heading, prompt, or artwork line per row<textarea className="input mt-2 min-h-24 w-full" name="content" required defaultValue={initial?.content.join('\n')} /></label>
    {v2 && <fieldset className="space-y-4 border-y border-surface-600 py-5"><legend className="font-semibold">Original product details</legend>
      <p className="max-w-prose text-sm text-surface-200">Describe your individual creative choices. Keep real customer names and photos in private order intake after approving the reusable product.</p>
      <label className="block text-sm">Your creative direction<textarea className="input mt-2 w-full" name="creative_note" required minLength={10} defaultValue={initial?.creative_note} /></label>
      <label className="block text-sm">Customer instructions<textarea className="input mt-2 min-h-24 w-full" name="instructions" required minLength={10} defaultValue={initial?.instructions} /></label>
      {['birthday_magazine','birthday_newspaper','memory_book','party_set','wedding_binder'].includes(family) && <>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Example recipient or event name<input className="input mt-2 w-full" name="recipient" defaultValue={String(productData.recipient || '')} /></label><label className="text-sm">Example occasion date<input className="input mt-2 w-full" name="occasion_date" defaultValue={String(productData.occasion_date || '')} /></label></div>
        <label className="block text-sm">Page text · separate pages with a blank line<textarea className="input mt-2 min-h-32 w-full" name="page_bodies" defaultValue={Array.isArray(productData.pages) ? productData.pages.map(page=>String((page as {body?: string}).body || '')).join('\n\n') : ''} /></label>
      </>}
      {family === 'wedding_workbook' && <>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Supported guest rows<input name="capacity" type="number" min="10" max="1000" className="input mt-2 w-full" defaultValue={Number(productData.capacity || 100)} /></label><label className="text-sm">Currency code<input name="currency" maxLength={3} pattern="[A-Z]{3}" className="input mt-2 w-full" defaultValue={String(productData.currency || 'USD')} /></label></div>
        <label className="block text-sm">Example budget rows<textarea name="budget_rows" className="input mt-2 min-h-24 w-full" placeholder="Venue | Room hire | 2500 | 2400 | 500" defaultValue={Array.isArray(productData.budget) ? productData.budget.map(row=>{const r=row as Record<string,unknown>;return [r.category,r.item,r.estimated,r.actual,r.paid].join(' | ')}).join('\n') : ''} /></label><p className="text-xs text-surface-200">One row per line: category | item | estimated cost | actual cost | paid. Use example data only.</p>
        <label className="block text-sm">Example guest rows<textarea name="guest_rows" className="input mt-2 min-h-24 w-full" placeholder="Household A | Example guest | Pending | Vegetarian" defaultValue={Array.isArray(productData.guests) ? productData.guests.map(row=>{const r=row as Record<string,unknown>;return [r.household,r.name,r.rsvp,r.meal].join(' | ')}).join('\n') : ''} /></label><p className="text-xs text-surface-200">One row per line: household | name | Pending, Yes or No | meal.</p>
      </>}
      {family === 'bundle' && <fieldset className="space-y-3"><legend className="text-sm font-semibold">Approved component revisions</legend>{catalog.data?.jobs.filter(job=>['approved','exported'].includes(job.status)).map(job=><label key={job.id} className="flex items-center gap-3 text-sm"><input type="checkbox" name="component" value={job.id} defaultChecked={Array.isArray(productData.components) && productData.components.some(component=>(component as {job_id:string}).job_id===job.id)} />{job.spec.name} · {job.revision.slice(0,8)}</label>)}{!catalog.data?.jobs.some(job=>['approved','exported'].includes(job.status)) && <p className="text-sm text-surface-200">Approve the workbook and binder first, then select their exact revisions here.</p>}</fieldset>}
      {family === 'pet_portrait' && <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Example pet name<input name="pet_name" className="input mt-2 w-full" defaultValue={String(productData.pet_name || '')} /></label><label className="text-sm">Optional date wording<input name="portrait_date" className="input mt-2 w-full" defaultValue={String(productData.date || '')} /></label><p className="text-sm text-surface-200 sm:col-span-2">Requires original portrait artwork or a verified local workflow. Likeness must be reviewed; generation does not prove it.</p><label className="flex items-start gap-3 text-sm sm:col-span-2"><input name="likeness_reviewed" type="checkbox" required />I inspected this original portrait artwork and verified the pet's identity and likeness.</label></div>}
      {family === 'crochet_pattern' && <>
        <label className="block text-sm">Actual maker-test completion date<input name="test_date" type="date" className="input mt-2 w-full" required defaultValue={String((productData.maker_test as {completed_at?:string})?.completed_at || '')} /></label>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Human pattern author<input name="author" className="input mt-2 w-full" required defaultValue={String(productData.author || '')} /></label><label className="text-sm">Tested instruction revision<input name="tested_revision" className="input mt-2 w-full" required defaultValue={String(productData.tested_revision || '')} /></label><label className="text-sm">Maker/tester<input name="tester" className="input mt-2 w-full" required defaultValue={String((productData.maker_test as {tester?:string})?.tester || '')} /></label></div>
        <label className="block text-sm">Materials · one item per line<textarea name="materials_list" className="input mt-2 w-full" required defaultValue={Array.isArray(productData.materials) ? productData.materials.join('\n') : ''} /></label>
        <label className="block text-sm">Human-written pattern instructions<textarea name="pattern_instructions" className="input mt-2 min-h-32 w-full" required defaultValue={Array.isArray(productData.instructions) ? productData.instructions.join('\n') : ''} /></label>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Maker-measured gauge<input name="gauge" className="input mt-2 w-full" defaultValue={String(productData.gauge || '')} /></label><label className="text-sm">Finished dimensions<input name="dimensions" className="input mt-2 w-full" defaultValue={String(productData.dimensions || '')} /></label></div>
        <label className="block text-sm">Optional maker-authored stitch chart<textarea name="authored_chart" className="input mt-2 w-full" placeholder="sc,sc,inc,sc" defaultValue={Array.isArray(productData.chart) ? productData.chart.map(row=>(row as string[]).join(',')).join('\n') : ''} /><span className="mt-2 block text-xs text-surface-200">One comma-separated row per line. Symbols: sc, dc, ch, inc, dec, slst, .</span></label>
        <label className="block text-sm">Documented maker-test result<textarea name="test_notes" className="input mt-2 w-full" required minLength={10} defaultValue={String((productData.maker_test as {notes?:string})?.notes || '')} /></label>
        <label className="flex items-start gap-3 text-sm"><input name="maker_attested" type="checkbox" required />The documented maker test used these exact human-written instructions and materials.</label>
        {patternFingerprint && <p className="break-all text-xs text-surface-200">Tested source fingerprint: {patternFingerprint}</p>}
        <p className="text-sm text-surface-200">Import the real finished-object photo below. Formatting and arithmetic checks do not replace making and testing the pattern.</p>
      </>}
    </fieldset>}
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="text-sm">Size<select name="size" className="input mt-2 w-full" defaultValue={initial?.size || 'letter'}>{(physical ? ['provider'] : ['wall_art','pet_portrait'].includes(family) ? ['8x10', '12x16'] : ['letter', 'a4']).map(x => <option key={x}>{x}</option>)}</select></label>
      <label className="text-sm">Palette<select name="palette" className="input mt-2 w-full" defaultValue={initial?.palette || 'ink'}>{['ink', 'sage', 'clay'].map(x => <option key={x}>{x}</option>)}</select></label>
      <label className="text-sm">Layout<select name="layout" className="input mt-2 w-full" defaultValue={initial?.layout || 'classic'}>{['classic', 'editorial', 'minimal'].map(x => <option key={x}>{x}</option>)}</select></label>
    </div>
    <label className="block text-sm">Personalized wording<input className="input mt-2 w-full" name="personalization" maxLength={80} defaultValue={initial?.personalization} /></label>
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="text-sm">Actual selling price · USD<input className="input mt-2 w-full" name="price" type="number" min="0.01" step="0.01" defaultValue={initial?.price ?? ''} /></label>
      <label className="text-sm">Total variable cost · USD<input className="input mt-2 w-full" name="unit_cost" disabled={costPlanAllowed&&costPlanEnabled} type="number" min="0" step="0.01" defaultValue={initial?.unit_cost ?? ''} /></label>
      <label className="text-sm">Verified Etsy taxonomy ID<input className="input mt-2 w-full" name="category_id" type="number" min="1" defaultValue={initial?.category_id ?? ''} /></label>
    </div>
    {v2&&!physical&&family!=='pet_portrait'&&<ProductionCostPlan initial={initial?.cost_plan} enabled={costPlanEnabled} toggle={setCostPlanEnabled}/>}
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

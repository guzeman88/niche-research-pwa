import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { COST_FIELDS, COST_LABELS, download, validationRequest, values } from '../lib/productValidation'
import type { ValidationProject } from '../lib/productValidation'
import ValidationOrderImport from './ValidationOrderImport'
import ValidationImportPreview from './ValidationImportPreview'

function Field({name, title, type = 'text', required = false, value}: {name: string; title: string; type?: string; required?: boolean; value?: string}) {
  return <label className="block text-sm text-surface-100">{title}<input className="input mt-2 w-full" name={name} type={type} min={type === 'number' ? 0 : undefined} step={type === 'number' ? 'any' : undefined} required={required} defaultValue={value} /></label>
}
function Form({title, children, save, button = 'Save evidence', success = 'Saved locally. Use Retry backup sync to update the database mirror.'}: {title: string; children: ReactNode; save: (data: Record<string, string>) => Promise<void>; button?: string; success?: string}) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = values(event.currentTarget); setBusy(true); setMessage('')
    try {await save(data); setMessage(success)}
    catch (error) {setMessage(error instanceof Error ? error.message : 'Unable to save evidence.')}
    finally {setBusy(false)}
  }
  return <form className="space-y-4" onSubmit={submit}><h3 className="text-lg font-semibold">{title}</h3>{children}<button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : button}</button>{message && <p role="status" className="text-sm text-surface-100">{message}</p>}</form>
}

export function CreateValidation({refresh}: {refresh: () => Promise<void>}) {
  return <Form title="Add a product concept" button="Create validation queue" save={async data => {
    await validationRequest('/projects', {...data, keywords: data.keywords.split('\n')}); await refresh()
  }}><Field name="name" title="Product concept" required /><Field name="product_type" title="Product type" required />
    <label className="block text-sm">Buyer keywords · one per line, up to 15<textarea className="input mt-2 min-h-28 w-full" name="keywords" required /></label>
  </Form>
}

export default function ValidationForms({project, refresh}: {project: ValidationProject; refresh: () => Promise<void>}) {
  const [tab, setTab] = useState('Demand')
  const [preview, setPreview] = useState<{rows: number; preview: Array<Record<string, unknown>>; data: Record<string, string>} | null>(null)
  const [importMessage, setImportMessage] = useState('')
  const [collectKeyword, setCollectKeyword] = useState(project.keywords[0]), [collectBusy, setCollectBusy] = useState(false)
  const date = new Date().toISOString().slice(0, 10)
  const save = async (kind: string, data: unknown) => {await validationRequest(`/projects/${project.id}/${kind}`, data); await refresh()}
  const keyword = <label className="block text-sm">Buyer keyword<select className="input mt-2 w-full" name="keyword">{project.keywords.map(k => <option key={k}>{k}</option>)}</select></label>
  return <section className="mt-8 border-t border-surface-600 pt-6">
    <h2 className="text-xl font-semibold">Complete the evidence</h2>
    <div className="my-4 flex flex-wrap gap-2" role="group" aria-label="Evidence forms">{['Demand', 'Competitors', 'Costs', 'Outcomes', 'Google'].map(name => <button key={name} className={tab === name ? 'btn-primary' : 'btn-secondary'} aria-pressed={tab === name} onClick={() => {setTab(name); setPreview(null)}}>{name}</button>)}</div>
    <div className="max-w-3xl">
      {tab === 'Demand' && <Form title="Record Etsy Marketplace Insights" save={data => save('market', data)}>{keyword}
        <p className="text-sm text-surface-200">Copy searches and listing counts from the same dated Etsy reporting window. This form does not require an API key.</p>
        <div className="grid gap-4 sm:grid-cols-2"><Field name="period_start" title="Period start" type="date" required /><Field name="period_end" title="Period end" type="date" required /><Field name="searches" title="Etsy searches" type="number" required /><Field name="listings" title="Competing listings" type="number" required /><Field name="observed_at" title="Date recorded" type="date" value={date} required /><Field name="geography" title="Geography shown, if available" /></div>
        <Field name="source_note" title="Source note or saved evidence reference" required />
      </Form>}
      {tab === 'Competitors' && <Form title="Inspect comparable listings" save={data => save('competitors', data)}>{keyword}
        <p className="text-sm text-surface-200">Keep comparable product types and original currencies. Record 20 samples initially. API samples still need a relevance review.</p>
        <button type="button" className="btn-secondary" onClick={() => download('competitor-template.csv', 'listing_id,shop_id,title,price,currency,shipping,differentiation_note\n', 'text/csv')}>Download competitor template</button>
        <Field name="observed_at" title="Sample date" type="date" value={date} required /><Field name="source" title="Sample source" required /><Field name="filters" title="Search filters and relevance review" required />
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" name="relevance_reviewed" className="mt-1" />I reviewed these samples for comparable products and relevance.</label>
        <label className="block text-sm">Competitor CSV<textarea name="text" className="input mt-2 min-h-36 w-full" required /></label>
        <label className="block text-sm">Keyword to collect from Etsy<select className="input mt-2 w-full" value={collectKeyword} onChange={event => setCollectKeyword(event.target.value)}>{project.keywords.map(k => <option key={k}>{k}</option>)}</select></label>
        <button type="button" disabled={collectBusy} className="btn-secondary" onClick={async () => {
          setCollectBusy(true)
          setImportMessage('Collecting from Etsy…')
          try {await validationRequest(`/projects/${project.id}/collect-etsy`, {keyword: collectKeyword}); await refresh(); setImportMessage('API samples saved. Review their relevance before relying on them.')}
          catch (error) {setImportMessage(error instanceof Error ? error.message : 'Collection failed.')}
          finally {setCollectBusy(false)}
        }}>{collectBusy ? 'Collecting…' : 'Collect selected keyword with Etsy API'}</button>
        {importMessage && <p role="status" className="text-sm">{importMessage}</p>}
      </Form>}
      {tab === 'Costs' && <Form title="Calculate product economics" save={async data => {
        const scenarios = Object.fromEntries(['conservative', 'base', 'optimistic'].map(name => [name, Object.fromEntries(['price', ...COST_FIELDS, 'setup', 'fixed_monthly'].map(field => [field, data[`${name}.${field}`] || null]))]))
        await save('economics', {source: data.source, observed_at: data.observed_at, currency: data.currency, scenarios})
      }}><p className="text-sm text-surface-200">Enter your own assumptions for each scenario. Blank costs stay unknown; enter 0 only when the cost truly does not apply. Monthly fixed expenses use a one-month break-even horizon.</p>
        <div className="grid gap-4 sm:grid-cols-2"><Field name="source" title="Cost and fee sources" required /><Field name="currency" title="Currency" value="USD" required /><Field name="observed_at" title="Cost evidence date" type="date" value={date} required /></div>
        {['conservative', 'base', 'optimistic'].map(name => <fieldset key={name} className="border-t border-surface-600 pt-4"><legend className="pr-3 text-base font-semibold capitalize">{name}</legend><div className="grid gap-4 sm:grid-cols-2">{['price', ...COST_FIELDS, 'setup', 'fixed_monthly'].map(field => <Field key={field} name={`${name}.${field}`} title={`${name} ${COST_LABELS[field]}`} type="number" required={field === 'price'} />)}</div></fieldset>)}
      </Form>}
      {tab === 'Outcomes' && <>
        <ValidationOrderImport projectId={project.id} refresh={refresh} />
        <Form title="Record one listing's results" save={data => save('outcome', data)}><p className="text-sm text-surface-200">Use non-overlapping periods. Each listing period belongs to one concept. Missing traffic or costs stay unknown; visits and listing views are different metrics.</p>
          <div className="grid gap-4 sm:grid-cols-2"><Field name="shop_id" title="Your shop ID" required /><Field name="listing_id" title="Your listing ID" required /><Field name="period_start" title="Results period start" type="date" required /><Field name="period_end" title="Results period end" type="date" required /><Field name="source" title="Results source" required /><Field name="currency" title="Results currency" value="USD" required />{['impressions', 'clicks', 'visits', 'orders', 'revenue', ...COST_FIELDS, 'setup_expenses', 'fixed_expenses'].map(field => <Field key={field} name={field} title={`Observed ${COST_LABELS[field] || field.replace(/_/g, ' ')}`} type="number" />)}</div>
        </Form>
        <div className="mt-8 border-t border-surface-600 pt-6"><Form title="Import a listing-results worksheet" button="Preview import" success="Preview prepared. Review the rows before committing." save={async data => {
          const result = await validationRequest<{rows: number; preview: Array<Record<string, unknown>>}>(`/projects/${project.id}/outcomes/import`, data); setPreview({...result, data})
        }}><p className="text-sm text-surface-200">Combine order/payment exports and Stats into the template using verified listing IDs. Do not paste raw order exports here or repeat an order across keywords.</p>
          <button type="button" className="btn-secondary" onClick={() => download('listing-results-template.csv', ['shop_id', 'listing_id', 'period_start', 'period_end', 'currency', 'impressions', 'clicks', 'visits', 'orders', 'revenue', ...COST_FIELDS, 'setup_expenses', 'fixed_expenses'].join(',') + '\n', 'text/csv')}>Download results template</button>
          <Field name="source" title="Worksheet sources" required /><label className="block text-sm">Results CSV<textarea name="text" className="input mt-2 min-h-36 w-full" required onChange={() => setPreview(null)} /></label>
        </Form>{preview && <div className="mt-4 space-y-3"><p>{preview.rows} rows passed validation. No results have been imported yet.</p><ValidationImportPreview rows={preview.preview} /><button className="btn-primary" onClick={async () => {
          try {await validationRequest(`/projects/${project.id}/outcomes/import?commit=true`, preview.data); setPreview(null); await refresh(); setImportMessage('Worksheet imported.')}
          catch (error) {setImportMessage(error instanceof Error ? error.message : 'Import failed.')}
        }}>Commit reviewed worksheet</button></div>}{importMessage && <p role="status" className="mt-3 text-sm">{importMessage}</p>}</div>
      </>}
      {tab === 'Google' && <Form title="Import Google collector evidence" save={data => save('google', {package: JSON.parse(data.package)})}>
        <p className="text-sm text-surface-200">Use the Google Validation Evidence workflow and import its JSON artifact. Close variants stay grouped. Google volume is supporting demand evidence, and advertiser competition is kept separate from Etsy seller competition.</p>
        <label className="block text-sm">Collector JSON<textarea className="input mt-2 min-h-44 w-full" name="package" required /></label>
      </Form>}
    </div>
  </section>
}

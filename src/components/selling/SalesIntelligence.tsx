import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {intelligenceRequest as request, type ReferenceSource, type ReferenceOverview, type ReferenceComparison, type ReferenceModel, type ResearchJob, type ImportPreview} from '../../lib/salesIntelligence'
import {number, text} from '../../lib/sellingProducts'
import {IntelligenceCoverage, IntelligenceOpportunities} from './IntelligenceCoverage'
import ReferenceHistory from './ReferenceHistory'

const date = (value: string | null) => value ? new Date(value).toLocaleString() : 'Unknown'
const errorText = (cause: unknown) => cause instanceof Error ? cause.message : 'Research request failed. Try again.'

export default function SalesIntelligence({onInvestigate}: {onInvestigate: (id: string) => void}) {
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(30), [unit, setUnit] = useState('purchases'), [objective, setObjective] = useState('consensus')
  const [tab, setTab] = useState('compare'), [search, setSearch] = useState(''), [page, setPage] = useState(0)
  const [selected, setSelected] = useState(''), [message, setMessage] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const overview = useQuery({queryKey: ['sales-intelligence', search, page], queryFn: () => request<ReferenceOverview>(`?${new URLSearchParams({q: search, page: String(page)})}`), retry: false, refetchInterval: 30000})
  const sources = useQuery({queryKey: ['intelligence-sources'], queryFn: () => request<{items: ReferenceSource[]}>('/sources'), enabled: open, retry: false})
  const comparison = useQuery({queryKey: ['intelligence-comparison', selected], queryFn: () => request<ReferenceComparison>(`/listings/${selected}/comparison`), enabled: open && Boolean(selected), retry: false})
  const jobs = useQuery({queryKey: ['intelligence-jobs'], queryFn: () => request<{items: ResearchJob[]}>('/jobs'), enabled: open && tab === 'learning', retry: false, refetchInterval: 15000})
  const models = useQuery({queryKey: ['intelligence-models'], queryFn: () => request<{items: ReferenceModel[]; actual_outcomes: number}>('/models'), enabled: open && tab === 'learning', retry: false, refetchInterval: 30000})
  const action = async (path: string, body: unknown = {}) => {
    setBusy(true); setError(''); setMessage('')
    try {const result = await request<{reason?: string; status?: string}>(path, body); setMessage(result.reason || (result.status === 'queued' ? 'Request queued. Research jobs update here as they finish.' : 'Research settings updated.')); await Promise.all([overview.refetch(), sources.refetch(), jobs.refetch(), models.refetch()])}
    catch (cause) {setError(errorText(cause))} finally {setBusy(false)}
  }
  const data = overview.data
  return <section aria-label="Sales intelligence" className="my-8 border-b border-surface-600 pb-8">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h2 className="text-lg font-semibold">Sales intelligence</h2><p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">Compare dated sales estimates, inspect disagreements and track what our model learns. Actual seller outcomes remain separate.</p></div>
      <button className="btn-secondary" aria-expanded={open} aria-controls="sales-intelligence-workspace" onClick={() => setOpen(value => !value)}>{open ? 'Close sales intelligence' : 'Open sales intelligence'}</button>
    </div>
    {data && <p className="mt-4 text-sm tabular-nums text-surface-200">{number(data.coverage.reference_listings)} listings with provider references · {number(data.coverage.observations)} retained readings · {number(data.coverage.outcomes)} actual outcome records</p>}
    {data && data.automated_provider_feeds === 0 && <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">Provider feeds need verified free access. Saved catalog history updates automatically; importing an export does not automate obtaining that export.</p>}
    {open && <div id="sales-intelligence-workspace">
    <nav aria-label="Sales intelligence sections" className="my-5 flex flex-wrap gap-2">
      {['compare', 'opportunities', 'coverage', 'sources', 'learning', 'import'].map(value => <button key={value} className={tab === value ? 'btn-primary' : 'btn-secondary'} aria-pressed={tab === value} onClick={() => setTab(value)}>{text(value)}</button>)}
    </nav>
    {message && <p role="status" className="my-4 text-sm text-surface-200">{message}</p>}
    {(error || overview.error) && <div role="alert" className="my-4 text-sm text-accent-amber"><p>{error || overview.error?.message}</p><button className="btn-secondary mt-3" onClick={() => void overview.refetch()}>Retry research</button></div>}
    {tab === 'coverage' && <IntelligenceCoverage />}
    {tab === 'opportunities' && <IntelligenceOpportunities onSelect={id => {setSelected(id); setTab('compare')}} />}
    {tab === 'compare' && <>
      <div className="grid gap-4 sm:grid-cols-2"><label className="min-w-0 text-sm">Find a saved listing<input className="input mt-2 w-full" type="search" maxLength={200} value={search} onChange={event => {setSearch(event.target.value); setPage(0)}} /></label>
        <form className="flex min-w-0 items-end gap-3" onSubmit={event => {event.preventDefault(); const id = new FormData(event.currentTarget).get('listing_id'); setSelected(String(id || ''))}}><label className="min-w-0 flex-1 text-sm">Compare Etsy listing ID<input className="input mt-2 w-full" name="listing_id" inputMode="numeric" pattern="[0-9]{1,30}" required /></label><button className="btn-secondary">Compare</button></form>
      </div>
      <button className="btn-secondary mt-4" disabled={busy} onClick={() => void action('/catalog/refresh')}>Refresh saved history</button>
      {overview.isPending && <p role="status" className="py-5 text-sm">Loading saved history…</p>}
      {data && <>
        {data.items.length === 0 && <p className="py-5 text-sm text-surface-200">{search ? 'No saved products match this search.' : 'Historical catalog indexing has not added any listings yet. Refresh saved history to queue a bounded pass.'}</p>}
        <ul className="mt-5 divide-y divide-surface-700">{data.items.map(item => <li key={item.listing_id} className="flex min-w-0 flex-wrap items-start justify-between gap-3 py-4"><div className="min-w-0 flex-1"><button className="break-words text-left text-sm font-semibold underline-offset-4 hover:underline" onClick={() => setSelected(item.listing_id)}>{item.title || `Listing ${item.listing_id}`}</button><p className="mt-1 text-xs text-surface-300">{item.shop || 'Shop unknown'} · {item.price == null ? 'Price unknown' : `${number(item.price)} ${item.currency}`} · captured {date(item.captured_at)}</p></div><a className="text-sm underline underline-offset-4" href={`https://www.etsy.com/listing/${item.listing_id}`} target="_blank" rel="noreferrer">View listing</a></li>)}</ul>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-sm"><button className="btn-secondary" disabled={page === 0} onClick={() => setPage(value => value - 1)}>Previous history</button><span>{number(data.total)} saved listings · page {page + 1}</span><button className="btn-secondary" disabled={(page + 1) * data.limit >= data.total} onClick={() => setPage(value => value + 1)}>Next history</button></div>
      </>}
      {selected && <div className="mt-8 border-t border-surface-600 pt-6" aria-label="Selected listing comparison">
        <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-base font-semibold">Listing {selected}</h3><button className="btn-secondary" disabled={busy} onClick={async () => {setBusy(true); setError(''); try {const item = await request<{id: string}>(`/listings/${selected}/investigate`, {}); onInvestigate(item.id); document.getElementById('opportunity-workspace')?.scrollIntoView({behavior: 'instant', block: 'start'}); document.getElementById('opportunity-workspace')?.focus({preventScroll: true})} catch (cause) {setError(errorText(cause))} finally {setBusy(false)}}}>Investigate this product</button></div>
        {comparison.isPending && <p role="status" className="mt-3 text-sm">Loading compatible references…</p>}
        {comparison.error && <p role="alert" className="mt-3 text-sm text-accent-amber">{comparison.error.message}</p>}
        {comparison.data && <ListingComparison value={comparison.data} />}
      </div>}
    </>}
    {tab === 'sources' && <>
      <div className="flex flex-wrap items-center gap-3"><p className="max-w-2xl flex-1 text-sm leading-relaxed text-surface-200">All 24 research leads remain visible. A free offer is separate from working collection and model-use permission.</p><button className="btn-secondary" disabled={busy} onClick={() => void action('/pause', {paused: !data?.coverage.paused})}>{data?.coverage.paused ? 'Resume research worker' : 'Pause research worker'}</button></div>
      {sources.error && <p role="alert" className="mt-4 text-sm">{sources.error.message}</p>}
      <ul className="mt-4 divide-y divide-surface-700">{sources.data?.items.map(source => <li key={source.id} className="grid gap-3 py-5 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0"><h3 className="text-sm font-semibold"><a className="underline underline-offset-4" href={source.url} target="_blank" rel="noreferrer">{source.name}</a> · {text(source.disposition)}{source.paused ? ' · paused' : ''}</h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">{source.reason}</p>
          <p className="mt-2 text-xs text-surface-300">Storage: {source.capabilities.storage ? 'recorded' : 'unverified'} · Model use: {source.capabilities.training ? 'recorded' : 'unverified'} · {text(source.automation)} · reviewed {source.reviewed_on}</p>
          <p className="mt-2 text-xs text-surface-300">Collection: {text(source.health.status)}{source.health.last_success ? ` · last success ${date(source.health.last_success)}` : ''}{source.health.retry_at ? ` · retry after ${date(source.health.retry_at)}` : ''}{source.access_review_at ? ` · access review ${date(source.access_review_at)}` : ''}</p>
          {source.allowance && <p className="mt-2 text-sm tabular-nums text-surface-200">Free allowance: {number(source.allowance.remaining)} / {number(source.allowance.limit)} remaining · {text(source.allowance.period)}{source.allowance.next_reset ? ` · resets ${date(source.allowance.next_reset)}` : ' · no recurring reset'}</p>}
        </div><div className="flex items-start gap-2"><button className="btn-secondary" disabled={busy} onClick={() => void action(`/sources/${source.id}/test`)}>Check {source.name}</button><button className="btn-secondary" disabled={busy} onClick={() => void action(`/sources/${source.id}/${source.paused ? 'resume' : 'pause'}`)}>{source.paused ? 'Resume' : 'Pause'}</button></div>
      </li>)}</ul>
    </>}
    {tab === 'learning' && <>
      <h3 className="text-base font-semibold">Learning from reference estimates</h3><p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">The student learns compatible provider consensus. Its agreement score measures that objective; actual purchase accuracy requires separate seller outcomes. The independent model remains in each opportunity’s Sales model section.</p>
      <div className="my-5 grid max-w-3xl gap-4 sm:grid-cols-3"><label className="text-sm">Target window<select className="input mt-2 w-full" value={days} onChange={event => setDays(Number(event.target.value))}><option value={30}>30 days</option><option value={7}>7 days</option></select></label><label className="text-sm">Target unit<select className="input mt-2 w-full" value={unit} onChange={event => setUnit(event.target.value)}><option value="purchases">Purchases</option><option value="units">Units</option></select></label><label className="text-sm">Learning objective<select className="input mt-2 w-full" value={objective} onChange={event => setObjective(event.target.value)}><option value="consensus">Provider consensus</option><option value="actual">Actual seller outcomes</option></select></label></div>
      <div className="my-5 flex flex-wrap gap-3"><button className="btn-secondary" disabled={busy} onClick={() => void action('/panels', {size: 30})}>Create 30-listing reference panel</button><button className="btn-secondary" disabled={busy} onClick={() => void action('/models/train', {days, unit, objective})}>{objective === 'consensus' && days === 30 && unit === 'purchases' ? 'Queue 30-day purchase model' : 'Queue selected model'}</button><button className="btn-secondary" disabled={busy} onClick={() => void action('/models/rollback', {days, unit, lane: objective === 'actual' ? 'actual_outcome' : 'consensus_student'})}>Restore previous model</button></div>
      <p className="my-4 max-w-3xl text-sm leading-relaxed text-surface-200">The actual-outcome lane requires 200 eligible windows across 25 identified shops, later validation/test shops, enough zero sellers, baseline improvement and bias/category checks. Passing software gates only supports the measured held-out sample.</p>
      {models.error && <p role="alert" className="my-3 text-sm">{models.error.message}</p>}
      {models.data?.items.length === 0 && <p className="my-4 max-w-3xl text-sm text-surface-200">No fitted consensus model. Training needs at least 100 eligible, nonoverlapping listing/window labels across 20 shops and separate earlier training, validation and later test periods. This minimum does not establish accuracy.</p>}
      {models.data?.items.map(model => <div key={model.id} className="border-t border-surface-700 py-4">
        <h4 className="text-sm font-semibold">{model.model.days}-day {model.model.unit} · {text(model.model.lane)} · {model.active ? 'active' : text(model.status)}</h4>
        <p className="mt-2 text-sm text-surface-200">{model.model.training_cases} training cases · {model.model.evaluation.cases} held-out cases / {model.model.evaluation.shops} shops · {model.model.lane === 'actual_outcome' ? 'actual-outcome' : 'consensus'} MAE {number(model.model.evaluation.mae)} · baseline {number(model.model.evaluation.baseline_mae)}</p>
        {model.actual_evaluation && <p className="mt-2 text-sm text-surface-200">Later actual-outcome audit: {text(model.actual_evaluation.status)} · {model.actual_evaluation.cases} cases / {model.actual_evaluation.shops} shops · MAE {number(model.actual_evaluation.mae)} · baseline {number(model.actual_evaluation.baseline_mae)}</p>}
        <p className="mt-2 text-xs text-surface-300">Created {date(model.created_at)} · {model.eligible ? 'eligibility current' : 'source eligibility or feature version stale'}</p>
        <div className="mt-3 flex flex-wrap gap-3"><button className="btn-secondary" disabled={busy || !model.eligible || !['qualified_experimental', 'qualified_outcome_tested'].includes(model.status)} onClick={() => void action(`/models/${model.id}/activate`)}>Use qualified model</button><button className="btn-secondary" disabled={busy} onClick={() => void action(`/models/${model.id}/evaluate`)}>Evaluate actual outcomes</button></div>
      </div>)}
      <details className="my-5"><summary className="cursor-pointer text-sm font-semibold">Recent research jobs</summary><ul className="mt-3 divide-y divide-surface-700">{jobs.data?.items.map(job => <li className="py-3 text-sm" key={job.id}>{text(job.status)} · {date(job.due_at)}{job.result?.reason && <p className="mt-1 text-surface-200">{job.result.reason}</p>}{job.result?.error && <p className="mt-1 text-accent-amber">Job stopped: {job.result.error}</p>}{job.result?.status && <p className="mt-1 text-surface-200">{text(job.result.status)}{job.result.cases !== undefined ? ` · ${job.result.cases} eligible cases` : ''}</p>}</li>)}</ul></details>
      <OutcomeImport />
    </>}
    {tab === 'import' && <ReferenceImport sources={sources.data?.items || []} onImported={() => {void overview.refetch(); void comparison.refetch()}} />}
    </div>}
  </section>
}

function ListingComparison({value}: {value: ReferenceComparison}) {
  return <div className="mt-3 space-y-5">
    {value.metadata && <p className="break-words text-sm text-surface-200">{value.metadata.title}</p>}
    {value.consensus.cohorts.length === 0 && <p className="max-w-3xl text-sm leading-relaxed text-surface-200">No eligible compatible sales estimates. Sales remain unknown; catalog favorites and prices do not establish purchases.</p>}
    {value.consensus.cohorts.map(cohort => <div key={cohort.fingerprint} className="border-y border-surface-700 py-4"><h4 className="text-sm font-semibold">{text(cohort.basis)} · {cohort.unit} · {text(cohort.status)}</h4>{cohort.period_start && <p className="mt-2 text-xs text-surface-300">{date(cohort.period_start)} to {date(cohort.period_end)} · end exclusive</p>}<p className="mt-3 text-base font-semibold">Provider center {number(cohort.center)} <span className="text-sm font-normal text-surface-200">· mean {number(cohort.mean)} · source spread {number(cohort.minimum)}–{number(cohort.maximum)}</span></p><p className="mt-2 text-sm text-surface-200">{cohort.source_count} providers / {cohort.group_count} method groups. Spread describes disagreement, not a confidence interval.</p>
      <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Compatible provider estimates</caption><thead><tr className="border-b border-surface-600"><th className="py-2 pr-4 font-semibold" scope="col">Source</th><th className="py-2 pr-4 font-semibold" scope="col">Estimate</th><th className="py-2 font-semibold" scope="col">Captured</th></tr></thead><tbody>{cohort.readings.map(reading => <tr key={reading.id} className="border-b border-surface-700"><td className="py-3 pr-4">{reading.source_id}</td><td className="py-3 pr-4 tabular-nums">{number(reading.value)}</td><td className="py-3">{date(reading.captured_at)}</td></tr>)}</tbody></table></div></div>)}
    <p className="text-sm">EtGen independent model: {value.independent_model.value == null ? text(value.independent_model.status) : `${number(value.independent_model.value)} purchases / 30 days · provisional`}</p>
    <p className="text-sm">EtGen student: {value.student.value == null ? text(value.student.status) : `${number(value.student.value)} ${value.student.unit} / ${value.student.days} days · experimental consensus estimate`}</p>
    <p className="text-sm">EtGen outcome model: {value.outcome_model.value == null ? text(value.outcome_model.status) : `${number(value.outcome_model.value)} ${value.outcome_model.unit} / ${value.outcome_model.days} days · estimate from an outcome-tested model`}</p>
    {value.consensus.excluded.length > 0 && <details><summary className="cursor-pointer text-sm">Excluded references · {value.consensus.excluded.length}</summary><ul className="mt-3 space-y-2 text-sm text-surface-200">{value.consensus.excluded.map(row => <li key={row.id}>{row.source_id} · {text(row.reason)}</li>)}</ul></details>}
    <ReferenceHistory readings={value.history} />
  </div>
}

function ReferenceImport({sources, onImported}: {sources: ReferenceSource[]; onImported: () => void}) {
  const [content, setContent] = useState(''), [format, setFormat] = useState('json'), [source, setSource] = useState('muadzo')
  const [basis, setBasis] = useState('provider_monthly'), [unit, setUnit] = useState('unknown'), [column, setColumn] = useState('monthly_sales')
  const [ref, setRef] = useState(''), [captured, setCaptured] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null), [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false)
  const packet = () => ({source_id: source, format, content, basis, unit, value_column: column, source_ref: ref,
    captured_at: captured ? new Date(captured).toISOString() : undefined, available_at: new Date().toISOString(),
    period_start: basis === 'period' && start ? new Date(start).toISOString() : undefined,
    period_end: basis === 'period' && end ? new Date(end).toISOString() : undefined})
  const [prepared, setPrepared] = useState<ReturnType<typeof packet> | null>(null)
  const change = () => {setPreview(null); setPrepared(null); setNotice('')}
  const submit = async (commit: boolean) => {
    setBusy(true); setError('')
    try {
      if (commit && prepared && preview) {await request('/imports/commit', {...prepared, expected_fingerprint: preview.fingerprint}); change(); setNotice('Reference history imported. Original estimates remain separate from actual outcomes.'); onImported()}
      else {const value = packet(); const result = await request<ImportPreview>('/imports/preview', value); setPrepared(value); setPreview(result)}
    } catch (cause) {setError(errorText(cause))} finally {setBusy(false)}
  }
  return <form className="max-w-4xl space-y-4" aria-label="Import provider references" onSubmit={event => {event.preventDefault(); void submit(false)}} onChange={change}>
    <h3 className="text-base font-semibold">Import dated provider estimates</h3><p className="max-w-3xl text-sm leading-relaxed text-surface-200">Preview CSV mappings or canonical JSON before saving. Storage and model-use eligibility are checked separately against protected source evidence.</p>
    <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Provider<select className="input mt-2 w-full" value={source} onChange={event => setSource(event.target.value)}>{sources.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-sm">Format<select className="input mt-2 w-full" value={format} onChange={event => setFormat(event.target.value)}><option value="json">Canonical JSON array</option><option value="csv">CSV with explicit mapping</option></select></label></div>
    <label className="block text-sm">Choose a research export<input type="file" accept=".json,.csv,text/csv,application/json" className="mt-2 block max-w-full text-sm" onChange={async event => {const file = event.target.files?.[0]; if (file) {if (file.size > 2000000) {setError('Import at most 2 MB.'); return} setContent(await file.text()); setFormat(file.name.toLowerCase().endsWith('.csv') ? 'csv' : 'json'); change()}}} /></label>
    {format === 'csv' && <><div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Sales column after header normalization<input className="input mt-2 w-full" value={column} onChange={event => setColumn(event.target.value)} required /></label><label className="text-sm">Source reference<input className="input mt-2 w-full" value={ref} onChange={event => setRef(event.target.value)} required minLength={3} /></label><label className="text-sm">Reporting basis<select className="input mt-2 w-full" value={basis} onChange={event => setBasis(event.target.value)}>{['provider_monthly', 'period', 'lifetime', 'lifetime_average'].map(item => <option key={item}>{item}</option>)}</select></label><label className="text-sm">Sales unit<select className="input mt-2 w-full" value={unit} onChange={event => setUnit(event.target.value)}>{['unknown', 'purchases', 'units', 'buyers'].map(item => <option key={item}>{item}</option>)}</select></label><label className="text-sm">Original capture time<input className="input mt-2 w-full" type="datetime-local" value={captured} onChange={event => setCaptured(event.target.value)} required /></label></div>{basis === 'period' && <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Period starts<input className="input mt-2 w-full" type="datetime-local" value={start} onChange={event => setStart(event.target.value)} required /></label><label className="text-sm">Period ends · exclusive<input className="input mt-2 w-full" type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} required /></label></div>}</>}
    <label className="block text-sm">Export contents<textarea aria-label="Export contents" className="input mt-2 w-full" rows={8} value={content} onChange={event => setContent(event.target.value)} required maxLength={2000000} spellCheck={false} /></label>
    <button className="btn-secondary" disabled={busy}>{busy ? 'Checking import…' : 'Preview references'}</button>
    {error && <p role="alert" className="text-sm text-accent-amber">{error}</p>}{notice && <p role="status" className="text-sm">{notice}</p>}
    {preview && <div className="space-y-3 border-y border-surface-600 py-4"><p className="text-sm">{preview.accepted} accepted rows · {preview.rejected.length} rejected</p>{preview.blocker && <p className="text-sm text-accent-amber">{preview.blocker}</p>}{preview.rejected.map(row => <p key={row.row} className="text-sm">Row {row.row}: {row.reason}</p>)}
      <ul aria-label="Normalized import preview" className="divide-y divide-surface-700">{preview.sample.map((row, index) => <li key={index} className="py-3 text-sm"><p>Listing {row.listing_id} · {number(row.value)} {row.unit} · {text(row.basis)} · {text(row.precision)}</p><p className="mt-1 text-xs text-surface-300">Captured {date(row.captured_at)}{row.period_start ? ` · ${date(row.period_start)} to ${date(row.period_end)} (end exclusive)` : ''}</p></li>)}</ul>
      <button className="btn-primary" type="button" disabled={busy || !preview.can_commit} onClick={() => void submit(true)}>Save reference history</button></div>}
  </form>
}

function OutcomeImport() {
  const [content, setContent] = useState(''), [fingerprint, setFingerprint] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  return <details className="border-t border-surface-600 pt-4"><summary className="cursor-pointer text-sm font-semibold">Import actual seller outcomes</summary><p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">Authorized aggregate listing counts only. Each JSON row needs listing_id, shop, numeric shop_id, period_start, period_end, available_at, actual, unit, source_ref and an attestation describing the seller records. Remove buyer information. Provider estimates are not actual outcomes.</p><form className="mt-4 max-w-3xl space-y-3" onSubmit={async event => {event.preventDefault(); setBusy(true); try {const result = await request<{fingerprint: string; rows: number; committed: boolean}>('/outcomes/import', {format: 'json', content, expected_fingerprint: fingerprint}); setFingerprint(result.committed ? '' : result.fingerprint); setMessage(result.committed ? `${result.rows} outcome rows retained.` : `${result.rows} valid outcome rows. Review your source records, then confirm.`)} catch (cause) {setMessage(errorText(cause))} finally {setBusy(false)}}}><label className="block text-sm">Actual outcome JSON<textarea aria-label="Actual outcome JSON" className="input mt-2 w-full" rows={6} value={content} onChange={event => {setContent(event.target.value); setFingerprint('')}} maxLength={2000000} required /></label><button className="btn-secondary" disabled={busy}>{fingerprint ? 'Confirm actual outcomes' : 'Preview actual outcomes'}</button>{message && <p role="status" className="text-sm">{message}</p>}</form></details>
}

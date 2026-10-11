import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import ValidationForms, { CreateValidation } from '../components/ValidationForms'
import ValidationEvidence from '../components/ValidationEvidence'
import { readConnection, saveConnection } from '../lib/operatorConnection'
import { display, download, label, validationRequest } from '../lib/productValidation'
import type { ValidationOverview } from '../lib/productValidation'

export default function ProductValidation() {
  const initial = readConnection()
  const [url, setUrl] = useState(initial.url || (['localhost', '127.0.0.1'].includes(location.hostname) ? 'http://127.0.0.1:18020' : ''))
  const [token, setToken] = useState(initial.token), [connected, setConnected] = useState(Boolean(initial.url))
  const [version, setVersion] = useState(0), [selected, setSelected] = useState(''), [message, setMessage] = useState('')
  const query = useQuery<ValidationOverview>({queryKey: ['product-validation', version], queryFn: () => validationRequest(), enabled: connected, retry: false})
  const refresh = async () => {await query.refetch()}
  const current = query.data?.projects.find(project => project.id === selected) || query.data?.projects[0]
  return <main className="page min-h-screen bg-surface-950 text-surface-50">
    <div className="flex flex-wrap items-baseline justify-between gap-4"><h1 className="text-2xl font-semibold">Product validation</h1><Link className="text-sm text-surface-200 underline" to="/evidence">Research tools</Link></div>
    <p className="mt-3 max-w-2xl text-base leading-relaxed text-surface-200">Build evidence for a profitable product: buyer demand, comparable listings, complete costs, and your own sales results.</p>
    <details className="my-6 border-y border-surface-600 py-4" open={!connected}><summary className="cursor-pointer text-sm font-semibold">Research workspace connection</summary>
      <form className="mt-4 grid max-w-3xl gap-4 sm:grid-cols-2" onSubmit={event => {
        event.preventDefault(); try {saveConnection({url, token}); setConnected(true); setVersion(v => v + 1); setMessage('')} catch (error) {setMessage(error instanceof Error ? error.message : 'Invalid connection.')}
      }}><label className="text-sm">Research server address<input className="input mt-2 w-full" type="url" value={url} onChange={event => setUrl(event.target.value)} required /></label>
        <label className="text-sm">Operator token · remote access only<input className="input mt-2 w-full" type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label><button className="btn-secondary w-fit">Connect workspace</button></form>
    </details>
    {query.isLoading && connected && <p role="status">Loading validation records…</p>}
    {query.error && <div role="alert" className="my-4 space-y-3"><p>{query.error.message}</p><button className="btn-secondary" onClick={() => void refresh()}>Retry connection</button></div>}
    {message && <p className="my-4 text-sm" role="status">{message}</p>}
    {query.data && <>
      <div className="my-6 flex flex-wrap items-center gap-3"><span className="text-sm text-surface-200">{query.data.pending_sync} records awaiting database mirror</span>
        <button className="btn-secondary" onClick={async () => {try {const result = await validationRequest<{pending: number; configured: boolean}>('/sync', {}); setMessage(result.configured ? `${result.pending} records still awaiting mirror. Local saves remain available.` : 'Database mirror is not configured. Local records remain saved.'); await refresh()} catch (error) {setMessage(String(error))}}}>Retry backup sync</button>
        <button className="btn-secondary" onClick={async () => {try {const ledger = await validationRequest('/export'); download('product-validation-ledger.json', JSON.stringify(ledger, null, 2)); setMessage('Export downloaded. It contains private research and cost records; store it securely.')} catch (error) {setMessage(String(error))}}}>Export evidence ledger</button>
      </div>
      <details className="mb-6 border-b border-surface-600 pb-6" open={!query.data.projects.length}><summary className="mb-4 cursor-pointer text-base font-semibold">Add a product concept</summary><div className="max-w-xl"><CreateValidation refresh={refresh} /></div></details>
      {query.data.projects.length === 0 && <p className="text-surface-200">Start with three concepts and a focused set of buyer keywords. Your queue will show what evidence each product still needs.</p>}
      {current && <>
        <label className="block max-w-xl text-sm">Product concept<select className="input mt-2 w-full" value={current.id} onChange={event => setSelected(event.target.value)}>{query.data.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <div className="mt-6 flex flex-wrap items-baseline gap-4"><h2 className="text-xl font-semibold">{current.name}</h2><span className="text-sm text-surface-200">{label(current.status)}</span></div>
        <p className="mt-2 text-sm text-surface-200">Readiness indicates whether a controlled test is supported. It is not a probability of profit.</p>
        <div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Demand and competitor evidence checklist</caption><thead className="text-surface-200"><tr>{['Buyer keyword', 'Etsy searches / listings', 'Competitor samples', 'Next action'].map(title => <th className="border-b border-surface-600 px-3 py-3 font-medium" key={title}>{title}</th>)}</tr></thead><tbody>{current.queue.map(row => <tr key={row.keyword} className="align-top"><th scope="row" className="border-b border-surface-700 px-3 py-4 font-medium">{row.keyword}</th><td className="border-b border-surface-700 px-3 py-4">{row.market ? <>{display(row.market.searches)} / {display(row.market.listings)}<span className="mt-1 block text-xs text-surface-200">{row.market.period_start}–{row.market.period_end}</span></> : 'Unknown'}</td><td className="border-b border-surface-700 px-3 py-4">{row.sample_count} listings · {row.distinct_sample_shops} shops</td><td className="border-b border-surface-700 px-3 py-4"><ul className="space-y-2">{row.blockers.length ? row.blockers.map(item => <li key={item}>{item}</li>) : <li>Ready for a controlled test</li>}</ul></td></tr>)}</tbody></table></div>
        <div className="mt-8 border-b border-surface-600 pb-6"><h2 className="text-lg font-semibold">Economics · {current.economics_currency || 'currency unknown'}</h2>{current.economics ? <div className="mt-3 flex flex-wrap gap-8">{Object.entries(current.economics).map(([name, row]) => <div key={name}><h3 className="text-sm font-semibold capitalize">{name}</h3><p className="mt-2 text-sm">Contribution / order: {display(row.contribution_per_order)}</p><p className="mt-1 text-sm text-surface-200">First-month break-even: {display(row.first_month_break_even_orders)} orders</p>{row.missing.length > 0 && <p className="mt-2 text-sm">Missing: {row.missing.join(', ')}</p>}</div>)}</div> : <p className="mt-2 text-sm text-surface-200">Record costs before evaluating profitability.</p>}</div>
        <div className="mt-6"><h2 className="text-lg font-semibold">Observed test results · {label(current.outcomes.status)}</h2><p className="mt-3 text-sm">{display(current.outcomes.orders)} orders · {display(current.outcomes.visits)} visits · {display(current.outcomes.contribution)} contribution · {display(current.outcomes.net_profit)} profit after setup and fixed expenses ({current.outcomes.currencies.join(', ') || 'currency unknown'})</p><p className="mt-2 text-sm text-surface-200">Missing traffic stays unknown. Contribution excludes setup and fixed expenses; a small test is preliminary evidence.</p></div>
        <ValidationForms key={current.id} project={current} refresh={refresh} />
        <ValidationEvidence project={current} refresh={refresh} />
        <p className="mt-8 break-all text-xs text-surface-200">Evidence model {current.model_version} · Record fingerprint {current.input_fingerprint}</p>
      </>}
    </>}
  </main>
}

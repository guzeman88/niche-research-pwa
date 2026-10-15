import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { display, download, label, validationRequest } from '../lib/productValidation'
import { readSupportedGoal } from '../lib/supportedKeywords'
import ResearchListingForm from './ResearchListingForm'
import KeywordRightsFlag from './KeywordRightsFlag'

export default function SupportedKeywordPipeline({onCreated}: {onCreated: (id: string) => Promise<void>}) {
  const query = useQuery({queryKey: ['supported-keyword-goal'], queryFn: readSupportedGoal, retry: false, refetchInterval: 60000})
  const [selected, setSelected] = useState(''), [filter, setFilter] = useState(''), [message, setMessage] = useState('')
  const data = query.data
  const candidate = data?.candidates.find(row => row.keyword === selected)
  return <section className="my-6 border-y border-surface-600 py-5" aria-labelledby="supported-goal-heading">
    <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 id="supported-goal-heading" className="text-lg font-semibold">Supported keywords → product drafts</h2><button className="btn-secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>Refresh progress</button></div>
    {query.isLoading && <p role="status" className="mt-3">Loading supported keyword progress…</p>}
    {query.error && <p role="alert" className="mt-3 text-sm">{query.error.message}</p>}
    {data && <>
      <p className="mt-3 text-sm"><strong>{display(data.qualified_this_month)} / {display(data.target)}</strong> newly supported keyword groups · {data.month || 'tracking not started'} {data.timezone || ''}</p>
      <progress className="mt-3 h-3 w-full max-w-3xl accent-primary-400" value={Math.min(data.qualified_this_month, data.target)} max={data.target} aria-label="Monthly supported keyword progress" />
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">The 3,000/month target counts a demand group once at first qualification. Existing evidence is baseline; refreshes and shared Google variants add no credit. Supporting Google demand does not establish Etsy sales.</p>
      <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-4 text-sm">
        {[['Available supported groups', data.available_supported_groups], ['Existing baseline', data.baseline_groups], ['Etsy demand backed', data.etsy_demand_backed_groups], ['Observed daily pace · last 7 days', data.observed_daily_pace], ['Required per remaining day', data.required_daily_pace], ['Projected month · observed pace', data.projected_month_total]].map(([title, value]) => <div key={title}><dt className="text-surface-200">{title}</dt><dd className="mt-1 font-semibold">{display(value as number | undefined)}</dd></div>)}
      </dl>
      <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Qualification rules and remaining evidence</summary>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">At least 500 US Google searches/month, 1–3,000 Etsy listings, 50 current listing samples (all available when fewer), and 70% automated title relevance. Direct Etsy reports can substitute qualifying demand from a matched reporting window. These are screening rules; review relevance, costs and product quality before launch.</p>
        <ul className="mt-3 space-y-2 text-sm">{data.blockers?.map(row => <li key={row.reason}>{row.reason} · {display(row.keywords)} keywords</li>)}</ul>
      </details>
      {data.candidates.length === 0 ? <p className="mt-5 max-w-3xl text-sm leading-relaxed">{data.status === 'awaiting_collector' ? 'The app collector will initialize the goal on its next completed cycle.' : 'No current keywords pass all support rules. Collection will continue; missing evidence remains unknown.'}</p> : <>
        <label className="mt-5 block max-w-xl text-sm">Find a supported keyword<input type="search" className="input mt-2 w-full" value={filter} onChange={event => setFilter(event.target.value)} /></label>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Supported research candidates for product preparation</caption><thead><tr>{['Keyword', 'Google monthly / Etsy listings', 'Sample relevance', 'Prepare'].map(title => <th className="border-b border-surface-600 px-3 py-3 font-medium" key={title}>{title}</th>)}</tr></thead><tbody>
          {data.candidates.filter(row => row.keyword.includes(filter.toLowerCase())).slice(0, 50).map(row => <tr key={row.keyword} className="align-top"><th scope="row" className="border-b border-surface-700 px-3 py-3 font-medium">{row.keyword}<span className="mt-1 block font-normal text-surface-200">{label(row.status)}</span><KeywordRightsFlag keyword={row.keyword} /></th><td className="border-b border-surface-700 px-3 py-3">{display(row.google_monthly_searches)} ({row.google_geography || 'scope unknown'}) / {display(row.etsy_listing_count)}</td><td className="border-b border-surface-700 px-3 py-3">{Math.round(row.automated_relevance * 100)}% of {row.sample_count}<span className="mt-1 block text-surface-200">Automated screen; review required</span></td><td className="border-b border-surface-700 px-3 py-3"><button className="btn-secondary" onClick={() => setSelected(row.keyword)} aria-pressed={selected === row.keyword}>Prepare product</button></td></tr>)}
        </tbody></table></div>
        <p className="mt-2 text-xs text-surface-200">Showing up to 50 matches from the top 200 supported groups.</p>
      </>}
      {candidate && <ResearchListingForm key={candidate.keyword} keyword={candidate} onSaved={async id => {await onCreated(id); await query.refetch(); setSelected(''); setMessage('Draft saved. Use the product concept below to review relevance, record costs and track outcomes.')}} />}
      {Boolean(data.drafts?.length) && <details className="mt-6"><summary className="cursor-pointer text-sm font-semibold">Saved listing drafts · {data.drafts.length}</summary><ul className="mt-4 space-y-5">
        {data.drafts.map(draft => <li key={draft.id} className="border-b border-surface-700 pb-4"><h3 className="text-base font-semibold">{draft.title}</h3><p className="mt-2 whitespace-pre-line text-sm leading-relaxed">{draft.description}</p><p className="mt-2 text-sm text-surface-200">Tags: {draft.tags.join(', ') || 'Complete relevant tags'}</p><ul className="mt-3 space-y-1 text-sm">{draft.audit.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul><button className="btn-secondary mt-3" onClick={async () => {try {const result = await validationRequest(`/listing-drafts/${encodeURIComponent(draft.id)}/export`); download('research-listing-draft.json', JSON.stringify(result, null, 2)); setMessage('Draft exported with a fresh audit. Review is required before marketplace publication.')} catch (cause) {setMessage(cause instanceof Error ? cause.message : 'Export failed.')}}}>Export draft for review</button></li>)}
      </ul></details>}
    </>}
    {message && <p role="status" className="mt-4 text-sm">{message}</p>}
  </section>
}

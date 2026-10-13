import { label } from '../lib/productValidation'
import type { ValidationOverview, ValidationProject } from '../lib/productValidation'

function timestamp(value?: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not recorded'
}

export default function KeywordFeedStatus({feed, project}: {feed?: ValidationOverview['feed_status']; project?: ValidationProject}) {
  return <section className="my-6 border-y border-surface-600 py-5" aria-labelledby="keyword-feed-heading">
    <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 id="keyword-feed-heading" className="text-lg font-semibold">Collection feed</h2><span className="text-sm">{label(feed?.status || 'not installed')}</span></div>
    <p className="mt-2 text-sm text-surface-200">Last check: {timestamp(feed?.last_attempt)} · Last successful check: {timestamp(feed?.last_success)}</p>
    <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">Competition refreshes weekly; Google demand monthly. Etsy buyer demand uses the free seller reports and may need sign-in. New listing samples need a relevance review.</p>
    {Boolean(feed?.errors?.length) && <p role="status" className="mt-3 text-sm">Collection needs attention. Saved evidence is preserved; check the worker report before retrying.</p>}
    {feed?.bulk?.mirror && <p className="mt-2 text-sm text-surface-200">Research mirror: {feed.bulk.mirror.pending} runs awaiting sync.</p>}
    {feed?.coverage?.active_keywords != null && <div className="mt-4">
      <p className="text-sm"><strong>{feed.coverage.active_keywords.toLocaleString()} active keywords</strong><span className="text-surface-200"> · {feed.coverage.exploration_keywords?.toLocaleString()} exploration · {feed.coverage.library_keywords?.toLocaleString()} preserved in the library</span></p>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">Last 24 hours of native attempts recorded since the upgrade. Useful results may be listing samples or supporting signals; they do not establish Etsy demand or profit. Repeated attempts are included in checks.</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Recorded collection outcomes over the rolling 24 hours</caption><thead><tr>{['Source', 'Checks / unique keywords', 'Useful / empty / failed', 'Repeated checks'].map(name => <th key={name} className="border-b border-surface-600 px-3 py-3 font-medium">{name}</th>)}</tr></thead><tbody>
        {(feed.coverage.providers || []).map(row => <tr key={row.provider}><th scope="row" className="border-b border-surface-700 px-3 py-3 font-medium">{label(row.provider)}</th><td className="border-b border-surface-700 px-3 py-3">{row.attempts} / {row.unique_keywords}</td><td className="border-b border-surface-700 px-3 py-3">{row.useful_attempts} / {row.empty_attempts} / {row.failed_attempts}</td><td className="border-b border-surface-700 px-3 py-3">{row.repeated_attempts}</td></tr>)}
      </tbody></table></div>
      <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Research priorities and evidence gaps</summary>
        <p className="mt-3 max-w-3xl text-sm text-surface-200">Priorities use buyer phrases, the watchlist and observed signals. They are research heuristics. Direct Etsy demand, relevance review, costs and sales must still be assessed.</p>
        <ul className="mt-3 space-y-3">{(feed.coverage.candidate_preview || []).map(row => <li key={row.keyword} className="text-sm"><strong>{row.keyword}</strong><span className="mt-1 block text-surface-200">Competition sample: {row.competition_sample_current ? 'current; review relevance' : 'missing or old'} · Google demand: {row.google_demand_measured ? 'measured' : 'unknown or old'}</span></li>)}</ul>
      </details>
    </div>}
    {feed?.bridge?.status && <p className="mt-3 max-w-3xl text-sm text-surface-200">Original collector import: {label(feed.bridge.status)} · {feed.bridge.imported_rows || 0} source rows archived this cycle · {feed.bridge.pending_rows || 0} awaiting import. Imported history is separate from native checks.</p>}
    {Boolean(feed?.marketplace_plan?.suggestions?.length) && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Next Etsy buyer-demand reports</summary><p className="mt-3 max-w-3xl text-sm text-surface-200">Suggested allocation: up to five refreshes and ten discoveries. Check the remaining free allowance in Etsy before searching.</p><ul className="mt-3 space-y-2">{feed?.marketplace_plan?.suggestions?.map(row => <li key={row.keyword} className="text-sm">{row.keyword}<span className="ml-2 text-surface-200">{label(row.lane)}</span></li>)}</ul></details>}
    {project && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Source freshness and observation history</summary>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Collection dates and next due dates by keyword and source</caption><thead><tr>{['Keyword / source', 'Last observation', 'Next due', 'History / status'].map(name => <th key={name} className="border-b border-surface-600 px-3 py-3 font-medium">{name}</th>)}</tr></thead><tbody>
        {project.queue.flatMap(row => (row.sources || []).map(source => <tr key={`${row.keyword}:${source.source}`}><th scope="row" className="border-b border-surface-700 px-3 py-3 font-medium">{row.keyword}<span className="mt-1 block font-normal text-surface-200">{source.source}</span></th><td className="whitespace-nowrap border-b border-surface-700 px-3 py-3">{source.last_observed || 'Unknown'}</td><td className="whitespace-nowrap border-b border-surface-700 px-3 py-3">{source.next_due || 'Collect first'}</td><td className="border-b border-surface-700 px-3 py-3">{source.observations} observations · {label(source.status)}</td></tr>))}
      </tbody></table></div>
    </details>}
  </section>
}

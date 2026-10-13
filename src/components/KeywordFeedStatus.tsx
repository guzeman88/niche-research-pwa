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
    {project && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Source freshness and observation history</summary>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Collection dates and next due dates by keyword and source</caption><thead><tr>{['Keyword / source', 'Last observation', 'Next due', 'History / status'].map(name => <th key={name} className="border-b border-surface-600 px-3 py-3 font-medium">{name}</th>)}</tr></thead><tbody>
        {project.queue.flatMap(row => (row.sources || []).map(source => <tr key={`${row.keyword}:${source.source}`}><th scope="row" className="border-b border-surface-700 px-3 py-3 font-medium">{row.keyword}<span className="mt-1 block font-normal text-surface-200">{source.source}</span></th><td className="whitespace-nowrap border-b border-surface-700 px-3 py-3">{source.last_observed || 'Unknown'}</td><td className="whitespace-nowrap border-b border-surface-700 px-3 py-3">{source.next_due || 'Collect first'}</td><td className="border-b border-surface-700 px-3 py-3">{source.observations} observations · {label(source.status)}</td></tr>))}
      </tbody></table></div>
    </details>}
  </section>
}

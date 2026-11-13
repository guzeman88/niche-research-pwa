import {useQuery} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import {getDashboardSummary} from '../lib/dashboardSummary'
import type {DashboardSummary} from '../types/api'
import {DashboardSkeleton} from './Skeleton'
import useClock from '../hooks/useClock'

const number=(value: number | null | undefined)=>value==null?'Unknown':value.toLocaleString()
const name=(value:string)=>value.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/_/g,' ')
const date=(value:string|null|undefined)=>value && Number.isFinite(Date.parse(value))?new Date(value).toLocaleString(): 'Not recorded'

export default function OperationalDashboard(){
  const currentTime=useClock()
  const query=useQuery<DashboardSummary>({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,refetchInterval:60000,staleTime:30000,retry:false})
  if(!query.data && query.isPending)return <DashboardSkeleton/>
  if(!query.data)return <div className="page max-w-3xl"><h1 className="text-2xl font-semibold">Dashboard</h1><p role="alert" className="mt-4 text-surface-200">{query.error?.message || 'Dashboard data is unavailable.'}</p><button className="btn-secondary mt-4" onClick={()=>void query.refetch()}>Retry dashboard</button></div>
  const data=query.data
  const operational=data.schema_version===2
  const stale=Boolean(data.delivery.stale)||currentTime-Date.parse(data.generated_at)>150000||!Number.isFinite(Date.parse(data.generated_at))
  const stats=data.stats
  const estimate=data.intelligence?.automatic_estimator
  const qualified=data.evidence.versioned_scores
  const maximum=Math.max(1,...(data.score_distribution || []).map(row=>row.count))
  return <div className="page">
    <header className="page-header"><h1 className="text-2xl font-semibold text-surface-50">Dashboard</h1><button className="btn-secondary" disabled={query.isFetching} onClick={()=>void query.refetch()}>{query.isFetching?'Refreshing…':'Refresh dashboard'}</button></header>
    <section aria-label="Data connection" className="panel p-4" role="status">
      <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-base font-semibold">{!operational?'Historical reporting source':stale?'Backend sync delayed':'Connected to active research'}</h2><span className="text-sm text-surface-200">Published {date(data.generated_at)}</span></div>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">{!operational?'This is the older hosted research library. Current local collection has not reached this report yet.':stale?'Showing the last saved backend report. Keep the EtGen computer running to restore updates.':'This report comes from the active native collection library. It updates about once a minute while EtGen is running.'}</p>
      <p className="mt-2 text-sm text-surface-200">Latest collection: {date(data.source_watermarks.latest_collection_at)}. Refreshing this page reloads the report; it does not collect new evidence.</p>
      {data.connection && !data.connection.private_actions_available && <p className="mt-2 text-sm text-accent-amber">Research totals are available. The private action connection is offline; keep the EtGen computer running and retry before editing products.</p>}
      {query.error && <p className="mt-3 text-sm text-accent-amber" role="alert">Refresh failed. The last loaded report remains visible.</p>}
    </section>
    <section aria-label="Research library" className="panel mt-5 p-4 sm:p-6">
      <h2 className="text-lg font-semibold">Research library</h2>
      <dl className="mt-4 grid grid-cols-2 gap-6 lg:grid-cols-4">
        <Metric label="Keyword seeds" value={number(stats.total_seeds)} detail="Native library; includes untested ideas"/>
        <Metric label="Attempted keywords" value={number(stats.attempted ?? stats.scanned)} detail={`${stats.coverage_pct ?? 'Unknown'}% of this library`}/>
        <Metric label="Supply evidence" value={number(stats.evidence_backed)} detail="Listing or pricing evidence; not sales"/>
        <Metric label="Historical scans" value={number(stats.total_scans)} detail="Repeated scans count separately"/>
      </dl>
      <p className="mt-5 text-sm text-surface-200">{number(stats.failed)} failed · {number(stats.no_data)} returned no data · {number(stats.stale)} collection states are over 30 days old.</p>
      <Link to="/keywords" className="mt-4 inline-block text-sm text-primary-200 underline underline-offset-4">Browse current keywords</Link>
    </section>
    <section className="mt-6" aria-labelledby="next-actions"><h2 id="next-actions" className="text-lg font-semibold">Move research into products</h2>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        <Workflow title="Validate a product" to="/validation" action="Open product validation"><p>{number(data.supported?.available_supported_groups)} currently supported groups.</p><p className="mt-2">{number(data.supported?.qualified_this_month)} new groups this month toward {number(data.supported?.target)}. Close variants count once.</p><p className="mt-2">{number(data.validation?.projects)} saved concepts · {number(data.validation?.records)} evidence records.</p></Workflow>
        <Workflow title="Investigate selling signals" to="/selling" action="Open selling products"><p>{number(data.intelligence?.listings)} saved listing identities.</p><p className="mt-2">{number(estimate?.tracked)} tracked · {number(estimate?.estimated)} provisional review scenarios.</p><p className="mt-2">{number(data.intelligence?.observations)} eligible reference observations · {number(data.intelligence?.outcomes)} actual outcomes. Estimates are not verified sales.</p></Workflow>
        <Workflow title="Build and review products" to="/production" action="Open production"><p>{number(data.production?.starting_recipes)} starting product recipes.</p><p className="mt-2">{number(data.production?.jobs)} real jobs · {number(data.production?.review_queue)} awaiting review.</p><p className="mt-2">Customer files and listings retain their approval gates. Starting recipes are not launched products.</p></Workflow>
      </div>
    </section>
    <section className="panel mt-6 p-4 sm:p-6" aria-labelledby="collection-status"><div className="flex flex-wrap items-baseline justify-between gap-3"><h2 id="collection-status" className="text-lg font-semibold">Collection status</h2><Link to="/evidence" className="text-sm text-primary-200 underline underline-offset-4">Review sources and errors</Link></div>
      <p className="mt-3 text-sm text-surface-200">Collector: {name(data.feed?.status || 'not reported')} · Last completed {date(data.feed?.last_completed)}.</p>
      {!!data.feed?.errors?.length && <p className="mt-2 text-sm text-accent-amber">Needs attention: {data.feed.errors.map(name).join(', ')}.</p>}
      <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="pb-3 text-left text-surface-200">Rolling 24-hour collection · measured {date(data.coverage?.as_of)}</caption><thead className="text-surface-200"><tr>{['Source','Attempts','Useful','Failed'].map(label=><th className="border-b border-surface-600 py-3 pr-5 font-medium" key={label}>{label}</th>)}</tr></thead><tbody>{data.coverage?.providers?.map(row=><tr key={row.provider}><th scope="row" className="border-b border-surface-700 py-3 pr-5 font-medium">{name(row.provider)}</th><td className="border-b border-surface-700 py-3 pr-5 tabular-nums">{number(row.attempts)}</td><td className="border-b border-surface-700 py-3 pr-5 tabular-nums">{number(row.useful_attempts)}</td><td className="border-b border-surface-700 py-3 tabular-nums">{number(row.failed_attempts)}</td></tr>)}</tbody></table></div>
      {!data.coverage?.providers?.length && <p className="mt-3 text-sm text-surface-200">Recent provider activity is unavailable in this report.</p>}
      <p className="mt-4 text-sm text-surface-200">Within the active focus set: {number(data.coverage?.active_current_competition)} current competition samples · {number(data.coverage?.active_paired_keywords)} keywords with paired supporting Google demand. Google demand does not establish Etsy sales.</p>
      <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Source observation dates</summary><ul className="mt-3 space-y-2 text-sm text-surface-200">{data.sources?.map(row=><li key={row.source}>{name(row.source)}: {date(row.latest)} · {number(row.keywords)} keywords · {number(row.rows)} observations</li>)}</ul></details>
    </section>
    <div className="mt-6 grid gap-5 lg:grid-cols-2">
      <section className="panel p-4 sm:p-6"><h2 className="text-lg font-semibold">Evidence-qualified rankings</h2><p className="mt-3 text-sm text-surface-200">{number(qualified)} latest verified keyword scores · {number(data.evidence.versioned_gaps)} verified gap reports.</p>
        {qualified>0?<div className="mt-4 space-y-3">{data.score_distribution?.map(row=><div key={row.label} className="flex items-center gap-3 text-sm"><span className="w-12 shrink-0">{row.label}</span><div className="progress-track flex-1"><div className="h-full bg-primary-300" style={{width:`${100*row.count/maximum}%`}}/></div><span className="w-12 text-right tabular-nums">{number(row.count)}</span></div>)}</div>:<p className="mt-4 max-w-prose text-sm leading-relaxed text-surface-200">Opportunity and gap scores remain unknown until a versioned model has sufficient evidence. Collection volume alone does not establish a profitable opportunity.</p>}
        {!!data.research_leads?.length && <ol className="mt-4 space-y-2 text-sm">{data.research_leads.map(row=><li key={row.keyword} className="flex justify-between gap-3"><span>{row.keyword}</span><span className="tabular-nums">{row.score.toFixed(1)}</span></li>)}</ol>}
        <p className="mt-4 text-sm text-surface-200">Breakout detection: {data.breakouts?.status==='available'?number(stats.breakout_count):'Unavailable'}. {data.breakouts?.reason}</p>
      </section>
      <section className="panel p-4 sm:p-6"><h2 className="text-lg font-semibold">Keywords by research category</h2><p className="mt-3 text-sm text-surface-200">Native-library categories, with known aliases combined. Counts describe ideas, not buyer demand.</p><dl className="mt-4 space-y-3">{stats.domains.slice(0,8).map(row=><div key={row.domain} className="flex justify-between gap-4 text-sm"><dt className="min-w-0 break-words text-surface-200">{name(row.domain)}</dt><dd className="shrink-0 tabular-nums">{number(row.cnt)}</dd></div>)}</dl></section>
    </div>
  </div>
}

function Metric({label,value,detail}:{label:string;value:string;detail:string}){return <div><dt className="text-sm text-surface-200">{label}</dt><dd className="mt-2 text-2xl font-semibold tabular-nums">{value}</dd><dd className="mt-2 text-sm leading-relaxed text-surface-200">{detail}</dd></div>}
function Workflow({title,to,action,children}:{title:string;to:string;action:string;children:React.ReactNode}){return <article className="panel flex flex-col p-4 sm:p-5"><h3 className="text-base font-semibold">{title}</h3><div className="mt-3 flex-1 text-sm leading-relaxed text-surface-200">{children}</div><Link to={to} className="btn-secondary mt-5 w-fit">{action}</Link></article>}

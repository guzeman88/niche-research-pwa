import {date,number,text,money} from './format'

import {usePipelineDrawer} from './drawerContext'

import {useEffect, useRef, useState} from 'react'

import type {ReactNode} from 'react'

import {Link, useLocation, useNavigate} from 'react-router-dom'

import {useQuery, useQueryClient} from '@tanstack/react-query'

import {useAuth} from '../lib/auth'

import {useAppMode} from '../lib/appMode'

import {accountConnectionAvailable, operatorRequest, readConnection} from '../lib/operatorConnection'

import {getDashboardSummary} from '../lib/dashboardSummary'

import {getStores, getTestCandidatePortfolio} from '../lib/api'
import type {TestStoreCandidate} from '../lib/api'

import {getUserStoreIdeas, listUserKeywords} from '../lib/userData'

import {validationRequest, download} from '../lib/productValidation'

import type {ValidationOverview, ValidationProject} from '../lib/productValidation'

import {artifactBlob, productionRequest} from '../lib/production'

import type {ProductionOverview, ProductionJob, ProductionSpec, LaunchRecipe} from '../lib/production'

import {intelligenceRequest} from '../lib/salesIntelligence'

import type {AutomaticEstimate} from '../lib/salesIntelligence'

import {sellingRequest} from '../lib/sellingProducts'

import type {Overview,Detail} from '../lib/sellingProducts'

import type {KeywordItem} from '../types/api'

import {readSupportedGoal} from '../lib/supportedKeywords'

import ProductionJobReview from '../components/ProductionJobReview'

import ProductionSpecForm from '../components/ProductionSpecForm'

import KeywordRightsFlag from '../components/KeywordRightsFlag'
import {keywordRightsMatches} from '../lib/keywordRights'
import {CreateValidation} from '../components/ValidationForms'
import ResearchListingForm from '../components/ResearchListingForm'

import {listLaunchWorkflows} from '../lib/launchWorkflow'

import {Facts, Heading, Pill, PipelineIcon, QueryState, Table} from './PipelineUI'



export type PipelinePage='keywords'|'selling'|'validation'|'production'|'generator'|'launch'|'stores'|'evidence'|'workspace'|'account'

const titles:Record<PipelinePage,string>={keywords:'Keywords',selling:'Selling products',validation:'Product validation',production:'Production',generator:'Store Generator',launch:'Launch Lab',stores:'My Stores',evidence:'Evidence operations',workspace:'Workspace & backups',account:'Account & profile'}

function usePrivateResearch(allowUserMode=false){const [,setRevision]=useState(0);useEffect(()=>{const changed=()=>setRevision(v=>v+1);window.addEventListener('etgen:connection-updated',changed);window.addEventListener('storage',changed);return()=>{window.removeEventListener('etgen:connection-updated',changed);window.removeEventListener('storage',changed)}},[]);const auth=useAuth(),{isUserMode}=useAppMode();return Boolean(readConnection().url)&&(accountConnectionAvailable()?auth.profile?.role==='admin'&&(!isUserMode||allowUserMode):true)}

function latestProducts(jobs:ProductionJob[]){const seen=new Set<string>();return jobs.filter(job=>{if(seen.has(job.product_id))return false;seen.add(job.product_id);return true})}

function useProjects(enabled=true){return useQuery({queryKey:['product-validation',0],queryFn:()=>validationRequest<ValidationOverview>(),enabled,refetchInterval:60000,retry:false})}

function useProduction(enabled=true){return useQuery({queryKey:['production'],queryFn:()=>productionRequest<ProductionOverview>(),enabled,refetchInterval:5000,retry:false})}

export function ArtifactPreview({job,kind='inside'}:{job:ProductionJob;kind?:'cover'|'inside'}){

 const names=job.result?.manifest?.render.previews||['preview.png'],name=kind==='inside'?(names[1]||names[0]):names[0]

 const [src,setSrc]=useState('')

 const query=useQuery({queryKey:['pipeline-artifact',job.id,job.revision,name],queryFn:()=>artifactBlob(job.id,name),enabled:Boolean(job.result?.manifest),staleTime:Infinity,retry:false})

 useEffect(()=>{if(!query.data)return;const url=URL.createObjectURL(query.data);setSrc(url);return()=>URL.revokeObjectURL(url)},[query.data])

 return src?<img src={src} alt={`Actual ${kind} page of ${job.spec.name}`}/>:<PipelineIcon name="file"/>

}

function useReview(){const open=usePipelineDrawer();return (job:ProductionJob)=>open(job.spec.name,<ReviewPanel initial={job}/>)}

function ReviewPanel({initial}:{initial:ProductionJob}){

 const query=useProduction(),open=usePipelineDrawer(),client=useQueryClient(),job=query.data?.jobs.find(j=>j.id===initial.id)||initial

 const refresh=()=>{void client.invalidateQueries({queryKey:['production']});void client.invalidateQueries({queryKey:['product-validation']})}

 const revise=(spec:ProductionSpec)=>open('Revise specification',<ProductionSpecForm initial={spec} productId={job.product_id} refresh={refresh} close={()=>open(job.spec.name,<ReviewPanel initial={job}/>)}/>)

 return <ProductionJobReview job={job} refresh={refresh} revise={revise}/>

}



export default function PipelineWorkspace({id,children}:{id:PipelinePage;children:ReactNode}){
 const open=usePipelineDrawer(),client=useQueryClient(),location=useLocation()
 const tools=useRef<HTMLDetailsElement>(null),[mounted,setMounted]=useState(Boolean(location.search))
 const showTools=()=>{setMounted(true);requestAnimationFrame(()=>{if(tools.current){tools.current.open=true;tools.current.scrollIntoView({block:'start'});tools.current.querySelector<HTMLElement>('summary')?.focus()}})}
 if(['account','workspace'].includes(id))return <div className={`pipeline-functional pipeline-functional-${id}`}>{children}</div>
 const primary=()=>{if(id==='validation')open('Add a product concept',<CreateValidation refresh={async()=>{await client.invalidateQueries({queryKey:['product-validation']})}}/>);else if(id==='production')open('Starting recipes',<RecipePicker/>);else showTools()}
 const action=id==='production'?'Starting recipes':id==='validation'?'Add product concept':id==='launch'?'New workflow':id==='stores'?'Store workspace':id==='evidence'?'Operations tools':'Workspace tools'
 return <>
  {id!=='keywords'&&<Heading title={titles[id]} actions={<button className="button" onClick={primary}>{action}</button>}/>}
  {id==='production'?<ProductionPage tools={showTools}/>:id==='validation'?<ValidationPage tools={showTools}/>:id==='keywords'?<KeywordsPage/>:id==='selling'?<SellingPage tools={showTools}/>:id==='stores'?<StoresPage/>:id==='launch'?<LaunchPage/>:id==='evidence'?<EvidencePage/>:<GeneratorPage tools={showTools}/>}
  <details className="pipeline-tools" ref={tools} open={Boolean(location.search)} onToggle={ev=>{if(ev.currentTarget.open)setMounted(true)}}><summary>Workspace tools</summary>{mounted&&<div className="pipeline-functional">{children}</div>}</details>
 </>
}

function RecipePicker(){
 const query=useQuery({queryKey:['production-launch-recipes'],queryFn:()=>productionRequest<{recipes:LaunchRecipe[]}>('/launch-recipes'),retry:false}),open=usePipelineDrawer(),client=useQueryClient()
 return <><QueryState pending={query.isPending} error={query.error} retry={query.refetch}/><div className="field-form">{query.data?.recipes.map(r=><button className="button" key={r.id} onClick={()=>open(r.name,<ProductionSpecForm initial={r.spec} refresh={()=>void client.invalidateQueries({queryKey:['production']})} close={()=>open('Starting recipes',<RecipePicker/>)}/>)}>{r.name}</button>)}</div></>
}



export function PipelineHome({userWorkspace}:{userWorkspace:ReactNode}){

 const enabled=usePrivateResearch(),{isUserMode}=useAppMode(),open=usePipelineDrawer(),review=useReview()

 const projects=useProjects(enabled),production=useProduction(enabled),summary=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled:!isUserMode,staleTime:30000,refetchInterval:60000,retry:false})

 const stores=useQuery({queryKey:['stores'],queryFn:getStores,enabled:isUserMode})

 const products=latestProducts(production.data?.jobs||[])

 return <><Heading title="Dashboard" actions={<Link className="button primary" to={isUserMode?'/stores':'/production'}>{isUserMode?'Open stores':'Review products'}</Link>}/><div className="pipeline dashboard-board"><section className="stage"><div className="section-heading"><h2>Research <span className="count">{enabled?number(projects.data?.projects.length):number(stores.data?.length)}</span></h2></div>{enabled?<><QueryState pending={projects.isPending} error={projects.error} retry={projects.refetch}/>{projects.data?.projects.map(p=><Link className="pipeline-task" key={p.id} to={'/validation?project='+encodeURIComponent(p.id)}><PipelineIcon name="file"/><h3>{p.name}</h3><PipelineIcon name="next"/></Link>)}<div className="stage-action"><Link className="button" to="/validation">Open validation</Link></div></>:<><QueryState pending={stores.isPending} error={stores.error} retry={stores.refetch}/>{stores.data?.map(store=><Link className="pipeline-task" key={store.slug} to={'/stores?store='+encodeURIComponent(store.slug)}><PipelineIcon name="file"/><h3>{store.name}</h3><PipelineIcon name="next"/></Link>)}<div className="stage-action"><Link className="button" to="/keywords">Keywords</Link></div></>}</section><section className="stage"><div className="section-heading"><h2>Review <span className="count">{enabled?number(production.data?products.length:null):'Account'}</span></h2></div>{enabled?<><QueryState pending={production.isPending} error={production.error} retry={production.refetch}/>{products.map(job=><article className="pipeline-product" key={job.id}><div className="pipeline-thumb"><ArtifactPreview job={job}/></div><h3>{job.spec.name}</h3><button className="button primary" onClick={()=>review(job)}>Review</button></article>)}</>:<Link className="button" to="/stores">Products and listings</Link>}</section><section className="stage"><div className="section-heading"><h2>Launch</h2></div><div className="launch-state"><PipelineIcon name="lock"/><h3>{enabled&&production.data&&!products.length?'No current products':products.length&&products.every(j=>['approved','exported'].includes(j.status))?'Approved packages':'Owner approval required'}</h3><Link className="button" to={isUserMode?'/stores':'/launch'}>{isUserMode?'My Stores':'Launch Lab'}</Link></div></section></div>{!isUserMode?<section className="section-block"><div className="section-heading"><h2>Collection</h2><Pill warning>{text(summary.data?.feed?.status)}</Pill></div><QueryState pending={summary.isPending} error={summary.error} retry={summary.refetch}/><Table heads={['Source','Keywords','Observations','Last observed']} rows={(summary.data?.sources||[]).slice(0,5).map(s=>[<button className="text-link" onClick={()=>open(text(s.source),<Facts rows={[["Source",text(s.source)],["Keywords",number(s.keywords)],["Observations",number(s.rows)],["Last observed",date(s.latest)],["Sales","Unverified"]]}/>)}>{text(s.source)}</button>,number(s.keywords),number(s.rows),date(s.latest)])}/></section>:<details className="pipeline-tools"><summary>Account research</summary>{userWorkspace}</details>}</>

}



function ProductionPage({tools}:{tools:()=>void}){

 const enabled=usePrivateResearch(true),query=useProduction(enabled),review=useReview(),[all,setAll]=useState(false)

 const jobs=query.data?.jobs||[],rows=all?jobs:latestProducts(jobs)

 return <><div className="filters"><label className="checkbox-label"><input type="checkbox" checked={all} onChange={e=>setAll(e.target.checked)}/>All revisions <span className="count">{number(query.data?.jobs.length)}</span></label></div><QueryState pending={enabled&&query.isPending} error={query.error} retry={query.refetch}/>{query.data&&<Table heads={['Product','Recipe','Revision','Checks','Review','Draft price','']} rows={rows.map(j=>[<div className="name-with-thumb"><div className="small-thumb"><ArtifactPreview job={j}/></div><button className="text-link" onClick={()=>review(j)}>{j.spec.name}</button></div>,text(j.spec.family),j.revision.slice(0,8),<Pill>{text(j.result?.quality?.status)}</Pill>,<Pill warning={j.status!=='approved'}>{text(j.status)}</Pill>,j.spec.price==null?'Unknown':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(j.spec.price),<button className="button primary" onClick={()=>review(j)}>Review</button>])}/>} {!enabled&&<button className="button" onClick={tools}>Connection settings</button>}</>

}

function ValidationPage({tools}:{tools:()=>void}){

 const enabled=usePrivateResearch(true),query=useProjects(enabled),[tab,setTab]=useState('projects'),open=usePipelineDrawer(),client=useQueryClient()

 const supported=useQuery({queryKey:['supported-keyword-goal'],queryFn:readSupportedGoal,enabled:enabled&&tab==='supported',retry:false})

 const project=(p:ValidationProject)=>open(p.name,<><Facts rows={[["Readiness",text(p.status)],["Keywords",number(p.keywords.length)],["Evidence records",number(p.records?.length)],["Orders",number(p.outcomes.orders)],["Revenue",number(p.outcomes.revenue)],["Net profit",number(p.outcomes.net_profit)]]}/><div className="drawer-actions"><Link className="button primary" to={'/validation?project='+encodeURIComponent(p.id)}>Edit evidence</Link></div></>)

 return <><div className="tabs"><button aria-pressed={tab==='projects'} onClick={()=>setTab('projects')}>Projects <span className="count">{number(query.data?.projects.length)}</span></button><button aria-pressed={tab==='supported'} onClick={()=>setTab('supported')}>Supported keywords</button></div><QueryState pending={enabled&&(tab==='projects'?query.isPending:supported.isPending)} error={tab==='projects'?query.error:supported.error} retry={tab==='projects'?query.refetch:supported.refetch}/>{tab==='projects'&&query.data?<Table heads={['Project','Type','Keywords','Records','Readiness','']} rows={query.data.projects.map(p=>[<button className="text-link" onClick={()=>project(p)}>{p.name}</button>,p.product_type,number(p.keywords.length),number(p.records?.length),<Pill warning>{text(p.status)}</Pill>,<button className="button" onClick={()=>project(p)}>View</button>])}/>:tab==='supported'&&supported.data?<Table heads={['Keyword','Google searches / month','Etsy listings','Samples','Human relevance review','']} rows={supported.data.candidates.map(p=>[<span>{p.keyword}<KeywordRightsFlag keyword={p.keyword}/></span>,number(p.google_monthly_searches),number(p.etsy_listing_count),number(p.sample_count),<Pill warning={p.human_relevance_review_required}>{p.human_relevance_review_required?'Required':'Recorded'}</Pill>,<button className="button" onClick={()=>open('Prepare product',<ResearchListingForm keyword={p} onSaved={async id=>{await client.invalidateQueries({queryKey:['product-validation']});await client.invalidateQueries({queryKey:['supported-keyword-goal']});open('Product draft saved',<Link className="button primary" to={'/validation?project='+encodeURIComponent(id)}>Review product</Link>)}}/>)}>Prepare product</button>])}/>:null}{!enabled&&<button className="button" onClick={tools}>Connection settings</button>}</>

}

function KeywordsPage(){
 const enabled=usePrivateResearch(),{isUserMode,userDataVersion}=useAppMode(),open=usePipelineDrawer()
 const [q,setQ]=useState(''),[domain,setDomain]=useState(''),[evidence,setEvidence]=useState(''),[sort,setSort]=useState('keyword'),[page,setPage]=useState(0)
 const categories=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled,staleTime:60000,retry:false})
 const local=useQuery({queryKey:['pipeline-user-keywords',userDataVersion],queryFn:()=>listUserKeywords(15000),enabled:isUserMode})
 const numeric=sort==='listing_count'||sort==='avg_price_usd'
 const remote=useQuery({queryKey:['pipeline-keywords',q,domain,evidence,sort,page],queryFn:()=>operatorRequest<{items:KeywordItem[];total:number}>(`/api/dashboard/keywords?${new URLSearchParams({q,domain,evidence,sort,direction:numeric?'desc':'asc',offset:String(page*20),limit:'20'})}`),enabled,retry:false})
 const own=(local.data||[]).filter(row=>(!q||row.keyword.toLowerCase().includes(q.toLowerCase()))&&(!domain||row.domain===domain)&&(!evidence||(row.evidence_status||'unverified')===evidence)).sort((a,b)=>{
  if(numeric){const key=sort==='listing_count'?'listing_count':'avg_price_usd',av=a[key],bv=b[key];if(av==null&&bv==null)return a.keyword.localeCompare(b.keyword);if(av==null)return 1;if(bv==null)return -1;return bv-av||a.keyword.localeCompare(b.keyword)}
  return a.keyword.localeCompare(b.keyword)
 })
 const rows=enabled?(remote.data?.items||[]):own.slice(page*20,(page+1)*20),total=enabled?remote.data?.total:own.length
 const domains=[...new Set((isUserMode?local.data||[]:categories.data?.stats.domains||rows).map(row=>row.domain))].sort()
 const show=(k:KeywordItem)=>open(k.keyword,<><Facts rows={[["Category",text(k.domain)],["Evidence",text(k.evidence_status)],["Etsy listings",number(k.listing_count)],["Sampled listings",number(k.sampled_listing_count)],["Average price",money(k.avg_price_usd)],["Last observed",date(k.last_scanned_at)],["Verified sales","Unknown"],["Rights check","Known-term matches only"],["Legal clearance","Not established"]]}/><KeywordRightsFlag keyword={k.keyword}/></>)
 const known=(enabled?remote.data:local.data)!==undefined
 return <>
  <Heading title="Keywords" actions={<button className="button" disabled={!known} onClick={()=>download('etgen-keyword-rows.json',JSON.stringify(rows,null,2))}>Export visible rows</button>}/>
  <div className="filters">
   <label className="search-field"><PipelineIcon name="search"/><input aria-label="Search keywords" placeholder="Search keywords" value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/></label>
   <label><span id="keyword-domain-label">Category</span><select aria-labelledby="keyword-domain-label" value={domain} onChange={e=>{setDomain(e.target.value);setPage(0)}}><option value="">All categories</option>{domains.map(d=><option key={d}>{d}</option>)}</select></label>
   <label><span id="keyword-evidence-label">Evidence</span><select aria-labelledby="keyword-evidence-label" value={evidence} onChange={e=>{setEvidence(e.target.value);setPage(0)}}><option value="">All evidence</option>{['verified','partial','failed','unverified'].map(value=><option value={value} key={value}>{text(value)}</option>)}</select></label>
   <label><span id="keyword-sort-label">Sort</span><select aria-labelledby="keyword-sort-label" value={sort} onChange={e=>{setSort(e.target.value);setPage(0)}}><option value="keyword">Keyword</option><option value="listing_count">Listing count</option><option value="avg_price_usd">Average price</option></select></label>
  </div>
  <QueryState pending={enabled?remote.isPending:local.isPending} error={enabled?remote.error:local.error} retry={enabled?remote.refetch:local.refetch}/>
  {known&&<Table heads={['Keyword','Category','Evidence','Etsy listings','Sampled','Average price','Rights']} rows={rows.map(k=>[<button className="text-link" onClick={()=>show(k)}>{k.keyword}</button>,text(k.domain),<Pill>{text(k.evidence_status)}</Pill>,number(k.listing_count),number(k.sampled_listing_count),money(k.avg_price_usd),keywordRightsMatches(k.keyword).length?<KeywordRightsFlag keyword={k.keyword}/>:<Pill>No match</Pill>])}/>}
  <div className="pager"><span>{number(total)} keywords · Page {page+1}</span><div><button className="button" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="button" disabled={total==null||(page+1)*20>=total} onClick={()=>setPage(p=>p+1)}>Next</button></div></div>
 </>
}

interface Catalog {items:Array<{listing_id:string;title:string;shop:string;keyword:string;observed_at:string;signal:string;fingerprint:string;price:{value:number|null;currency:string}|null}>;total:number}

function SellingPage({tools}:{tools:()=>void}){
 const navigate=useNavigate(),[busy,setBusy]=useState(''),[actionError,setActionError]=useState('')
 const investigate=async(item:Catalog['items'][number])=>{setBusy(item.listing_id);setActionError('');try{const result=await sellingRequest<Detail>(`/discovery/${encodeURIComponent(item.listing_id)}/investigate`,{expected_fingerprint:item.fingerprint});navigate('/selling?opportunity='+encodeURIComponent(result.id))}catch(error){setActionError(error instanceof Error?error.message:'Could not investigate this listing.')}finally{setBusy('')}}

 const enabled=usePrivateResearch(true),[tab,setTab]=useState('tracked'),[q,setQ]=useState(''),[page,setPage]=useState(0),open=usePipelineDrawer()

 const estimates=useQuery({queryKey:['automatic-sales-estimates'],queryFn:()=>intelligenceRequest<{items:AutomaticEstimate[];summary:{tracked?:number;estimated?:number}}>('/estimates'),enabled:enabled&&tab==='tracked',retry:false,refetchInterval:30000})

 const catalog=useQuery({queryKey:['selling-discovery',q,'all',page],queryFn:()=>sellingRequest<Catalog>(`/discovery?${new URLSearchParams({q,signal:'all',page:String(page)})}`),enabled:enabled&&tab==='catalog',retry:false})

 const saved=useQuery({queryKey:['selling-products',0],queryFn:()=>sellingRequest<Overview>(),enabled:enabled&&tab==='saved',retry:false})

 const tracked=(estimates.data?.items||[]).filter(x=>JSON.stringify([x.listing_id,x.collection?.title,x.listing?.title]).toLowerCase().includes(q.toLowerCase()))

 const show=(x:AutomaticEstimate)=>open(x.collection?.title||x.listing?.title||x.listing_id,<><Facts rows={[["Listing",x.listing_id],["Status",text(x.status)],["30-day scenario",number(x.review_scenarios?.['30']?.value)],["Low / high",`${number(x.review_scenarios?.['30']?.low)} / ${number(x.review_scenarios?.['30']?.high)}`],["Range type","Assumption sensitivity"],["Confidence interval","Not available"],["Verified sales","Unknown"],["Rights check","Known-term matches only"],["Legal clearance","Not established"],["Captured",date(x.captured_at)]]}/><button className="button" onClick={tools}>Sales intelligence</button></>)

 const query=tab==='tracked'?estimates:tab==='catalog'?catalog:saved

 return <><div className="tabs">{[['tracked','Tracked'],['catalog','Catalog'],['saved','Saved opportunities']].map(([key,label])=><button key={key} aria-pressed={tab===key} onClick={()=>{setTab(key);setQ('');setPage(0)}}>{label}</button>)}</div><div className="filters"><label className="search-field"><PipelineIcon name="search"/><input aria-label="Search listings" placeholder="Search listings" value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/></label><Pill warning>Sales unverified</Pill>{tab==='tracked'&&<Pill>30-day scenarios</Pill>}</div><QueryState pending={enabled&&query.isPending} error={query.error} retry={query.refetch}/>{actionError&&<div role="alert">{actionError}</div>}{query.data&&(tab==='tracked'?<><Table heads={['Listing','30-day scenario','Observed reviews','Status','']} rows={tracked.slice(page*20,(page+1)*20).map(x=>[<button className="text-link" onClick={()=>show(x)}>{x.collection?.title||x.listing?.title||x.listing_id}</button>,number(x.review_scenarios?.['30']?.value),number(x.review_scenarios?.['30']?.review_count),<Pill warning>{text(x.status)}</Pill>,<button className="button" onClick={()=>show(x)}>View</button>])}/><div className="pager"><span>{number(tracked.length)} tracked listings</span><div><button className="button" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="button" disabled={(page+1)*20>=tracked.length} onClick={()=>setPage(p=>p+1)}>Next</button></div></div></>:tab==='catalog'?<><Table heads={['Listing','Shop','Price','Observed','Signal','']} rows={(catalog.data?.items||[]).map(x=>[x.title,x.shop,x.price?.value==null?'Unknown':`${number(x.price.value)} ${x.price.currency}`,date(x.observed_at),text(x.signal),<button className="button" disabled={busy===x.listing_id} onClick={()=>void investigate(x)}>{busy===x.listing_id?'Opening…':'Investigate'}</button>])}/><div className="pager"><span>{number(catalog.data?.total)} listings</span><div><button className="button" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous</button><button className="button" disabled={catalog.data?.total==null||(page+1)*20>=catalog.data.total} onClick={()=>setPage(p=>p+1)}>Next</button></div></div></>:<Table heads={['Opportunity','Keyword','Stage','']} rows={(saved.data?.items||[]).filter(x=>JSON.stringify(x).toLowerCase().includes(q.toLowerCase())).map(x=>[x.name,x.keyword,text(x.stage),<Link className="button" to={'/selling?opportunity='+encodeURIComponent(x.id)}>Open opportunity</Link>])}/>)}</>

}

function GeneratorPage({tools}:{tools:()=>void}){

 const {isUserMode,userDataVersion}=useAppMode(),[q,setQ]=useState(''),open=usePipelineDrawer()

 const portfolio=useQuery({queryKey:['test-candidate-portfolio','developer',userDataVersion],queryFn:getTestCandidatePortfolio,enabled:!isUserMode,retry:false})

 const own=useQuery({queryKey:['profitable-store-ideas','user',userDataVersion,12],queryFn:()=>getUserStoreIdeas(12),enabled:isUserMode})

 const candidates=(portfolio.data?.stores||[]).filter(c=>`${c.name} ${c.focus}`.toLowerCase().includes(q.toLowerCase()))

 return <><div className="filters"><label className="search-field"><PipelineIcon name="search"/><input aria-label="Search store candidates" placeholder="Search candidates" value={q} onChange={e=>setQ(e.target.value)}/></label><Pill warning>{isUserMode?'Account ideas':'Provisional candidates'}</Pill></div><QueryState pending={isUserMode?own.isPending:portfolio.isPending} error={isUserMode?own.error:portfolio.error} retry={isUserMode?own.refetch:portfolio.refetch}/>{(isUserMode?own.data:portfolio.data)!==undefined&&(isUserMode?<Table heads={['Store idea','Review','']} rows={(own.data||[]).filter(c=>c.name.toLowerCase().includes(q.toLowerCase())).map(c=>[c.name,'Account evidence',<button className="button" onClick={tools}>Review</button>])}/>:<Table heads={['Candidate','Keywords','Median listing price','Test priority','Validation','']} rows={candidates.map(c=>[<button className="text-link" onClick={()=>open(c.name,<CandidateDetails candidate={c}/>)}>{c.name}</button>,number(c.evidence.keyword_count),money(c.evidence.median_observed_price_usd),`${number(c.test_priority_score)} / ${number(c.score_cap)}`,<Pill warning>{text(c.validation_state)}</Pill>,<button className="button" onClick={()=>open(c.name,<CandidateDetails candidate={c}/>)}>Review</button>])}/>)}</>

}



function StoresPage(){

 const query=useQuery({queryKey:['stores'],queryFn:getStores}),open=usePipelineDrawer()

 return <><QueryState pending={query.isPending} error={query.error} retry={query.refetch}/><section className="section-block pipeline-first-section"><div className="section-heading"><h2>Account stores</h2></div>{query.data&&<Table heads={['Store','Focus','Buyer','Products','']} rows={(query.data||[]).map(store=>[<button className="text-link" onClick={()=>open(store.name,<><Facts rows={[["Focus",store.niche],["Buyer",store.target_audience],["Product types",store.product_types.join(', ')],["Created",date(store.created_at)],["Status",store.active?'Active':'Inactive']]}/><div className="drawer-actions"><Link className="button primary" to={'/stores?store='+encodeURIComponent(store.slug)}>Open store</Link></div></>)}>{store.name}</button>,store.niche,store.target_audience,store.product_types.join(', '),<Link className="button" to={'/stores?store='+encodeURIComponent(store.slug)}>Open store</Link>])}/>}</section></>

}

function LaunchPage(){

 const query=useProduction(usePrivateResearch(true)),review=useReview(),{userDataVersion}=useAppMode()

 // Workspace updates dispatch the existing version event; no second persistence lane.

 void userDataVersion

 const workflows=listLaunchWorkflows()

 return <><section className="section-block pipeline-first-section"><div className="section-heading"><h2>Current products</h2></div><QueryState pending={query.isPending} error={query.error} retry={query.refetch}/><Table heads={['Product','File checks','Cost plan','Owner approval','Publishing','']} rows={latestProducts(query.data?.jobs||[]).map(j=>[<button className="text-link" onClick={()=>review(j)}>{j.spec.name}</button>,<Pill>{text(j.result?.quality?.status)}</Pill>,<Pill warning>{j.spec.unit_cost==null?(j.spec.cost_plan?'Provisional':'Unknown'):'Recorded'}</Pill>,<Pill warning={!['approved','exported'].includes(j.status)}>{['approved','exported'].includes(j.status)?'Recorded':'Required'}</Pill>,<Pill>Not published</Pill>,<button className="button" onClick={()=>review(j)}>Review</button>])}/></section><section className="section-block"><div className="section-heading"><h2>Account workflows</h2></div><Table heads={['Keyword','Product type','Approval','Updated','']} rows={workflows.map(w=>[w.keyword,text(w.productType),w.approval?'Recorded':'Required',date(w.updatedAt),<Link className="button" to={'/launch?workflow='+encodeURIComponent(w.id)}>Open workflow</Link>])}/></section></>

}

function EvidencePage(){
 const health=useQuery({queryKey:['pipeline-health'],queryFn:()=>operatorRequest<{backend:string;collection:{interval_minutes:number}}>('/api/health'),retry:false})

 const [tab,setTab]=useState('collection'),open=usePipelineDrawer()

 const query=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,staleTime:30000,refetchInterval:60000,retry:false})

 const coverage=useQuery({queryKey:['pipeline-reference-coverage'],queryFn:()=>intelligenceRequest<{observations:number;outcomes:number;models:number}>('/coverage'),enabled:tab==='models',retry:false})

 const d=query.data

 return <><div className="tabs">{[['collection','Collection'],['models','Model validation'],['sources','Sources']].map(([key,label])=><button key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</div><QueryState pending={query.isPending} error={query.error} retry={query.refetch}/>{tab==='models'?<section className="section-block"><div className="section-heading"><h2>Sales validation</h2></div><QueryState pending={coverage.isPending} error={coverage.error} retry={coverage.refetch}/><Facts rows={[["Eligible reference observations",number(coverage.data?.observations)],["Actual outcomes",number(coverage.data?.outcomes)],["Registered models",number(coverage.data?.models)],["Uncalibrated review scenarios",number(d?.intelligence?.automatic_estimator?.estimated)],["General sales accuracy","Unproved"],["Verified keyword scores",number(d?.evidence.versioned_scores)],["Verified gap reports",number(d?.evidence.versioned_gaps)]]}/></section>:tab==='sources'?<Table heads={['Source','Keywords','Observations','Last observed']} rows={(d?.sources||[]).map(s=>[<button className="text-link" onClick={()=>open(text(s.source),<Facts rows={[["Source",text(s.source)],["Last observed",date(s.latest)],["Keywords",number(s.keywords)],["Observations",number(s.rows)]]}/>)}>{text(s.source)}</button>,number(s.keywords),number(s.rows),date(s.latest)])}/>:<><section className="section-block"><div className="section-heading"><h2>Collection status</h2></div><Facts rows={[["Backend",health.error?'Unavailable':text(health.data?.backend)],["Collector",text(d?.feed?.status)],["Last cycle",date(d?.feed?.last_completed)],["Latest keyword collection",date(d?.source_watermarks.latest_collection_at)],["Research report",date(d?.generated_at)],["Interval",health.data?number(health.data.collection.interval_minutes)+' minutes':'Unknown'],["Failed keyword states",number(d?.stats.failed)],["No-data keyword states",number(d?.stats.no_data)],["States over 30 days",number(d?.stats.stale)]]}/></section><section className="section-block"><div className="section-heading"><h2>Research categories</h2></div><Table heads={['Category','Keyword ideas']} rows={(d?.stats.domains||[]).slice(0,12).map(row=>[text(row.domain),number(row.cnt)])}/></section></>}</>

}


function CandidateDetails({candidate:c}:{candidate:TestStoreCandidate}){
 return <><Facts rows={[["Median listing price",money(c.evidence.median_observed_price_usd)],["Buyer",c.target_buyer],["Focus",c.focus],["Validation",text(c.validation_state)],["Test priority",`${number(c.test_priority_score)} / ${number(c.score_cap)}`],["Verified profit","Unknown"]]}/><section className="drawer-section"><h2>Keywords</h2><Table heads={['Keyword','Etsy listings','Sampled','Google searches / month']} rows={c.keywords.map(k=>[<span>{k.keyword}<KeywordRightsFlag keyword={k.keyword}/></span>,number(k.listing_count),number(k.sampled_listing_count),number(k.monthly_searches)])}/></section><section className="drawer-section"><h2>Product candidates</h2><Table heads={['Product','Type','Keyword']} rows={c.product_candidates.map(p=>[p.title,text(p.product_type),p.primary_keyword])}/></section><section className="drawer-section"><h2>Remaining evidence</h2><ul>{c.blockers.map((b,i)=><li key={i}>{b}</li>)}</ul></section><div className="drawer-actions"><Link className="button primary" to={'/store-generator?candidate='+encodeURIComponent(c.id)}>Create store</Link></div></>
}

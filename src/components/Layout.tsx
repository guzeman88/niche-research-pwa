import {operatorRequest,readConnection} from '../lib/operatorConnection'
import type {BackendHealth} from '../lib/dataContracts'
import useNetworkOnline from '../hooks/useNetworkOnline'
import {recoveryInterval} from '../lib/readRecovery'
import {markStartupChanged} from '../lib/startup'
import {date,number} from '../pipeline/format'

import {usePipelineDrawer} from '../pipeline/drawerContext'

import {Outlet, useLocation} from 'react-router-dom'

import {useEffect,useState} from 'react'

import useClock from '../hooks/useClock'

import type {ReactNode} from 'react'

import {useQuery,useQueryClient} from '@tanstack/react-query'

import Sidebar from './Sidebar'

import WorkspaceSaveStatus from './account/WorkspaceSaveStatus'

import {getDashboardSummary} from '../lib/dashboardSummary'

import {useAuth} from '../lib/auth'

import {useAppMode} from '../lib/appMode'

import {PipelineProvider,Facts} from '../pipeline/PipelineUI'



export default function Layout({content,local=false}:{content?:ReactNode;local?:boolean}){

 return <div className="pipeline-app flow"><PipelineProvider><PipelineLayout local={local}>{content||<Outlet/>}</PipelineLayout></PipelineProvider></div>

}
function PipelineLayout({children,local}:{children:ReactNode;local:boolean}){
 const client=useQueryClient(),[,connectionChanged]=useState(0)
 useEffect(()=>{const changed=()=>{connectionChanged(v=>v+1);void client.resetQueries({predicate:q=>['pipeline-artifact','production-launch-recipes','supported-keyword-goal','pipeline-reference-coverage','pipeline-health','product-validation','production','pipeline-keywords','selling-products','selling-discovery','automatic-sales-estimates'].includes(String(q.queryKey[0]))})};window.addEventListener('etgen:connection-updated',changed);return()=>window.removeEventListener('etgen:connection-updated',changed)},[client])
 useEffect(()=>{const changed=(event:Event)=>{const path=(event as CustomEvent<string>).detail;const keys=path.startsWith('/api/product-validation')?['startup','product-validation','supported-keyword-goal']:path.startsWith('/api/production')?['startup','production-job','production','product-validation']:path.startsWith('/api/selling-products')?['selling-products','selling-discovery']:path.startsWith('/api/sales-intelligence')?['automatic-sales-estimates','pipeline-reference-coverage']:[];if(keys.includes('startup'))markStartupChanged();for(const key of keys)void client.invalidateQueries({queryKey:[key]})};window.addEventListener('etgen:research-updated',changed);return()=>window.removeEventListener('etgen:research-updated',changed)},[client])
 const now=useClock(),online=useNetworkOnline()
 const auth=useAuth(),{isUserMode}=useAppMode(),location=useLocation(),open=usePipelineDrawer()
 const accountScope=['/account','/workspace','/stores'].includes(location.pathname)
 const query=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled:!local&&!accountScope&&auth.profile?.role==='admin'&&!isUserMode,staleTime:30000,refetchInterval:recoveryInterval(60000),retry:false})
 const health=useQuery({queryKey:['pipeline-health'],queryFn:()=>operatorRequest<BackendHealth>('/api/health'),enabled:!accountScope&&(local||(!isUserMode&&auth.profile?.role==='admin'))&&Boolean(readConnection().url),retry:false,refetchInterval:recoveryInterval(60000)})
 const storage=health.data?.storage||query.data?.storage
 const report=!local&&!isUserMode&&!accountScope?query.data:undefined
 useEffect(()=>{window.scrollTo(0,0);const h=document.querySelector<HTMLElement>('.pipeline-main h1');if(h){h.tabIndex=-1;h.focus({preventScroll:true})}},[location.pathname])
 return <><a className="skip" href="#pipeline-main">Skip to page</a><div className="app-shell"><aside className="sidebar"><Sidebar local={local}/></aside><div className="content-shell"><div className="capture-header"><span className="pill">{!online?'Offline':local?'Local workspace':(isUserMode||accountScope)?'Account workspace':query.error||health.error?'Reconnecting':storage?.status==='critical'?'Storage low':storage?.status==='low'?'Storage low':query.data?.delivery.mode==='fallback'?'Historical report':query.data&&(!Number.isFinite(Date.parse(query.data.generated_at))||query.data.delivery.stale||now-Date.parse(query.data.generated_at)>150000)?'Sync delayed':'Research workspace'}</span><button onClick={()=>open('Data sources',<ReportDetails local={local} user={isUserMode||accountScope}/>)}>{report?'Report · '+date(report.generated_at):'Data sources'}</button></div><WorkspaceSaveStatus/><main id="pipeline-main" className="pipeline-main">{children}</main></div></div></>
}
function ReportDetails({local,user}:{local:boolean;user:boolean}){
 const health=useQuery({queryKey:['pipeline-health'],queryFn:()=>operatorRequest<BackendHealth>('/api/health'),enabled:(local||!user)&&Boolean(readConnection().url),retry:false})
 const query=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled:!local&&!user,staleTime:30000,retry:false})
 return <><Facts rows={[["Research report",date(!local&&!user?query.data?.generated_at:null)],["Latest collection",date(!local&&!user?query.data?.source_watermarks.latest_collection_at:null)],["Connection",local?'Local backend':user?'Account workspace':health.error?'Reconnecting':health.data?.status==='ok'?'Connected':query.data?.connection?.status||'Unknown'],["Report scope",local?'Local research':user?'Account records':query.data?.scope==='historical_static_release'?'Historical report':query.data?.scope==='native_collection_library'?'Local research library':query.data?.scope||'Unknown'],["Sales","Unverified"],["Free storage",health.data?.storage?.free_bytes==null?'Unknown':number(health.data.storage.free_bytes/1073741824)+' GB'],["Collection reserve",health.data?.storage?.minimum_free_bytes==null?'Unknown':number(health.data.storage.minimum_free_bytes/1073741824)+' GB'],...(!local&&!user?[["Keyword ideas",number(query.data?.stats.total_seeds)],["Listing evidence",number(query.data?.stats.evidence_backed)],["Attempted coverage",query.data?.stats.coverage_pct==null?'Unknown':number(query.data.stats.coverage_pct)+'%'],["Tracked listings",number(query.data?.intelligence?.automatic_estimator?.tracked)]] as Array<[string,string]>:[])]}/>{!local&&!user&&<div className="drawer-actions"><button className="button" onClick={()=>void query.refetch()} disabled={query.isFetching}>Refresh report</button></div>}{query.error&&<div role="alert">{query.error.message}</div>}</>
}

import {date,number} from '../pipeline/format'

import {usePipelineDrawer} from '../pipeline/drawerContext'

import {Outlet, useLocation} from 'react-router-dom'

import {useEffect} from 'react'

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
 const client=useQueryClient()
 useEffect(()=>{const changed=(event:Event)=>{const path=(event as CustomEvent<string>).detail;const keys=path.startsWith('/api/product-validation')?['product-validation','supported-keyword-goal']:path.startsWith('/api/production')?['production','product-validation']:path.startsWith('/api/selling-products')?['selling-products','selling-discovery']:path.startsWith('/api/sales-intelligence')?['automatic-sales-estimates','pipeline-reference-coverage']:[];for(const key of keys)void client.invalidateQueries({queryKey:[key]})};window.addEventListener('etgen:research-updated',changed);return()=>window.removeEventListener('etgen:research-updated',changed)},[client])
 const now=useClock()
 const auth=useAuth(),{isUserMode}=useAppMode(),location=useLocation(),open=usePipelineDrawer()
 const accountScope=['/account','/workspace','/stores'].includes(location.pathname)
 const query=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled:!local&&!accountScope&&auth.profile?.role==='admin'&&!isUserMode,staleTime:30000,refetchInterval:60000,retry:false})
 const report=!local&&!isUserMode&&!accountScope?query.data:undefined
 useEffect(()=>{window.scrollTo(0,0);const h=document.querySelector<HTMLElement>('.pipeline-main h1');if(h){h.tabIndex=-1;h.focus({preventScroll:true})}},[location.pathname])
 return <><a className="skip" href="#pipeline-main">Skip to page</a><div className="app-shell"><aside className="sidebar"><Sidebar local={local}/></aside><div className="content-shell"><div className="capture-header"><span className="pill">{local?'Local workspace':(isUserMode||accountScope)?'Account workspace':query.data?.delivery.mode==='fallback'?'Historical report':query.data&&(!Number.isFinite(Date.parse(query.data.generated_at))||query.data.delivery.stale||now-Date.parse(query.data.generated_at)>150000)?'Sync delayed':'Research workspace'}</span><button onClick={()=>open('Data sources',<ReportDetails local={local} user={isUserMode||accountScope}/>)}>{report?'Report · '+date(report.generated_at):'Data sources'}</button></div><WorkspaceSaveStatus/><main id="pipeline-main" className="pipeline-main">{children}</main></div></div></>
}
function ReportDetails({local,user}:{local:boolean;user:boolean}){
 const query=useQuery({queryKey:['dashboard-summary'],queryFn:getDashboardSummary,enabled:!local&&!user,staleTime:30000,retry:false})
 return <><Facts rows={[["Research report",date(!local&&!user?query.data?.generated_at:null)],["Latest collection",date(!local&&!user?query.data?.source_watermarks.latest_collection_at:null)],["Connection",local?'Local backend':user?'Account workspace':query.data?.connection?.status||'Unknown'],["Report scope",local?'Local research':user?'Account records':query.data?.scope||'Active research'],["Sales","Unverified"],...(!local&&!user?[["Keyword ideas",number(query.data?.stats.total_seeds)],["Listing evidence",number(query.data?.stats.evidence_backed)],["Attempted coverage",query.data?.stats.coverage_pct==null?'Unknown':number(query.data.stats.coverage_pct)+'%'],["Tracked listings",number(query.data?.intelligence?.automatic_estimator?.tracked)]] as Array<[string,string]>:[])]}/>{!local&&!user&&<div className="drawer-actions"><button className="button" onClick={()=>void query.refetch()} disabled={query.isFetching}>Refresh report</button></div>}{query.error&&<div role="alert">{query.error.message}</div>}</>
}

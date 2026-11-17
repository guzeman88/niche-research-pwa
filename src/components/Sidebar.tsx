import {useQuery} from '@tanstack/react-query'
import {productionRequest} from '../lib/production'
import type {ProductionOverview} from '../lib/production'
import {validationRequest} from '../lib/productValidation'
import type {ValidationOverview} from '../lib/productValidation'
import {readConnection} from '../lib/operatorConnection'
import {usePipelineDrawer} from '../pipeline/drawerContext'

import {NavLink,Link,useLocation} from 'react-router-dom'

import {useAuth} from '../lib/auth'

import {useAppMode} from '../lib/appMode'

import {PipelineIcon,Facts} from '../pipeline/PipelineUI'

const items=[['/','Dashboard','grid'],['/keywords','Keywords','search'],['/selling','Selling products','chart'],['/validation','Product validation','check'],['/production','Production','box'],['/store-generator','Store Generator','layers'],['/launch','Launch Lab','file'],['/stores','My Stores','box'],['/evidence','Evidence','chart'],['/workspace','Workspace & backups','layers'],['/account','Account & profile','account']] as const

const privatePages=['/selling','/validation','/production','/launch','/evidence']

export default function Sidebar({local=false}:{local?:boolean}){

 const auth=useAuth(),open=usePipelineDrawer(),location=useLocation()

 const {isUserMode}=useAppMode(),enabled=Boolean(readConnection().url)&&(local||auth.profile?.role==='admin'&&!isUserMode)
 const projects=useQuery({queryKey:['product-validation',0],queryFn:()=>validationRequest<ValidationOverview>(),enabled,staleTime:30000,refetchInterval:60000,retry:false})
 const production=useQuery({queryKey:['production'],queryFn:()=>productionRequest<ProductionOverview>(),enabled,staleTime:30000,refetchInterval:60000,retry:false})
 const badge=(path:string)=>enabled&&path==='/validation'&&Array.isArray(projects.data?.projects)?<span className="count">{projects.data!.projects.length}</span>:enabled&&path==='/production'&&Array.isArray(production.data?.jobs)?<span className="count">{new Set(production.data!.jobs.map(j=>j.product_id)).size}</span>:null
 const visible=items.filter(([path])=>local||auth.profile?.role==='admin'||!privatePages.includes(path))

 const links=()=>visible.map(([path,label,icon])=>local&&!['/selling','/validation','/production'].includes(path)?<a key={path} href={'https://etgen.xyz'+path}><PipelineIcon name={icon}/><span>{label}</span></a>:<NavLink key={path} to={path} end={path==='/'} onClick={()=>document.querySelector<HTMLDetailsElement>('#mobile-pages')?.removeAttribute('open')}><PipelineIcon name={icon}/><span>{label}</span>{badge(path)}</NavLink>)

 return <><Link className="brand" to={local?'/validation':'/'}>EtGen</Link><nav className="primary-nav" aria-label="EtGen pages">{links()}</nav><div className="sidebar-tools"><button className="snapshot-button" onClick={()=>open('Workspace',<WorkspaceInfo local={local}/>)}>Workspace</button><details id="mobile-pages" className="pages mobile-pages" key={location.pathname}><summary>All pages</summary><nav aria-label="Mobile EtGen pages">{links()}</nav></details></div></>

}


function WorkspaceInfo({local}:{local:boolean}){
 const auth=useAuth(),{mode,setMode}=useAppMode()
 return <><Facts rows={[["Scope",local?'Local research':mode==='developer'?'Active research':'Account records'],["Access",local?'Local operator':auth.profile?.role==='admin'?'Administrator':'Member']]}/>{!local&&auth.profile?.role==='admin'&&<div className="drawer-actions"><button className="button" aria-pressed={mode==='developer'} onClick={()=>setMode('developer')}>Developer</button><button className="button" aria-pressed={mode==='user'} onClick={()=>setMode('user')}>User</button></div>}</>
}

import type {QueryClient} from '@tanstack/react-query'
import type {DashboardSummary} from '../types/api'
import {validStartup} from './startup'

const PREFIX='etgen:startup:v1:',LIMIT=128*1024,TTL=86400000
const key=(owner:string,role:string)=>PREFIX+encodeURIComponent(owner)+':'+role
export function purgeStartupCache(storage:Storage=localStorage,except=''){
  try{for(let i=storage.length-1;i>=0;i--){const name=storage.key(i);if(name?.startsWith(PREFIX)&&name!==except)storage.removeItem(name)}}catch{/* Storage is optional. */}
}
// Persist only allowlisted display data; never an arbitrary query or auth object.
export function startupDisplay(value:unknown){
  if(!validStartup(value))return undefined
  return {schema_version:1,generated_at:value.generated_at,input_fingerprint:value.input_fingerprint,
    projects:value.projects.status==='ready'?{status:'ready',total:value.projects.total,has_more:value.projects.has_more,projects:value.projects.projects.map(p=>({id:p.id,name:p.name,product_type:p.product_type,updated_at:p.updated_at}))}:{status:'unavailable',projects:null,total:null,error:'Saved projects could not be read. Retry the connection.'},
    production:value.production.status==='ready'?{status:'ready',total:value.production.total,has_more:value.production.has_more,paused:value.production.paused,human_approval_required:true,jobs:value.production.jobs.map(j=>({id:j.id,product_id:j.product_id,revision:j.revision,status:j.status,updated_at:j.updated_at,spec:{name:j.spec.name,family:j.spec.family},has_preview:j.has_preview}))}:{status:'unavailable',jobs:null,total:null,error:'Saved production could not be read. Retry the connection.'}}
}
export function dashboardDisplay(value:unknown){
  const v=value as DashboardSummary
  if(!v||v.delivery?.mode!=='live'||!Number.isFinite(Date.parse(v.generated_at))||typeof v.input_fingerprint!=='string'||!Array.isArray(v.sources)||!v.stats||!Number.isSafeInteger(v.stats.total_seeds)||v.stats.total_seeds<0||!v.evidence||!v.source_watermarks)return undefined
  return {schema_version:v.schema_version,scope:v.scope,snapshot_version:v.snapshot_version,generated_at:v.generated_at,data_status:v.data_status,input_fingerprint:v.input_fingerprint,source_watermarks:v.source_watermarks,duration_ms:v.duration_ms,stats:v.stats,evidence:v.evidence,providers:[],sources:v.sources,feed:v.feed,delivery:v.delivery,storage:v.storage,connection:v.connection,coverage:v.coverage,intelligence:v.intelligence,production:v.production,validation:v.validation,supported:v.supported,score_distribution:v.score_distribution,research_leads:v.research_leads,breakouts:v.breakouts}
}
export function hydrateStartupCache(client:QueryClient,owner:string,role:string,storage:Storage=localStorage){
  const name=key(owner,role);purgeStartupCache(storage,name)
  if(role!=='admin'){purgeStartupCache(storage);return}
  try{
    const raw=storage.getItem(name)
    if(!raw||raw.length>LIMIT)return
    const saved=JSON.parse(raw),age=Date.now()-saved.savedAt
    if(saved.owner!==owner||saved.role!==role||!Number.isFinite(age)||age<0||age>TTL){storage.removeItem(name);return}
    for(const [query,project] of [['startup',startupDisplay],['dashboard-summary',dashboardDisplay]] as const){
      const data=project(saved[query]),at=data?Date.parse(data.generated_at):0
      if(data&&at<=Date.now()+5000&&Date.now()-at<TTL)client.setQueryData([query],data,{updatedAt:at})
    }
  }catch{try{storage.removeItem(name)}catch{/* Optional cache. */}}
}
export function persistStartupCache(client:QueryClient,owner:string,role:string,storage:Storage=localStorage){
  if(role!=='admin')return
  const payload={owner,role,savedAt:Date.now(),startup:startupDisplay(client.getQueryData(['startup'])),'dashboard-summary':dashboardDisplay(client.getQueryData(['dashboard-summary']))}
  try{const text=JSON.stringify(payload);if(text.length<=LIMIT)storage.setItem(key(owner,role),text)}catch{/* Quota/private mode cannot prevent login. */}
}

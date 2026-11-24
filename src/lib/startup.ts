import {accountRequest} from './accountApi'
import {accountConnectionAvailable,operatorRequest} from './operatorConnection'

export interface StartupJob {id:string;product_id:string;revision:string;status:string;updated_at:string;spec:{name:string;family:string};has_preview:boolean}
export interface StartupProject {id:string;name:string;product_type?:string;updated_at:string}
type Part<T,K extends string> = {status:'ready';total:number;has_more:boolean}&Record<K,T[]> | {status:'unavailable';total:null;error:string}&Record<K,null>
export interface StartupSummary {schema_version:1;generated_at:string;input_fingerprint:string;projects:Part<StartupProject,'projects'>;production:Part<StartupJob,'jobs'>&{paused?:boolean;human_approval_required?:true}}

export function validStartup(value:unknown):value is StartupSummary {
  const v=value as StartupSummary
  if(!v||v.schema_version!==1||!Number.isFinite(Date.parse(v.generated_at))||typeof v.input_fingerprint!=='string')return false
  const check=(part:StartupSummary['projects']|StartupSummary['production'],key:'projects'|'jobs',max:number)=>{
    if(!part)return false
    const rows=(part as unknown as Record<string,unknown>)[key]
    if(part.status==='unavailable')return rows===null&&part.total===null&&typeof part.error==='string'
    if(part.status!=='ready'||!Array.isArray(rows)||rows.length>max||!Number.isSafeInteger(part.total)||part.total<rows.length||part.has_more!==(part.total>rows.length))return false
    const ids=new Set<string>()
    return rows.every(row=>{
      if(typeof row?.id!=='string'||ids.has(row.id)||!Number.isFinite(Date.parse(row.updated_at)))return false
      ids.add(row.id)
      return key==='projects'?typeof row.name==='string':typeof row.spec?.name==='string'&&typeof row.spec.family==='string'&&typeof row.product_id==='string'&&typeof row.revision==='string'&&typeof row.status==='string'&&typeof row.has_preview==='boolean'
    })
  }
  return check(v.projects,'projects',50)&&check(v.production,'jobs',24)
}
let changes=0,refreshed=0
export function markStartupChanged(){changes++}
export async function getStartup():Promise<StartupSummary>{
  const version=changes,refresh=version>refreshed
  const value=accountConnectionAvailable()?await accountRequest<StartupSummary>('/startup'+(refresh?'?refresh=1':'')):await operatorRequest<StartupSummary>('/api/startup')
  if(!validStartup(value))throw new Error('The product summary failed consistency checks. Previously loaded data may be shown.')
  if(refresh)refreshed=Math.max(refreshed,version)
  return value
}

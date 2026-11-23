// Validate transport contracts, never infer sales, replace unknowns with zero,
// or silently turn a malformed response into an empty list.
const object=(v:unknown):v is Record<string,unknown>=>Boolean(v)&&typeof v==='object'&&!Array.isArray(v)
const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0
const finite=(v:unknown)=>v==null||(typeof v==='number'&&Number.isFinite(v))
export class DataIntegrityError extends Error {}
export function validateReadData(path:string,data:unknown):void {
 const route=path.split('?')[0]
 const fail=()=>{throw new DataIntegrityError('The service returned incomplete or inconsistent data. The last successful records have been retained.')}
 const list=(key:string,identifier?:string)=>{
  if(!object(data)||!Array.isArray(data[key]))return fail()
  const rows=data[key] as unknown[]
  if(!rows.every(object))return fail()
  if(identifier){const ids=rows.map(row=>(row as Record<string,unknown>)[identifier]);if(ids.some(id=>typeof id!=='string'||!id)||new Set(ids).size!==ids.length)return fail()}
  return rows as Record<string,unknown>[]
 }
 if(route==='/api/product-validation'){
  const rows=list('projects','id')
  if(rows.some(row=>typeof row.name!=='string'||!Array.isArray(row.keywords)||!object(row.outcomes)||!finite(row.outcomes.orders)||!finite(row.outcomes.revenue)||!finite(row.outcomes.net_profit)))fail()
 }else if(route==='/api/production'){
  const rows=list('jobs','id')
  if(rows.some(row=>typeof row.revision!=='string'||!object(row.spec)||typeof row.spec.name!=='string'||!finite(row.spec.price)))fail()
 }else if(route==='/api/dashboard/keywords'){
  const rows=list('items','keyword')
  if(!object(data)||!count(data.total)||(data.total as number)<rows.length||rows.some(row=>(row.listing_count!=null&&!count(row.listing_count))||(row.sampled_listing_count!=null&&!count(row.sampled_listing_count))||!finite(row.avg_price_usd)||(typeof row.avg_price_usd==='number'&&row.avg_price_usd<0)))fail()
 }else if(route==='/api/sales-intelligence/estimates'||route==='/api/selling-products/discovery'){
  const rows=list('items','listing_id')
  if(object(data)&&data.total!=null&&(!count(data.total)||(data.total as number)<rows.length))fail()
 }else if(route==='/api/product-validation/supported-keywords'){
  list('candidates','keyword')
 }else if(route==='/api/production/launch-recipes'){
  list('recipes','id')
 }else if(route==='/api/sales-intelligence/coverage'){
  if(!object(data)||['observations','outcomes','models'].some(key=>!count(data[key])))fail()
 }else if(route==='/api/health'){
  if(!object(data)||typeof data.status!=='string')fail()
  if(object(data)&&object(data.collection_scheduler)&&data.collection_scheduler.interval_minutes!=null&&(!finite(data.collection_scheduler.interval_minutes)||(data.collection_scheduler.interval_minutes as number)<=0))fail()
 }
}

export interface BackendHealth {
 status:string
 collection_scheduler?:{interval_minutes?:number}|null
 storage?:{status:string;free_bytes:number|null;minimum_free_bytes:number}
}

export function validateCandidatePortfolio(data:unknown):void {
 if(!object(data)||!Array.isArray(data.stores)||data.stores.some(row=>!object(row)||typeof row.id!=='string'||typeof row.name!=='string'||!object(row.evidence)||!count(row.evidence.keyword_count)||!finite(row.evidence.median_observed_price_usd)||!Array.isArray(row.keywords)||!Array.isArray(row.product_candidates)||!Array.isArray(row.blockers)))throw new DataIntegrityError('Store candidate data is incomplete. Previously loaded records have been retained.')
}

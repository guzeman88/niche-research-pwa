const finite=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
const age=(value,now)=>{const time=Date.parse(value);return Number.isFinite(time)&&time<=now+60000?Math.max(0,now-time):Infinity};
export async function sampleHealth(service,read=fetch,now=Date.now()){
 const checks=await Promise.all([
  (async()=>{try{
   const {data,error}=await service.rpc('app_account_service_health');
   if(error||!finite(data?.database_bytes)||!finite(data?.warning_bytes)||data.warning_bytes===0)throw new Error();
   return {id:'account_storage',status:data.database_bytes>=data.warning_bytes?'warning':'healthy',details:{database_bytes:data.database_bytes,warning_bytes:data.warning_bytes}};
  }catch{return {id:'account_storage',status:'unavailable',details:{reason:'storage_check_failed'}}}})(),
  (async()=>{try{
   const {data,error}=await service.from('app_backend_connections').select('updated_at,enabled').eq('id','active').maybeSingle();
   if(error||!data)throw new Error();
   const fresh=data.enabled===true&&age(data.updated_at,now)<=150000;
   return {id:'private_backend',status:fresh?'healthy':'warning',details:{reason:fresh?'heartbeat_current':'heartbeat_delayed',last_heartbeat:data.updated_at}};
  }catch{return {id:'private_backend',status:'unavailable',details:{reason:'heartbeat_unavailable'}}}})(),
  (async()=>{try{
   const response=await read('https://etgen.xyz/data/current/release.json?health='+now,{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(12000)});
   if(!response.ok||!response.headers.get('content-type')?.includes('application/json')||Number(response.headers.get('content-length')||0)>262144)throw new Error();
   const text=await response.text();if(text.length>262144)throw new Error();const m=JSON.parse(text);
   if(m.schema_version!==1||m.source!=='supabase_local'||m.scope!=='local_research_projection'||!/^[a-f0-9]{64}$/.test(m.id)||!Number.isSafeInteger(m.resources?.['keywords.json']?.items)||m.resources['keywords.json'].items<0)throw new Error();
   const fresh=age(m.generated_at,now)<=13*3600000&&age(m.source_data_as_of,now)<=48*3600000;
   return {id:'public_research',status:fresh?'healthy':'warning',details:{reason:fresh?'published_current':'publication_or_source_delayed',generated_at:m.generated_at,source_data_as_of:m.source_data_as_of,keyword_count:m.resources['keywords.json'].items}};
  }catch{return {id:'public_research',status:'unavailable',details:{reason:'published_package_unavailable'}}}})(),
 ]);
 const result=await service.rpc('app_record_health_checks',{checks});
 if(result.error)throw new Error('Health status could not be recorded.');
 return checks;
}
export function publicHealthRows(rows,now=Date.now()){
 if(!Array.isArray(rows))throw new Error('Health status is unavailable.');
 return ['account_storage','private_backend','public_research'].map(id=>{
  const row=rows.find(r=>r.id===id),stale=!row||age(row.checked_at,now)>11*60000;
  return row?{id,status:stale?'unavailable':row.status,checked_at:row.checked_at,first_seen_at:row.first_seen_at,resolved_at:row.resolved_at,details:row.details,stale}:{id,status:'unavailable',checked_at:null,details:{reason:'not_checked'},stale:true};
 });
}

import {createClient} from '@supabase/supabase-js';
import {accountServiceConfig} from './lib/account-service-config.mjs';
import {buildCollectionReport} from './lib/collection-report.mjs';

export default async function handler(request){
 const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'public, max-age=0, s-maxage=300','X-Content-Type-Options':'nosniff'};
 if(request.method!=='GET')return new Response(JSON.stringify({error:'Method not allowed.'}),{status:405,headers});
 try{
  const config=accountServiceConfig(process.env);
  if(!config.url||!config.serviceKey)throw new Error();
  const service=createClient(config.url,config.serviceKey,{auth:{persistSession:false,autoRefreshToken:false},global:{fetch:(input,init={})=>fetch(input,{...init,signal:AbortSignal.timeout(12000)})}});
  const {data,error}=await service.from('app_dashboard_state').select('generated_at,payload').eq('id','active').maybeSingle();
  const bundle=data?.payload?.public_collection,at=Date.now();
  const fresh=value=>Number.isFinite(Date.parse(value))&&Date.parse(value)<=at+60000&&at-Date.parse(value)<=75*60000;
  if(error||!bundle||bundle.schema_version!==1||bundle.scope!=='native_collection_library'||bundle.rate_basis!=='observed_storage'||!fresh(data.generated_at)||!fresh(bundle.generated_at)||bundle.data_status==='unavailable')throw new Error();
  const counts=Object.fromEntries(Object.entries(bundle.counts||{}).filter(([name,value])=>/^[a-z_]+_(total|24h)$/.test(name)&&Number.isSafeInteger(value)&&value>=0));
  const latest=Object.fromEntries(Object.entries(bundle.latest||{}).filter(([name,value])=>/^[a-z_]+$/.test(name)&&typeof value==='string'&&Number.isFinite(Date.parse(value))));
  const report=buildCollectionReport({counts,latest,measuredStorage:true,now:new Date(bundle.generated_at),dataStatus:bundle.data_status});
  return new Response(JSON.stringify({...report,scope:bundle.scope,window_start:bundle.window_start}),{headers});
 }catch{return new Response(JSON.stringify({error:'Current collection measurements are unavailable. No fallback values were used.'}),{status:503,headers:{...headers,'Cache-Control':'no-store'}})}
}
export const config={path:'/api/collection-rates'};

import {createClient} from '@supabase/supabase-js';
import {createRequire} from 'node:module';
import {activeBackend,accessTicket,backendPath} from '../netlify/functions/lib/backend-access.mjs';
const {readPackage}=createRequire(import.meta.url)('./public-research-package.cjs');

export async function readPrivatePackage(env=process.env,read=fetch){
 const {ACCOUNT_SUPABASE_URL:url,ACCOUNT_SUPABASE_SERVICE_ROLE_KEY:key,DASHBOARD_BRIDGE_SECRET:secret}=env;
 if(!url||!key||!secret||!/^https:\/\/[a-z]{20}\.supabase\.co\/?$/.test(url))throw new Error('Dedicated publisher credentials are not configured.');
 const service=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false},global:{fetch:(input,init={})=>read(input,{...init,signal:AbortSignal.timeout(12000)})}});
 const backend=await activeBackend(service,secret);
 return readPackage((name,identity)=>{
  const path='/api/export/public-snapshot'+(name==='release.json'?'':'/'+identity+'/'+name);
  const ticket=accessTicket(backend,backendPath(path,'GET'),'etgen-public-publisher');
  // Only short-lived, exact-path read permissions leave this build process.
  return read(ticket.url,{headers:{Authorization:'Bearer '+ticket.token},redirect:'error',cache:'no-store',signal:AbortSignal.timeout(120000)});
 });
}

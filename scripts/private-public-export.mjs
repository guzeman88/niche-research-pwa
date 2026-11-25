import {createClient} from '@supabase/supabase-js';
import {createRequire} from 'node:module';
import {setTimeout as pause} from 'node:timers/promises';
import {activeBackend,accessTicket,backendPath} from '../netlify/functions/lib/backend-access.mjs';
const {readPackage}=createRequire(import.meta.url)('./public-research-package.cjs');

export async function waitForBackend(service,secret,{lookup=activeBackend,wait=pause}={}){
 for(let attempt=0;;attempt++){
  try{return await lookup(service,secret)}catch(error){
   if(attempt>=6||!/connector is reconnecting|heartbeat is delayed|connection status could not be checked/i.test(error.message))throw error;
   await wait(5000);
  }
 }
}

export async function readPrivatePackage(env=process.env,read=fetch){
 const {ACCOUNT_SUPABASE_URL:url,ACCOUNT_SUPABASE_SERVICE_ROLE_KEY:key,DASHBOARD_BRIDGE_SECRET:secret}=env;
 if(!url||!key||!secret||!/^https:\/\/[a-z]{20}\.supabase\.co\/?$/.test(url))throw new Error('Dedicated publisher credentials are not configured.');
 const service=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false},global:{fetch:(input,init={})=>read(input,{...init,signal:AbortSignal.timeout(12000)})}});
 for(let attempt=0;;attempt++){
 const backend=await waitForBackend(service,secret);
 try{return await readPackage((name,identity)=>{
  const path='/api/export/public-snapshot'+(name==='release.json'?'':'/'+identity+'/'+name);
  const ticket=accessTicket(backend,backendPath(path,'GET'),'etgen-public-publisher');
  // Only short-lived, exact-path read permissions leave this build process.
  return read(ticket.url,{headers:{Authorization:'Bearer '+ticket.token},redirect:'error',cache:'no-store',signal:AbortSignal.timeout(120000)});
 })}catch(error){
  if(attempt>=2||!(/request failed: HTTP (502|503|504)/.test(error.message)||['TimeoutError','AbortError'].includes(error.name)||error instanceof TypeError&&/fetch failed/i.test(error.message)))throw error;
  // Discard a partial family and obtain fresh registry/read tickets. Never
  // retry an authorization, checksum, schema or size-bound failure.
  await pause(5000);
 }
 }
}

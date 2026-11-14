import {activeBackend,accessTicket,backendPath} from './backend-access.mjs';

export async function sellerRequest(service,account,path,body,fetcher=fetch){
  const method=body===undefined?'GET':'POST';
  const resource=backendPath('/api/production/etsy/'+path,method);
  const backend=await activeBackend(service,process.env.DASHBOARD_BRIDGE_SECRET);
  const ticket=accessTicket(backend,resource,account);
  const response=await fetcher(ticket.url,{method,redirect:'error',signal:AbortSignal.timeout(28000),
    headers:{Authorization:`Bearer ${ticket.token}`,'Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok)throw new Error('The seller connection could not be verified.');
  return response.json();
}

export function verifiedAuthorization(result){
  const target=new URL(result.authorize_url);
  if(target.origin!=='https://www.etsy.com'||target.pathname!=='/oauth/connect'||target.username||target.password||target.hash)
    throw new Error('The seller authorization address failed verification.');
  return {authorize_url:target.href,expected_shop:result.expected_shop};
}

export function callbackFields(url){
  const state=url.searchParams.get('state'),code=url.searchParams.get('code');
  if(url.searchParams.has('error'))return null;
  if(typeof state!=='string'||!/^[A-Za-z0-9_-]{20,200}$/.test(state)||typeof code!=='string'||code.length<1||code.length>2000)
    throw new Error('The seller callback is incomplete.');
  return {state,code};
}

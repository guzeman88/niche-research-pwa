import {createHmac} from 'node:crypto';
import {unseal} from './account-security.mjs';

export function backendPath(path, method='GET') {
  if(typeof path!=='string'||path.length>4000||!path.startsWith('/api/')||path.includes('#')||path.includes('\\'))throw new Error('Invalid research action.');
  if(decodeURIComponent(path.split('?')[0]).includes('..'))throw new Error('Invalid research action.');
  const url=new URL(path,'https://backend.invalid');
  const decoded=decodeURIComponent(url.pathname);
  if(url.origin!=='https://backend.invalid'||decoded.includes('..')||decoded.includes('\\')||decoded.includes('//')||decoded.includes('%')||[...decoded].some(c=>c.charCodeAt(0)<32))throw new Error('Invalid research action.');
  if(!/^\/api\/(stats|health|dashboard|scheduler|settings|stream|stores|workspace|evidence|research|keywords|gaps|designs|export|store-ideas|validation|product-validation|selling-products|sales-intelligence|production)(\/|$)/.test(decoded))throw new Error('Unsupported research action.');
  if(!['GET','POST','PUT','DELETE'].includes(method))throw new Error('Unsupported research method.');
  return {url,path:decoded,method};
}

export async function activeBackend(service, secret, at=Date.now()) {
  const result=await service.from('app_backend_connections').select('*').eq('id','active').maybeSingle();
  const updated=Date.parse(result.data?.updated_at);
  if(result.error||!result.data?.enabled||!Number.isFinite(updated)||updated>at+5000||at-updated>150000)throw new Error('The local research service is offline. Keep the EtGen computer running and retry.');
  const endpoint=new URL(result.data.endpoint);
  if(endpoint.protocol!=='https:'||!endpoint.hostname.endsWith('.trycloudflare.com')||endpoint.username||endpoint.password||endpoint.search||endpoint.hash||endpoint.pathname!=='/')throw new Error('The research connection failed verification.');
  const {token}=unseal(result.data.credential,secret,'private-backend');
  if(typeof token!=='string'||token.length<40)throw new Error('The research connection failed verification.');
  return {endpoint:endpoint.origin,token};
}

export function accessTicket(backend, resource, accountId, at=Date.now()) {
  const iat=Math.floor(at/1000);
  const encode=value=>Buffer.from(JSON.stringify(value)).toString('base64url');
  const data=encode({alg:'HS256',typ:'JWT'})+'.'+encode({iss:'etgen-account-bridge',aud:'etgen-private-api',sub:accountId,method:resource.method,path:resource.path,iat,exp:iat+30});
  const token=data+'.'+createHmac('sha256',backend.token).update(data).digest('base64url');
  return {url:backend.endpoint+resource.url.pathname+resource.url.search,token,expires_at:new Date((iat+30)*1000).toISOString()};
}

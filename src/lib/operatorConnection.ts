import {validateReadData,DataIntegrityError} from './dataContracts'
const KEY = 'etgen:operator-connection'
const LOCAL_KEY = 'etgen:local-validation-address'
const DISCONNECTED_KEY = 'etgen:operator-disconnected'
export interface OperatorConnection { url: string; token: string }
let accountAccess = false
export const setAccountConnectionAvailable = (value: boolean) => {accountAccess=value}
export const accountConnectionAvailable = () => accountAccess

function localValidationPage() {
  return ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) && ['/validation', '/selling', '/production'].includes(location.pathname)
}

function loopbackOrigin(value: string) {
  try {const url = new URL(value); return url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) && url.origin === value}
  catch {return false}
}

export function readConnection(): OperatorConnection {
  try {
    const connection = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (connection) return connection
    // Account refresh still clears every operator token. Retain only an explicit
    // loopback address for the standalone local validation page, never credentials.
    const local = sessionStorage.getItem(LOCAL_KEY) || ''
    const installed = localValidationPage() && location.port === '5175' && sessionStorage.getItem(DISCONNECTED_KEY) !== '1'
    return {url: localValidationPage() && loopbackOrigin(local) ? local : installed ? 'http://127.0.0.1:18020' : accountAccess ? location.origin : '', token: ''}
  }
  catch { return {url: '', token: ''} }
}

export function saveConnection(connection: OperatorConnection) {
  const url = new URL(connection.url)
  if (url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) {
    throw new Error('Enter the backend origin, without a path or credentials.')
  }
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
    throw new Error('Use HTTPS for a remote backend.')
  }
  sessionStorage.setItem(KEY, JSON.stringify({url: url.origin, token: connection.token.trim()}))
  sessionStorage.removeItem(DISCONNECTED_KEY)
  if (localValidationPage() && loopbackOrigin(url.origin)) sessionStorage.setItem(LOCAL_KEY, url.origin)
  else sessionStorage.removeItem(LOCAL_KEY)
  if(typeof window!=='undefined'&&typeof window.dispatchEvent==='function')window.dispatchEvent(new Event('etgen:connection-updated'))
}

export function clearConnection(removeLocalAddress = false) {
  sessionStorage.removeItem(KEY)
  if (removeLocalAddress) {sessionStorage.removeItem(LOCAL_KEY); sessionStorage.setItem(DISCONNECTED_KEY, '1')}
  if(typeof window!=='undefined'&&typeof window.dispatchEvent==='function')window.dispatchEvent(new Event('etgen:connection-updated'))
}

export function operatorHeaders(url: string): Record<string, string> {
  const connection = readConnection()
  return connection.url === url && connection.token ? {Authorization: `Bearer ${connection.token}`} : {}
}

export class OperatorError extends Error {
  constructor(message:string,public status:number,public retryable:boolean){super(message);this.name='OperatorError'}
}
const transient=(status:number)=>[408,429,500,502,503,504].includes(status)

async function operatorTransfer<T>(path:string,options:RequestInit,consume:(response:Response)=>Promise<T>):Promise<T>{
  const method=(options.method||'GET').toUpperCase(),read=method==='GET'
  const initial=readConnection()
  if(!initial.url)throw new OperatorError('Connect to your backend first.',0,false)
  const deadline=Date.now()+(read&&!path.includes('/files/')?45000:120000)
  for(let attempt=0;;attempt++){
    const remaining=deadline-Date.now()
    if(options.signal?.aborted)throw options.signal.reason
    try{
      const current=readConnection()
      if(current.url!==initial.url||current.token!==initial.token)throw new OperatorError('The workspace connection changed. Retry in the current account.',0,false)
      const controller=new AbortController()
      const abort=()=>controller.abort(options.signal?.reason)
      options.signal?.addEventListener('abort',abort,{once:true})
      const timer=setTimeout(()=>controller.abort(new DOMException('Connection timed out.','TimeoutError')),Math.max(1,remaining))
      try{
        let target=current.url+path
        let headers:HeadersInit={...operatorHeaders(current.url),...options.headers}
        if(accountAccess&&current.url===location.origin){
          const permission=await fetch('/api/account/backend/access',{method:'POST',credentials:'same-origin',cache:'no-store',
            headers:{'Content-Type':'application/json','X-Etgen-Request':'1'},body:JSON.stringify({path,method}),signal:controller.signal})
          const ticket=await permission.json().catch(()=>({})) as {url?:string;token?:string;error?:string}
          if(!permission.ok||!ticket.url||!ticket.token)throw new OperatorError(ticket.error||'The private connection could not be verified. Reconnecting.',permission.status,(transient(permission.status)||permission.status===409))
          target=ticket.url;headers={...options.headers,Authorization:`Bearer ${ticket.token}`}
        }
        const response=await fetch(target,{...options,headers,cache:'no-store',signal:controller.signal})
        if(read&&transient(response.status)){
          const problem=await response.json().catch(()=>({})) as {detail?:unknown}
          throw new OperatorError(typeof problem.detail==='string'?problem.detail:`The service is temporarily unavailable (${response.status}). Reconnecting.`,response.status,true)
        }
        const result=await consume(response)
        if(read){const latest=readConnection();if(latest.url!==initial.url||latest.token!==initial.token)throw new OperatorError('The workspace connection changed. Retry in the current account.',0,false)}
        return result
      }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort)}
    }catch(error){
      if(options.signal?.aborted)throw error
      const failure=error instanceof DataIntegrityError?new OperatorError(error.message,502,false):error instanceof OperatorError?error:new OperatorError(
        typeof navigator!=='undefined'&&!navigator.onLine?'You are offline. Reconnect to refresh these records.':
        localValidationPage()&&location.port==='5175'?'The local service could not be reached. EtGen will retry automatically.':
        'The private service could not be reached. EtGen will retry automatically.',0,true)
      // Fresh permissions on each read retry. Never replay a write or an auth failure.
      if(!read||!failure.retryable||attempt>=2||deadline-Date.now()<3000)throw failure
      await new Promise(resolve=>setTimeout(resolve,750*2**attempt+Math.random()*250))
    }
  }
}

export const operatorFetch=(path:string,options:RequestInit={})=>operatorTransfer(path,options,async response=>{
 if(path.startsWith('/api/stream'))return response
 // Keep the deadline active through complete JSON/file receipt, including a
 // connection lost after headers. These callers consume the full body anyway.
 const body=response.body===null?null:await response.arrayBuffer()
 return new Response(body,{status:response.status,statusText:response.statusText,headers:response.headers})
})

export async function operatorRequest<T>(path: string, body?: unknown): Promise<T> {
  const result=await operatorTransfer<T>(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)},async response=>{
    if(!response.ok){
      const detail=await response.json().catch(()=>({})) as {detail?:unknown}
      throw new OperatorError(response.status===401?'The backend rejected this session. Reconnect or sign in again.':
        typeof detail.detail==='string'?detail.detail:`Backend request failed (${response.status}).`,response.status,false)
    }
    let data:T
    try{data=await response.json() as T}catch(error){
      if(error instanceof SyntaxError)throw new DataIntegrityError('The service returned an incomplete response. Previously loaded records have been retained.')
      throw error
    }
    if(body===undefined)validateReadData(path,data)
    return data
  })
  if(body!==undefined&&typeof window!=='undefined'&&typeof window.dispatchEvent==='function')window.dispatchEvent(new CustomEvent('etgen:research-updated',{detail:path}))
  return result
}

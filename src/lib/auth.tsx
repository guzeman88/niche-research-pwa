import {createContext, useCallback, useContext, useEffect, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {Link, Navigate, useLocation} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {accountRequest, AccountError} from './accountApi'
import {activateWorkspace, clearAccountWorkspace, flushAccountWorkspace, hasInterruptedEdits, subscribeWorkspace, workspaceStatus} from './accountWorkspace'
import {clearConnection, setAccountConnectionAvailable} from './operatorConnection'
import {hydrateStartupCache,persistStartupCache,purgeStartupCache,startupDisplay} from './startupCache'
import type {DashboardSummary} from '../types/api'
import type {StartupSummary} from './startup'

export interface Profile {id:string; display_name:string; business_name:string; timezone:string; currency:string; role:'admin'|'member'; created_at:string}
export interface AccountSession {user:{id:string;email:string}|null;profile?:Profile|null;mfa_required?:boolean;recovery?:boolean;factors?:Array<{id:string;friendly_name?:string}>}
export interface AccountBootstrap extends AccountSession {workspace?:{payload:Record<string,unknown>;revision:number};dashboard?:DashboardSummary;startup?:StartupSummary}
interface AuthState extends AccountSession {loading:boolean;error:string;refresh:(restart?:boolean)=>Promise<void>;establish:(next:AccountBootstrap)=>Promise<void>;logout:(all?:boolean)=>Promise<void>}
const AuthContext = createContext<AuthState|null>(null)
export const useAuth = () => {const value=useContext(AuthContext);if(!value)throw new Error('Missing account provider');return value}

export function AuthProvider({children}:{children:ReactNode}) {
  const client = useQueryClient()
  const [session,setSession] = useState<AccountSession>({user:null})
  const [loading,setLoading] = useState(true), [error,setError] = useState('')
  const accountId = useRef('')
  const role=useRef(''),generation=useRef(0),inFlight=useRef<Promise<void>|null>(null)
  const accountCheck=useRef<AbortController|null>(null)
  const clear = useCallback(() => {generation.current++;accountCheck.current?.abort();accountId.current='';role.current='';purgeStartupCache();clearAccountWorkspace();client.clear();setSession({user:null});setLoading(false);clearConnection();setAccountConnectionAvailable(false)},[client])
  const accept=useCallback(async(next:AccountBootstrap,expected:number,signal?:AbortSignal)=>{
    if(expected!==generation.current)return
    if(!next.user){clear();return}
    const allowed=!next.mfa_required&&!next.recovery, nextRole=allowed?next.profile?.role||'':''
    if(accountId.current!==next.user.id||role.current!==nextRole){
      clearAccountWorkspace();client.clear();clearConnection();setAccountConnectionAvailable(false)
      accountId.current=next.user.id;role.current=nextRole
      if(allowed)hydrateStartupCache(client,next.user.id,nextRole)
      else purgeStartupCache()
    }
    if(allowed&&workspaceStatus().owner!==next.user.id){
      const workspace=next.workspace||await accountRequest<{payload:Record<string,unknown>;revision:number}>('/workspace',undefined,{signal})
      if(expected!==generation.current)return
      activateWorkspace(next.user.id,workspace.payload,workspace.revision)
    }
    if(expected!==generation.current)return
    if(allowed&&nextRole==='admin'){
      const seed=(key:string,data:{generated_at:string}|undefined)=>{if(data){const at=Date.parse(data.generated_at);const old=client.getQueryData<{generated_at:string}>([key]);if(Number.isFinite(at)&&at<=Date.now()+5000&&(!old||at>=Date.parse(old.generated_at)))client.setQueryData([key],data,{updatedAt:at})}}
      seed('startup',startupDisplay(next.startup));seed('dashboard-summary',next.dashboard)
      persistStartupCache(client,next.user.id,nextRole)
    }
    setAccountConnectionAvailable(allowed&&nextRole==='admin'&&!['localhost','127.0.0.1','[::1]'].includes(location.hostname))
    setSession(next);setError('')
  },[clear,client])
  const establish=useCallback(async(next:AccountBootstrap)=>{const expected=++generation.current;accountCheck.current?.abort();try{await accept(next,expected)}finally{if(expected===generation.current)setLoading(false)}},[accept])
  const refresh = useCallback((restart=false) => {
    if(inFlight.current&&!restart)return inFlight.current
    if(restart){generation.current++;accountCheck.current?.abort();setError('');setLoading(true)}
    const expected=generation.current
    const controller=new AbortController();accountCheck.current=controller
    // Bound the entire restore, including a missing workspace, rather than
    // allowing consecutive account requests to each consume their own timeout.
    const deadline=setTimeout(()=>controller.abort(new DOMException('Account check timed out','TimeoutError')),15000)
    const task=(async()=>{
    try {
      const next=await accountRequest<AccountBootstrap>('/bootstrap'+(workspaceStatus().owner?'?workspace=0':''),undefined,{signal:controller.signal})
      await accept(next,expected,controller.signal)
    } catch (error) {
      if(expected!==generation.current)return
      if (error instanceof AccountError && [401,403].includes(error.status)) clear()
      setError(error instanceof Error ? error.message : 'Unable to load your account.')
    } finally {clearTimeout(deadline);if(accountCheck.current===controller)accountCheck.current=null;if(expected===generation.current)setLoading(false)}
    })()
    inFlight.current=task;void task.finally(()=>{if(inFlight.current===task)inFlight.current=null})
    return task
  },[clear,accept])
  const logout = async (all=false) => {
    generation.current++;accountCheck.current?.abort();inFlight.current=null
    // Saving problems must not prevent a user from revoking their session.
    await flushAccountWorkspace().catch(()=>{})
    await accountRequest('/logout',{all}); clear()
    const channel=new BroadcastChannel('etgen-account');channel.postMessage('logout');channel.close()
  }
  useEffect(()=>{clearConnection();void refresh();const timer=setInterval(()=>void refresh(),60000);return()=>clearInterval(timer)},[refresh])
  useEffect(()=>{
    if(!session.user||session.mfa_required||session.recovery||session.profile?.role!=='admin')return
    const connection=(navigator as Navigator&{connection?:{saveData?:boolean;effectiveType?:string}}).connection
    if(connection?.saveData||['slow-2g','2g'].includes(connection?.effectiveType||''))return
    // Download likely next screens after login settles; imports never mount their
    // heavy evidence/provider queries and are skipped on constrained connections.
    const timer=setTimeout(()=>{void Promise.allSettled([import('../pages/Production'),import('../pages/ProductValidation')])},2000)
    return()=>clearTimeout(timer)
  },[session.user,session.profile?.role,session.mfa_required,session.recovery])
  useEffect(()=>{
    return client.getQueryCache().subscribe(event=>{
      if(event.type==='updated'&&accountId.current&&role.current==='admin'&&['startup','dashboard-summary'].includes(String(event.query.queryKey[0])))persistStartupCache(client,accountId.current,role.current)
    })
  },[client])
  useEffect(()=>{
    const channel=new BroadcastChannel('etgen-account');channel.onmessage=()=>{clear();void refresh()}
    const focus=()=>void refresh();window.addEventListener('focus',focus)
    return()=>{channel.close();window.removeEventListener('focus',focus)}
  },[clear,refresh])
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>
    const unsubscribe=subscribeWorkspace(()=>{clearTimeout(timer);const state=workspaceStatus();if(state.dirty&&!state.saving&&!state.error)timer=setTimeout(()=>void flushAccountWorkspace().catch(()=>{}),750)})
    const unload=(e:BeforeUnloadEvent)=>{if(workspaceStatus().dirty || hasInterruptedEdits()){e.preventDefault();e.returnValue=''}}
    window.addEventListener('beforeunload',unload)
    return()=>{clearTimeout(timer);unsubscribe();window.removeEventListener('beforeunload',unload)}
  },[])
  return <AuthContext.Provider value={{...session,loading,error,refresh,establish,logout}}>{children}</AuthContext.Provider>
}

export function RequireAccount({children}:{children:ReactNode}) {
  const auth=useAuth(), location=useLocation()
  const [slow,setSlow]=useState(false)
  useEffect(()=>{if(!auth.loading)return;const timer=setTimeout(()=>setSlow(true),5000);return()=>clearTimeout(timer)},[auth.loading])
  if(auth.loading)return <div className="page max-w-xl" aria-busy="true"><div className="panel p-6"><p role="status">Loading your account…</p>{slow&&<button type="button" className="btn-secondary mt-4" onClick={()=>void auth.refresh(true)}>Retry connection</button>}</div></div>
  if(!auth.user&&auth.error)return <div className="page max-w-xl"><div className="panel p-6"><h1 className="text-lg font-semibold">Account connection interrupted</h1><p className="mt-3" role="alert">{auth.error}</p><div className="mt-4 flex flex-wrap items-center gap-4"><button type="button" className="btn-secondary" onClick={()=>void auth.refresh(true)}>Retry connection</button><Link to="/signin">Sign in</Link></div></div></div>
  if(!auth.user)return <Navigate to="/signin" replace state={{from:location.pathname}}/>
  if(auth.mfa_required)return <Navigate to="/signin?mode=mfa" replace/>
  if(auth.recovery && location.pathname !== '/account')return <Navigate to="/account" replace/>
  return children
}

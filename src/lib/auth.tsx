import {createContext, useCallback, useContext, useEffect, useRef, useState} from 'react'
import type {ReactNode} from 'react'
import {Navigate, useLocation} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {accountRequest, AccountError} from './accountApi'
import {activateWorkspace, clearAccountWorkspace, flushAccountWorkspace, hasInterruptedEdits, subscribeWorkspace, workspaceStatus} from './accountWorkspace'
import {clearConnection} from './operatorConnection'

export interface Profile {id:string; display_name:string; business_name:string; timezone:string; currency:string; role:'admin'|'member'; created_at:string}
export interface AccountSession {user:{id:string;email:string}|null;profile?:Profile|null;mfa_required?:boolean;recovery?:boolean;factors?:Array<{id:string;friendly_name?:string}>}
interface AuthState extends AccountSession {loading:boolean;error:string;refresh:()=>Promise<void>;logout:(all?:boolean)=>Promise<void>}
const AuthContext = createContext<AuthState|null>(null)
export const useAuth = () => {const value=useContext(AuthContext);if(!value)throw new Error('Missing account provider');return value}

export function AuthProvider({children}:{children:ReactNode}) {
  const client = useQueryClient()
  const [session,setSession] = useState<AccountSession>({user:null})
  const [loading,setLoading] = useState(true), [error,setError] = useState('')
  const accountId = useRef('')
  const clear = useCallback(() => {accountId.current=''; clearAccountWorkspace(); client.clear(); setSession({user:null}); clearConnection()},[client])
  const refresh = useCallback(async () => {
    try {
      const next = await accountRequest<AccountSession>('/session')
      if (!next.user) clear()
      else {
        if (accountId.current !== next.user.id) {clear(); accountId.current=next.user.id}
        if (!next.mfa_required && !next.recovery && workspaceStatus().owner !== next.user.id) {
          const workspace = await accountRequest<{payload:Record<string,unknown>;revision:number}>('/workspace')
          activateWorkspace(next.user.id,workspace.payload,workspace.revision)
          client.clear()
        }
        setSession(next)
      }
      setError('')
    } catch (error) {
      if (error instanceof AccountError && [401,403].includes(error.status)) clear()
      setError(error instanceof Error ? error.message : 'Unable to load your account.')
    } finally {setLoading(false)}
  },[clear,client])
  const logout = async (all=false) => {
    // Saving problems must not prevent a user from revoking their session.
    await flushAccountWorkspace().catch(()=>{})
    await accountRequest('/logout',{all}); clear()
    const channel=new BroadcastChannel('etgen-account');channel.postMessage('logout');channel.close()
  }
  useEffect(()=>{clearConnection();void refresh();const timer=setInterval(()=>void refresh(),60000);return()=>clearInterval(timer)},[refresh])
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
  return <AuthContext.Provider value={{...session,loading,error,refresh,logout}}>{children}</AuthContext.Provider>
}

export function RequireAccount({children}:{children:ReactNode}) {
  const auth=useAuth(), location=useLocation()
  if(auth.loading)return <div className="page max-w-xl" aria-busy="true"><div className="panel p-6"><p role="status">Loading your account…</p></div></div>
  if(!auth.user)return <Navigate to="/signin" replace state={{from:location.pathname}}/>
  if(auth.mfa_required)return <Navigate to="/signin?mode=mfa" replace/>
  if(auth.recovery && location.pathname !== '/account')return <Navigate to="/account" replace/>
  return children
}

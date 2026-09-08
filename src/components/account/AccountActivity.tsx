import {useEffect,useState} from 'react'
import {accountRequest} from '../../lib/accountApi'
import {useAuth} from '../../lib/auth'
interface Device {id:string;device:string;created_at:string;last_seen_at:string;current:boolean}
interface Event {id:number;event:string;created_at:string}
export default function AccountActivity(){
  const auth=useAuth(),[devices,setDevices]=useState<Device[]>([]),[events,setEvents]=useState<Event[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true)
  async function load(){const [d,e]=await Promise.all([accountRequest<Device[]>('/sessions'),accountRequest<Event[]>('/events')]);setDevices(d);setEvents(e)}
  useEffect(()=>{void load().catch(e=>setError(e.message)).finally(()=>setLoading(false))},[])
  async function revoke(id:string){setBusy(true);setError('');try{await accountRequest('/sessions/revoke',{id});await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="space-y-8">
    <section className="space-y-4"><h2 className="text-lg font-semibold">Signed-in devices</h2><p className="text-sm text-surface-200">Sessions expire after 12 hours of inactivity or seven days. Revoke access for a device you no longer use.</p>
      <div aria-busy={loading}>{loading&&<p role="status" className="text-sm text-surface-200">Loading signed-in devices…</p>}<ul className="divide-y divide-surface-600">{devices.map(d=><li key={d.id} className="py-4 space-y-2"><p className="text-sm font-semibold">{d.current?'This device':'Other device'}</p><p className="break-words text-xs text-surface-200">{d.device}</p><div className="flex flex-wrap items-center gap-3 text-xs text-surface-300"><span>Last active {new Date(d.last_seen_at).toLocaleString()}</span>{!d.current&&<button className="btn-secondary" disabled={busy} onClick={()=>void revoke(d.id)}>Sign out device</button>}</div></li>)}</ul></div>
      <button className="btn-secondary" disabled={busy} onClick={()=>{setBusy(true);void auth.logout(true).catch(e=>setError(e.message)).finally(()=>setBusy(false))}}>Sign out everywhere</button>
    </section>
    <section className="border-t border-surface-600 pt-6"><h2 className="text-lg font-semibold mb-4">Recent account activity</h2>{events.length?<ul className="divide-y divide-surface-600">{events.map(e=><li key={e.id} className="py-3 flex flex-wrap justify-between gap-2 text-sm"><span>{e.event.replace(/_/g,' ')}</span><time className="text-xs text-surface-300" dateTime={e.created_at}>{new Date(e.created_at).toLocaleString()}</time></li>)}</ul>:<p className="text-sm text-surface-200">Account events will appear here as you use your account.</p>}</section>
    {error&&<p role="alert" className="text-sm text-red-200">{error}</p>}
  </div>
}

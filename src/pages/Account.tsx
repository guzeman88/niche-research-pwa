import {useState} from 'react'
import {useAuth} from '../lib/auth'
import {accountRequest} from '../lib/accountApi'
import AccountSecurity from '../components/account/AccountSecurity'
import AccountActivity from '../components/account/AccountActivity'

export default function Account(){
  const auth=useAuth(),profile=auth.profile
  const [tab,setTab]=useState('profile'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const [fields,setFields]=useState({display_name:profile?.display_name||'',business_name:profile?.business_name||'',timezone:profile?.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone,currency:profile?.currency||'USD'})
  const [inviteEmail,setInviteEmail]=useState(''),[inviteLink,setInviteLink]=useState('')
  const active=auth.recovery?'security':tab
  async function run(action:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await action()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="page max-w-3xl">
    <header className="page-header flex flex-wrap justify-between gap-4 items-start"><div><h1 className="text-xl font-bold">Account & profile</h1><p className="mt-2 text-sm text-surface-200">Manage your details, security, and signed-in devices.</p></div><button className="btn-secondary" disabled={busy} onClick={()=>void run(()=>auth.logout())}>Sign out</button></header>
    <div className="flex items-center gap-4 my-6"><span aria-hidden="true" className="flex items-center justify-center h-12 w-12 shrink-0 rounded-lg bg-primary-400/20 text-primary-100 text-lg font-bold">{(profile?.display_name||auth.user?.email||'E').slice(0,2).toUpperCase()}</span><div className="min-w-0"><p className="font-semibold truncate">{profile?.display_name||'Finish your profile'}</p><p className="text-sm text-surface-200 break-all">{auth.user?.email}</p><p className="text-xs text-surface-300 mt-1">Verified email · {profile?.role==='admin'?'Administrator':'Member'}</p></div></div>
    {!auth.recovery&&<nav className="flex gap-2 border-b border-surface-600 pb-3 mb-6" aria-label="Account sections">{['profile','security','activity'].map(t=><button key={t} className={active===t?'btn-primary text-surface-950':'btn-secondary'} aria-current={active===t?'page':undefined} onClick={()=>{setTab(t);setError('');setMessage('')}}>{t[0].toUpperCase()+t.slice(1)}</button>)}</nav>}
    <div className="panel p-5 sm:p-6">
      {active==='profile'&&<div className="space-y-8"><section><h2 className="text-lg font-semibold">Your details</h2><p className="text-sm text-surface-200 mt-2">These details belong to your EtGen account. Store branding is managed inside each store.</p>
        <form className="space-y-5 mt-6" onSubmit={e=>{e.preventDefault();void run(async()=>{await accountRequest('/profile',fields);await auth.refresh();setMessage('Profile saved.')})}}>
          <div><label className="block text-sm mb-2" htmlFor="display-name">Display name</label><input className="input w-full" id="display-name" autoComplete="name" maxLength={80} required value={fields.display_name} onChange={e=>setFields({...fields,display_name:e.target.value})}/></div>
          <div><label className="block text-sm mb-2" htmlFor="business-name">Business name <span className="text-surface-300">(optional)</span></label><input className="input w-full" id="business-name" autoComplete="organization" maxLength={120} value={fields.business_name} onChange={e=>setFields({...fields,business_name:e.target.value})}/></div>
          <div className="grid sm:grid-cols-2 gap-5"><div><label className="block text-sm mb-2" htmlFor="profile-timezone">Time zone</label><input className="input w-full" id="profile-timezone" list="timezones" required value={fields.timezone} onChange={e=>setFields({...fields,timezone:e.target.value})}/><datalist id="timezones">{['America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Toronto','Europe/London','Europe/Paris','Australia/Sydney','UTC'].map(z=><option key={z} value={z}/>)}</datalist></div>
            <div><label className="block text-sm mb-2" htmlFor="profile-currency">Preferred currency</label><select className="input w-full" id="profile-currency" value={fields.currency} onChange={e=>setFields({...fields,currency:e.target.value})}>{['USD','CAD','GBP','EUR','AUD'].map(c=><option key={c}>{c}</option>)}</select><p className="text-xs text-surface-300 mt-2">Stores keep their configured prices; this preference does not convert amounts.</p></div></div>
          <button className="btn-primary text-surface-950" disabled={busy}>{busy?'Saving…':'Save profile'}</button>
        </form></section>
        {profile?.role==='admin'&&<section className="border-t border-surface-600 pt-6 space-y-4"><h2 className="text-lg font-semibold">Invite a member</h2><p className="text-sm text-surface-200">Approve an email address for registration. Members get separate private workspaces and cannot access your administrator controls.</p><form className="space-y-3" onSubmit={e=>{e.preventDefault();void run(async()=>{const result=await accountRequest<{url:string;message:string}>('/invites',{email:inviteEmail});setInviteLink(result.url);setMessage(result.message);setInviteEmail('')})}}><label htmlFor="invite-email" className="block text-sm">Member email</label><input className="input w-full" type="email" id="invite-email" required value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)}/><button className="btn-secondary" disabled={busy}>Approve invitation</button></form>{inviteLink&&<div className="text-sm space-y-2"><p>Share this registration link with the approved person:</p><a className="text-primary-200 break-all" href={inviteLink}>{inviteLink}</a></div>}</section>}
      </div>}
      {active==='security'&&<AccountSecurity/>}{active==='activity'&&<AccountActivity/>}
    </div>
    {message&&<p role="status" className="mt-4 text-sm">{message}</p>}{error&&<p role="alert" className="mt-4 text-sm text-red-200">{error}</p>}
  </div>
}

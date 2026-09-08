import {useState} from 'react'
import {useNavigate} from 'react-router-dom'
import {useAuth} from '../../lib/auth'
import {accountRequest} from '../../lib/accountApi'
import {flushAccountWorkspace} from '../../lib/accountWorkspace'

export default function AccountSecurity(){
  const auth=useAuth(),navigate=useNavigate()
  const [current,setCurrent]=useState(''),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState('')
  const [enrollment,setEnrollment]=useState<{id:string;totp:{qr_code:string;secret:string}}|null>(null),[code,setCode]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  async function run(action:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await action()}catch(e){setError(e instanceof Error?e.message:'Unable to complete this action.')}finally{setBusy(false)}}
  const factor=auth.factors?.[0]
  return <div className="space-y-8">
    <section aria-labelledby="password-title" className="space-y-4">
      <h2 id="password-title" className="text-lg font-semibold">{auth.recovery?'Choose your password':'Change password'}</h2>
      <p className="text-sm text-surface-200">Use a unique password of at least 12 characters. Changing it signs you out on every device.</p>
      <form className="space-y-4 max-w-md" onSubmit={e=>{e.preventDefault();void run(async()=>{
        if(password!==confirmation)throw new Error('The new passwords do not match.')
        await flushAccountWorkspace();await accountRequest('/password',{current_password:current,password});await auth.refresh();navigate('/signin',{replace:true})
      })}}>
        {!auth.recovery&&<div><label htmlFor="current-password" className="block text-sm mb-2">Current password</label><input id="current-password" className="input w-full" type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/></div>}
        <div><label htmlFor="new-password" className="block text-sm mb-2">New password</label><input id="new-password" className="input w-full" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={e=>setPassword(e.target.value)}/></div>
        <div><label htmlFor="confirm-password" className="block text-sm mb-2">Confirm new password</label><input id="confirm-password" className="input w-full" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></div>
        <button className="btn-primary text-surface-950" disabled={busy}>{busy?'Please wait…':'Save password and sign out'}</button>
      </form>
    </section>
    {!auth.recovery&&<section className="border-t border-surface-600 pt-6 space-y-4" aria-labelledby="mfa-title">
      <h2 id="mfa-title" className="text-lg font-semibold">Two-factor authentication</h2>
      <p className="text-sm text-surface-200">{factor?'An authenticator protects your account. New sign-ins require its six-digit code.':'Add an authenticator app for a second check when you sign in.'}</p>
      {!factor&&!enrollment&&<button className="btn-secondary" disabled={busy} onClick={()=>void run(async()=>{setEnrollment(await accountRequest('/mfa/enroll',{}))})}>Set up authenticator</button>}
      {enrollment&&<div className="space-y-4 max-w-md">
        <p className="text-sm">Scan this code in your authenticator, then enter the code it generates.</p>
        <img alt="Scan this QR code with your authenticator app" className="w-52 h-52 bg-white p-2 rounded-lg" src={enrollment.totp.qr_code.startsWith('data:')?enrollment.totp.qr_code:`data:image/svg+xml,${encodeURIComponent(enrollment.totp.qr_code)}`}/>
        <details className="text-sm"><summary className="cursor-pointer">Can’t scan the code?</summary><p className="mt-2 break-all font-mono">{enrollment.totp.secret}</p></details>
        <p className="text-xs text-surface-300">Keep your authenticator backed up. Account recovery after losing it requires administrator assistance.</p>
        <form className="space-y-3" onSubmit={e=>{e.preventDefault();void run(async()=>{await accountRequest('/mfa/verify',{factor_id:enrollment.id,code});setEnrollment(null);setCode('');await auth.refresh();setMessage('Two-factor authentication is enabled.')})}}>
          <label htmlFor="enroll-code" className="block text-sm">Six-digit code</label><input id="enroll-code" className="input w-full" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,''))}/>
          <button className="btn-primary text-surface-950" disabled={busy}>Verify and enable</button>
        </form>
      </div>}
      {factor&&<details className="text-sm"><summary className="cursor-pointer text-surface-200">Remove authenticator</summary><form className="mt-4 space-y-3 max-w-md" onSubmit={e=>{e.preventDefault();void run(async()=>{await accountRequest('/mfa/verify',{factor_id:factor.id,code});await accountRequest('/mfa/remove',{factor_id:factor.id,current_password:current});setCurrent('');setCode('');await auth.refresh();setMessage('Authenticator removed.')})}}>
        <p>Confirm your password and a current authenticator code.</p><label htmlFor="remove-password" className="block">Current password</label><input id="remove-password" className="input w-full" type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/>
        <label htmlFor="remove-code" className="block">Authenticator code</label><input id="remove-code" className="input w-full" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required value={code} onChange={e=>setCode(e.target.value)}/>
        <button className="btn-secondary" disabled={busy}>Remove authenticator</button>
      </form></details>}
    </section>}
    {message&&<p role="status" className="text-sm">{message}</p>}{error&&<p role="alert" className="text-sm text-red-200">{error}</p>}
  </div>
}

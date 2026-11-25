import {useState} from 'react'
import {Link, Navigate, useSearchParams} from 'react-router-dom'
import BrandLogo from '../components/BrandLogo'
import {useAuth} from '../lib/auth'
import type {AccountBootstrap} from '../lib/auth'
import {accountRequest} from '../lib/accountApi'

export default function SignIn() {
  const auth=useAuth(), [params,setParams]=useSearchParams()
  const mode=auth.mfa_required ? 'mfa' : ['signup','recover','email'].includes(params.get('mode') || '') ? params.get('mode')! : 'login'
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[code,setCode]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  if(auth.user&&!auth.mfa_required)return <Navigate to={auth.recovery || !auth.profile?.display_name ? '/account' : '/'} replace/>
  const titles:Record<string,string>={login:'Welcome back',signup:'Create your account',recover:'Reset your password',email:'Sign in with email',mfa:'Verify it’s you'}
  async function submit(e:React.FormEvent) {
    e.preventDefault();if(busy||auth.loading)return;setBusy(true);setError('');setMessage('')
    const values=new FormData(e.currentTarget as HTMLFormElement)
    const submittedEmail=String(values.get('email')||'').trim(),submittedPassword=String(values.get('password')||''),submittedCode=String(values.get('code')||'')
    setEmail(submittedEmail);setPassword(submittedPassword);setCode(submittedCode)
    try {
      if(mode==='mfa'){await accountRequest('/mfa/verify',{factor_id:auth.factors?.[0]?.id,code:submittedCode});await auth.refresh()}
      else {const result=await accountRequest<AccountBootstrap&{message?:string}>(`/${mode}`,{email:submittedEmail,password:submittedPassword});if(mode==='login')await auth.establish(result);else setMessage(result.message || 'Check your email for the next step.')}
      setPassword('');setCode('')
    } catch(error){setError(error instanceof Error ? error.message : 'Unable to continue.')}finally{setBusy(false)}
  }
  function invalid(e:React.FormEvent<HTMLFormElement>) {
    const field=e.target as HTMLInputElement
    if(field.form?.querySelector(':invalid')!==field)return
    setMessage('')
    setError(field.name==='email'?(field.validity.valueMissing?'Enter your email address.':'Enter a valid email address.'):field.name==='code'?'Enter the six-digit authenticator code.':field.validity.valueMissing?'Enter your password.':'Use a password between 12 and 128 characters.')
  }
  function switchMode(next:string){setParams(next==='login'?{}:{mode:next});setError('');setMessage('');setPassword('')}
  return <main className="account-signin min-h-screen bg-surface-950 px-4 py-10 sm:py-16">
    <div className="mx-auto max-w-md">
      <BrandLogo subtitle="Your research. Your stores."/>
      <section className="panel mt-8 p-6 sm:p-8">
        <h1 className="text-2xl font-bold text-surface-50">{titles[mode]}</h1>
        <p className="mt-3 text-sm leading-6 text-surface-200">{mode==='signup'?'EtGen is invite-only. Use the email address your administrator approved.':mode==='recover'?'We’ll email you a secure link to choose a new password.':mode==='email'?'Use your approved email address. We’ll send a sign-in link—no password needed. Open it in this browser.':mode==='mfa'?'Enter the six-digit code from your authenticator app.':'Sign in to access your private stores, products, and workspace.'}</p>
        <form className="mt-6 space-y-5" onSubmit={submit} aria-busy={busy||auth.loading} onInvalidCapture={invalid}>
          {mode==='mfa'?<div><label className="block text-sm mb-2" htmlFor="auth-code">Authenticator code</label><input id="auth-code" name="code" className="input w-full" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,''))}/></div>:<>
            <div><label className="block text-sm mb-2" htmlFor="auth-email">Email address</label><input id="auth-email" name="email" className="input w-full" type="email" autoComplete="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></div>
            {!['recover','email'].includes(mode)&&<div><label className="block text-sm mb-2" htmlFor="auth-password">Password</label><input id="auth-password" name="password" className="input w-full" type="password" autoComplete={mode==='signup'?'new-password':'current-password'} minLength={mode==='signup'?12:1} maxLength={128} required value={password} onChange={e=>setPassword(e.target.value)}/>{mode==='signup'&&<p className="text-xs text-surface-300 mt-2">Use at least 12 characters. A unique passphrase works well.</p>}</div>}
          </>}
          <button type="submit" className="btn-primary text-surface-950 w-full" disabled={busy||auth.loading}>{busy?'Please wait…':auth.loading?'Checking account…':mode==='signup'?'Create account':mode==='recover'?'Send reset link':mode==='email'?'Email me a sign-in link':mode==='mfa'?'Verify code':'Sign in'}</button>
        </form>
        {(error||auth.error)&&<p className="mt-4 text-sm text-red-200" role="alert">{error||auth.error}</p>}
        {message&&<p className="mt-4 text-sm text-surface-100" role="status">{message}</p>}
        <div className="mt-6 border-t border-surface-600 pt-5 flex flex-wrap gap-x-5 gap-y-3 text-sm">
          {mode==='login'?<><button onClick={()=>switchMode('email')} className="text-primary-200">Sign in with an email link</button><button onClick={()=>switchMode('recover')} className="text-primary-200">Forgot password?</button><button onClick={()=>switchMode('signup')} className="text-surface-100">Have an invitation?</button></>:mode==='mfa'?<button onClick={()=>void auth.logout().catch(e=>setError(e.message))}>Use a different account</button>:<button onClick={()=>switchMode('login')} className="text-primary-200">Back to sign in</button>}
        </div>
      </section>
      <p className="mt-6 text-xs leading-5 text-surface-300">Signing in connects you to EtGen. You can connect an Etsy shop separately when you’re ready.</p>
      <Link to="/api-application" className="inline-block mt-4 text-xs text-surface-200">About EtGen</Link>
    </div>
  </main>
}

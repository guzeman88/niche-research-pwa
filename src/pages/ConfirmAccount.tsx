import {useEffect,useRef,useState} from 'react'
import {Link,useNavigate} from 'react-router-dom'
import {accountRequest} from '../lib/accountApi'
import {useAuth} from '../lib/auth'

export default function ConfirmAccount(){
  const [link]=useState(()=>{const p=new URLSearchParams(window.location.search);return {token_hash:p.get('token_hash'),type:p.get('type')}})
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  const auth=useAuth(),navigate=useNavigate(),submitted=useRef(false)
  useEffect(()=>{window.history.replaceState(null,'','/auth/confirm')},[])
  async function confirm(){
    if(submitted.current)return;submitted.current=true;setBusy(true)
    try{await accountRequest('/confirm',link);await auth.refresh();navigate('/account',{replace:true})}
    catch(e){setError(e instanceof Error?e.message:'Unable to verify this link.');submitted.current=false}finally{setBusy(false)}
  }
  return <main className="page max-w-lg mx-auto pt-12"><section className="panel p-6 space-y-5">
    <h1 className="text-xl font-bold">Confirm your account</h1>
    <p className="text-sm text-surface-200">Continue to verify this email link. If you requested a password reset, you’ll choose a new password next.</p>
    {link.token_hash?<button className="btn-primary text-surface-950" disabled={busy} onClick={()=>void confirm()}>{busy?'Verifying…':'Continue securely'}</button>:<p role="alert" className="text-sm text-red-200">This link is incomplete. Request a new verification or recovery email.</p>}
    {error&&<p role="alert" className="text-sm text-red-200">{error}</p>}
    <Link className="block text-sm text-primary-200" to="/signin">Back to sign in</Link>
  </section></main>
}

import {createHash, randomBytes} from 'node:crypto';
import {seal, unseal, ValidationError} from './account-security.mjs';

const lifetime = 3600;
const name = origin => origin.startsWith('https:') ? '__Host-etgen-email' : 'etgen-email';
export function emailFlowCookie(value, origin, clear = false) {
  return `${name(origin)}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${clear ? 0 : lifetime}${origin.startsWith('https:') ? '; Secure' : ''}`;
}
export function createEmailFlow(email, intent, secret, origin) {
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const value = seal({email, intent, verifier, expires:Date.now() + lifetime * 1000}, secret, `email:${origin}`);
  return {challenge, cookie:emailFlowCookie(value, origin)};
}
export function readEmailFlow(request, secret, origin) {
  const value = (request.headers.get('cookie') || '').split(';').map(s=>s.trim()).find(s=>s.startsWith(name(origin)+'='))?.slice(name(origin).length+1);
  try {
    const flow = unseal(value || '', secret, `email:${origin}`);
    if (flow.expires <= Date.now() || !['signup','recover','email'].includes(flow.intent) || !/^[A-Za-z0-9_-]{43}$/.test(flow.verifier)) throw new Error();
    return flow;
  } catch { throw new ValidationError('Open the latest email link in the browser where you requested it. If it has expired, request a new link.'); }
}
export function emailRecipientAllowed(email) {
  if (process.env.ACCOUNT_EMAIL_MODE !== 'team-only') return true;
  return (process.env.ACCOUNT_EMAIL_ALLOWED_RECIPIENTS || '').split(',').map(s=>s.trim().toLowerCase()).filter(Boolean).includes(email);
}

// Standard Supabase emails return a short-lived code. Only the initiating
// browser's encrypted HttpOnly cookie can exchange it for a server-side session.
export async function authEmailRequest(url, key, path, body) {
  const response = await fetch(`${url}/auth/v1/${path}`, {
    method:'POST', headers:{apikey:key, 'Content-Type':'application/json'},
    body:JSON.stringify(body), signal:AbortSignal.timeout(12000),
  });
  const data = await response.json();
  return {ok:response.ok, status:response.status, data};
}

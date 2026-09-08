import { createClient } from '@supabase/supabase-js';
import { randomBytes } from 'node:crypto';
import { ValidationError, hash, seal, unseal, trustedMutation, validatePassword, validateProfile, validateWorkspace, sessionCookie, readSessionCookie } from './lib/account-security.mjs';

const options = {global:{fetch:(input, init = {}) => fetch(input, {...init, signal: init.signal ? AbortSignal.any([init.signal,AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000)})},auth:{persistSession:false, autoRefreshToken:false, detectSessionInUrl:false}};
class Failure extends Error { constructor(status, message) { super(message); this.status = status; } }
function required(value, label) { if (!value) throw new Failure(503, `${label} is not configured.`); return value; }
function check(result) { if (result.error) throw new Failure(['40001','PT409'].includes(result.error.code) ? 409 : 400, ['40001','PT409'].includes(result.error.code) ? 'This workspace changed on another device. Download your current work before reloading.' : result.error.message); return result.data; }
const verifiedFactors = user => (user.factors || []).filter(f => f.status === 'verified');
const assurance = token => { try { return JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).aal; } catch { return ''; } };

export default async function handler(request, context = {}) {
  const origin = process.env.APP_ORIGIN || 'https://etsy-niches.netlify.app';
  const headers = {'Content-Type':'application/json', 'Cache-Control':'private, no-store', 'Pragma':'no-cache', 'Vary':'Cookie', 'X-Content-Type-Options':'nosniff'};
  const response = (data, status = 200) => new Response(JSON.stringify(data), {status, headers});
  try {
    const url = new URL(request.url);
    const route = url.pathname.replace(/^\/(?:api\/account|\.netlify\/functions\/account)/, '') || '/session';
    if (!['GET','POST'].includes(request.method)) throw new Failure(405, 'Method not allowed.');
    if (request.method === 'POST' && !trustedMutation(request, origin)) throw new Failure(403, 'Request origin could not be verified.');
    if (Number(request.headers.get('content-length') || 0) > 4.5 * 1024 * 1024) throw new Failure(413, 'Request is too large.');
    const text = request.method === 'POST' ? await request.text() : '{}';
    if (Buffer.byteLength(text) > 4.5 * 1024 * 1024) throw new Failure(413, 'Request is too large.');
    let body; try { body = JSON.parse(text); } catch { throw new Failure(400, 'Invalid request.'); }
    const supabaseUrl = required(process.env.SUPABASE_URL, 'Account service');
    const anonKey = required(process.env.SUPABASE_ANON_KEY, 'Account public key');
    const secret = required(process.env.AUTH_COOKIE_SECRET, 'Account encryption');
    const service = createClient(supabaseUrl, required(process.env.SUPABASE_SERVICE_ROLE_KEY, 'Account service key'), options);
    const auth = createClient(supabaseUrl, anonKey, options);
    const audit = async (userId, event) => { check(await service.from('app_security_events').insert({user_id:userId, event})); };
    const limit = async (key, max = 20, window = 900) => {
      const allowed = check(await service.rpc('app_consume_auth_limit', {bucket_key:hash(key), max_attempts:max, window_seconds:window}));
      if (!allowed) throw new Failure(429, 'Too many attempts. Please wait before trying again.');
    };
    if (request.method === 'POST') await limit(`ip:${context.ip || 'local'}:${route}`, route === '/workspace' || route === '/backend' ? 1200 : 40);

    async function startSession(tokens, recovery = false) {
      const user = check(await auth.auth.getUser(tokens.access_token)).user;
      const profile = check(await service.from('app_profiles').select('*').eq('id', user.id).maybeSingle());
      if (!profile?.active || !user.email_confirmed_at) throw new Failure(403, 'Your account is not active or your email is not verified.');
      const raw = randomBytes(32).toString('base64url'), id = hash(raw);
      check(await service.from('app_login_sessions').insert({id, user_id:user.id,
        encrypted_tokens:seal({access_token:tokens.access_token,refresh_token:tokens.refresh_token,recovery}, secret, id),
        device:(request.headers.get('user-agent') || 'Unknown device').slice(0, 240),
        expires_at:new Date(Date.now() + 7 * 86400000).toISOString()}));
      headers['Set-Cookie'] = sessionCookie(raw, origin);
      await audit(user.id, recovery ? 'recovery_started' : 'signed_in');
      return {user:{id:user.id,email:user.email}, mfa_required:verifiedFactors(user).length > 0 && assurance(tokens.access_token) !== 'aal2', recovery};
    }
    if (request.method === 'POST' && ['/login','/signup','/recover'].includes(route)) {
      const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) throw new Failure(400, 'Enter a valid email address.');
      await limit(`${route}:${email}`, route === '/recover' ? 5 : 10, route === '/recover' ? 3600 : 900);
      if (route === '/login') {
        const result = await auth.auth.signInWithPassword({email, password:String(body.password || '')});
        if (result.error || !result.data.session) throw new Failure(401, 'Unable to sign in. Check your email, password, and email verification.');
        return response(await startSession(result.data.session));
      }
      const message = 'If this email has access, you will receive an email with the next steps.';
      if (process.env.ACCOUNT_EMAIL_READY !== '1') throw new Failure(503,'Account email delivery is being configured. Please contact the administrator before registering or resetting a password.');
      if (route === '/recover') {
        const sent = await auth.auth.resetPasswordForEmail(email, {redirectTo:`${origin}/auth/confirm`});
        if (sent.error && sent.error.status >= 500) throw new Failure(503, 'Email delivery is unavailable. Please try again later.');
      } else {
        validatePassword(body.password);
        const invite = check(await service.from('app_invites').select('email').eq('email',email).gt('expires_at',new Date().toISOString()).maybeSingle());
        if (invite) {
          const result = await auth.auth.signUp({email,password:body.password,options:{emailRedirectTo:`${origin}/auth/confirm`}});
          // Never establish an unverified session, even if provider configuration changes.
          if (result.error && !['user_already_exists','email_exists'].includes(result.error.code)) throw new Failure(400, 'Unable to send your verification email. Please contact the administrator.');
        }
      }
      return response({message});
    }
    if (route === '/confirm' && request.method === 'POST') {
      if (!['signup','invite','recovery','email_change'].includes(body.type) || typeof body.token_hash !== 'string' || body.token_hash.length > 512) throw new Failure(400, 'Invalid verification link.');
      const result = await auth.auth.verifyOtp({token_hash:body.token_hash,type:body.type});
      if (result.error || !result.data.session) throw new Failure(400, 'This link has expired or has already been used. Request a new email.');
      return response(await startSession(result.data.session, body.type === 'recovery' || body.type === 'invite'));
    }

    const raw = readSessionCookie(request, origin);
    if (!/^[A-Za-z0-9_-]{43}$/.test(raw)) {
      if (route === '/session' && request.method === 'GET') return response({user:null});
      throw new Failure(401, 'Sign in to continue.');
    }
    const sessionId = hash(raw);
    const stored = check(await service.from('app_login_sessions').select('*').eq('id',sessionId).maybeSingle());
    if (!stored || stored.revoked_at || Date.parse(stored.expires_at) <= Date.now() || Date.parse(stored.last_seen_at) < Date.now() - 12 * 3600000) throw new Failure(401, 'Your session has expired. Sign in again.');
    const saved = unseal(stored.encrypted_tokens, secret, sessionId);
    const restored = await auth.auth.setSession({access_token:saved.access_token,refresh_token:saved.refresh_token});
    if (restored.error || !restored.data.session) throw new Failure(401, 'Your session has expired. Sign in again.');
    const tokens = restored.data.session;
    const result = await auth.auth.getUser();
    if (result.error || !result.data.user || result.data.user.id !== stored.user_id) throw new Failure(401, 'Sign in again.');
    const user = result.data.user;
    const profile = check(await service.from('app_profiles').select('*').eq('id',user.id).maybeSingle());
    if (!profile?.active || !user.email_confirmed_at) throw new Failure(403, 'Your account is not active.');
    let expectedEncrypted = stored.encrypted_tokens;
    let latest = saved;
    async function persist(updated = tokens, recovery = saved.recovery) {
      const next = {access_token:updated.access_token,refresh_token:updated.refresh_token,recovery};
      const changed = next.access_token !== latest.access_token || next.refresh_token !== latest.refresh_token || recovery !== latest.recovery;
      const encrypted = changed ? seal(next,secret,sessionId) : expectedEncrypted;
      let query = service.from('app_login_sessions').update({...(changed ? {encrypted_tokens:encrypted} : {}),last_seen_at:new Date().toISOString()}).eq('id',sessionId).is('revoked_at',null);
      // A background session check must not replace a newly verified MFA session.
      if (changed) query = query.eq('encrypted_tokens',expectedEncrypted);
      const rows = check(await query.select('id'));
      if (!rows.length) throw new Failure(409,'Your session changed in another request. Please try again.');
      latest = next; expectedEncrypted = encrypted;
    }
    await persist();
    const needsMfa = verifiedFactors(user).length > 0 && assurance(tokens.access_token) !== 'aal2';
    if (route === '/session' && request.method === 'GET') return response({user:{id:user.id,email:user.email},profile:needsMfa ? null : profile,mfa_required:needsMfa,recovery:Boolean(saved.recovery),factors:verifiedFactors(user).map(f=>({id:f.id,friendly_name:f.friendly_name}))});
    if (route === '/logout' && request.method === 'POST') {
      let query = service.from('app_login_sessions').update({revoked_at:new Date().toISOString()}).eq('user_id',user.id);
      if (!body.all) query = query.eq('id',sessionId);
      check(await query);
      await auth.auth.signOut({scope:body.all ? 'global' : 'local'});
      headers['Set-Cookie'] = sessionCookie('',origin,true);
      await audit(user.id, body.all ? 'signed_out_everywhere' : 'signed_out');
      return response({ok:true});
    }
    if (route === '/mfa/verify' && request.method === 'POST') {
      await limit(`mfa:${user.id}`,10);
      const verified = check(await auth.auth.mfa.challengeAndVerify({factorId:String(body.factor_id),code:String(body.code)}));
      await persist(verified);
      await audit(user.id,'mfa_verified');
      return response({ok:true});
    }
    if (needsMfa) throw new Failure(403, 'Complete two-factor authentication to continue.');
    if (saved.recovery && route !== '/password') throw new Failure(403, 'Set your password to finish account recovery.');
    if (route === '/profile' && request.method === 'POST') {
      const updated = check(await auth.from('app_profiles').update(validateProfile(body)).eq('id',user.id).select().single());
      await audit(user.id,'profile_updated'); return response(updated);
    }
    async function reauthenticate() {
      if (saved.recovery) return;
      const fresh = createClient(supabaseUrl,anonKey,options);
      const result = await fresh.auth.signInWithPassword({email:user.email,password:String(body.current_password || '')});
      if (result.error) throw new Failure(400, 'Your current password is incorrect.');
      await fresh.auth.signOut({scope:'local'});
    }
    if (route === '/password' && request.method === 'POST') {
      await limit(`password:${user.id}`,5); await reauthenticate();
      check(await auth.auth.updateUser({password:validatePassword(body.password)}));
      check(await service.from('app_login_sessions').update({revoked_at:new Date().toISOString()}).eq('user_id',user.id));
      await auth.auth.signOut({scope:'global'});
      headers['Set-Cookie'] = sessionCookie('',origin,true);
      await audit(user.id,'password_changed'); return response({ok:true});
    }
    if (route === '/mfa/enroll' && request.method === 'POST') {
      if (verifiedFactors(user).length) throw new Failure(400, 'An authenticator is already connected.');
      const factors = check(await auth.auth.mfa.listFactors());
      for (const f of factors.all.filter(f=>f.status==='unverified')) check(await auth.auth.mfa.unenroll({factorId:f.id}));
      const data = check(await auth.auth.mfa.enroll({factorType:'totp',friendlyName:'EtGen authenticator'}));
      return response({id:data.id,totp:data.totp});
    }
    if (route === '/mfa/remove' && request.method === 'POST') {
      if (assurance(tokens.access_token) !== 'aal2') throw new Failure(403,'Verify your authenticator first.');
      await reauthenticate(); check(await auth.auth.mfa.unenroll({factorId:String(body.factor_id)}));
      await audit(user.id,'mfa_removed'); return response({ok:true});
    }
    if (route === '/sessions' && request.method === 'GET') {
      const rows = check(await service.from('app_login_sessions').select('id,device,created_at,last_seen_at,expires_at').eq('user_id',user.id).is('revoked_at',null).gt('expires_at',new Date().toISOString()).order('created_at',{ascending:false}));
      return response(rows.map(s=>({...s,current:s.id === sessionId})));
    }
    if (route === '/sessions/revoke' && request.method === 'POST') {
      check(await service.from('app_login_sessions').update({revoked_at:new Date().toISOString()}).eq('id',String(body.id)).eq('user_id',user.id));
      await audit(user.id,'session_revoked'); return response({ok:true});
    }
    if (route === '/events' && request.method === 'GET') return response(check(await service.from('app_security_events').select('id,event,created_at').eq('user_id',user.id).order('id',{ascending:false}).limit(30)));
    if (route === '/workspace' && request.method === 'GET') return response(check(await auth.from('app_workspaces').select('payload,revision,updated_at').eq('owner_id',user.id).single()));
    if (route === '/workspace' && request.method === 'POST') {
      if (!Number.isSafeInteger(body.revision) || body.revision < 0) throw new Failure(400,'Invalid workspace revision.');
      const rows = check(await auth.rpc('app_save_workspace',{expected_revision:body.revision,new_payload:validateWorkspace(body.payload)}));
      return response(rows[0]);
    }
    if (route === '/backups' && request.method === 'POST') {
      validateWorkspace(body.data); if (body.schema_version !== 1) throw new Failure(400,'Unsupported backup version.');
      return response(check(await auth.from('app_workspace_backups').insert({owner_id:user.id,payload:body}).select('id,created_at').single()),201);
    }
    if (route === '/backups' && request.method === 'GET') return response(check(await auth.from('app_workspace_backups').select('id,created_at').order('id',{ascending:false}).limit(50)));
    if (/^\/backups\/\d+$/.test(route) && request.method === 'GET') {
      const row = check(await auth.from('app_workspace_backups').select('payload').eq('id',route.split('/').pop()).maybeSingle());
      if (!row) throw new Failure(404,'Backup not found.'); return response(row.payload);
    }
    if (route === '/invites' && request.method === 'POST') {
      if (profile.role !== 'admin') throw new Failure(403,'Administrator access required.');
      const email = String(body.email || '').trim().toLowerCase();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Failure(400,'Enter a valid email.');
      await limit(`invite:${user.id}`,10,3600);
      const existing = check(await service.from('app_invites').select('role').eq('email',email).maybeSingle());
      if (existing?.role === 'admin') throw new Failure(400,'The administrator invitation is managed by the deployment owner.');
      check(await service.from('app_invites').upsert({email,role:'member',expires_at:new Date(Date.now()+14*86400000).toISOString()}));
      // Invitation membership and verified-email signup are separate: no password or bearer link is shared.
      await audit(user.id,'member_invited'); return response({message:'Access granted for 14 days. Share the registration link with this person.',url:`${origin}/signin?mode=signup`});
    }
    if (route === '/backend' && request.method === 'POST') {
      if (profile.role !== 'admin') throw new Failure(403,'Administrator access required.');
      const target = required(process.env.PRIVATE_BACKEND_URL,'Private research backend');
      const path = String(body.path || '');
      if (!/^\/api\/(scheduler|settings|stream|stores|research|keywords|gaps|designs|export)(?:\/|\?|$)/.test(path) || path.includes('%') || path.includes('#') || path.includes('..') || path.includes('\\') || !['GET','POST','PUT','DELETE'].includes(body.method || 'POST')) throw new Failure(400,'Unsupported backend action.');
      const backend = new URL(target); if (backend.protocol !== 'https:') throw new Failure(503,'Private backend must use HTTPS.');
      const forwarded = await fetch(backend.origin+path,{method:body.method || 'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${tokens.access_token}`},body:body.method === 'GET' ? undefined : JSON.stringify(body.body || {}),signal:AbortSignal.timeout(25000)});
      return new Response(await forwarded.text(),{status:forwarded.status,headers});
    }
    throw new Failure(404, 'Account action not found.');
  } catch (error) {
    if (error.status === 401) headers['Set-Cookie'] = sessionCookie('', origin, true);
    return response({error:error instanceof Failure || error instanceof ValidationError ? error.message : 'The account service could not complete this request. Please try again.'},error.status || 400);
  }
}

export const config = {path:'/api/account/*'};

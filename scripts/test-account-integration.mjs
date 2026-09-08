// Opt-in integration test: creates isolated synthetic accounts, sends no email,
// and removes only the exact users/invitations it created, even after a failure.
import assert from 'node:assert/strict';
import {randomUUID, randomBytes, createHmac} from 'node:crypto';
import {createClient} from '@supabase/supabase-js';
import handler from '../netlify/functions/account.mjs';

if (!process.argv.includes('--live')) throw new Error('Pass --live to test the configured Supabase project.');
for (const path of ['../.env.local','.env.local']) {try {process.loadEnvFile(path);} catch { /* optional path */ }}
process.env.APP_ORIGIN = 'http://127.0.0.1:5173';
const origin = process.env.APP_ORIGIN;
const options = {auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false}};
const service = createClient(process.env.SUPABASE_URL,process.env.SUPABASE_SERVICE_ROLE_KEY,options);
const client = () => createClient(process.env.SUPABASE_URL,process.env.SUPABASE_ANON_KEY,options);
const suffix=randomUUID(), password=randomBytes(24).toString('base64url');
const users=[], emails=[];
const check = result => {assert.equal(result.error,null,result.error?.message);return result.data;};
function browser() {
  let cookie='';
  return {get cookie(){return cookie;},async call(path,body,expected=200,headers={}) {
    const res = await handler(new Request(origin+'/api/account'+path,{method:body===undefined?'GET':'POST',headers:{Origin:origin,'X-Etgen-Request':'1','Content-Type':'application/json',Cookie:cookie,...headers},body:body===undefined?undefined:JSON.stringify(body)}),{ip:suffix});
    const data = await res.json();
    assert.equal(res.status,expected,`${path}: ${JSON.stringify(data)}`);
    const set=res.headers.get('set-cookie');if(set)cookie=set.split(';')[0];
    assert.match(res.headers.get('cache-control'),/no-store/);
    return {data,headers:res.headers};
  }};
}
function totp(secret) {
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits='';for(const char of secret.replace(/=+$/,''))bits+=alphabet.indexOf(char).toString(2).padStart(5,'0');
  const key=Buffer.from((bits.match(/.{8}/g)||[]).map(b=>parseInt(b,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const mac=createHmac('sha1',key).update(counter).digest(), offset=mac[19]&15;
  return ((mac.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,'0');
}
try {
  for (const [label,role,confirmed] of [['admin','admin',true],['member','member',true],['unverified','member',false]]) {
    const email=`auth-test-${label}-${suffix}@example.test`;emails.push(email);
    check(await service.from('app_invites').insert({email,role}));
    const user=check(await service.auth.admin.createUser({email,password,email_confirm:confirmed})).user;
    users.push(user);
  }
  assert.ok((await service.auth.admin.createUser({email:`uninvited-${suffix}@example.test`,password,email_confirm:true})).error);
  const [admin,member,unverified]=users;
  const a=browser(), b=browser(), another=browser();
  assert.equal((await a.call('/session')).data.user,null);
  await a.call('/workspace',undefined,401);
  await a.call('/login',{email:admin.email,password},403,{Origin:'https://untrusted.example'});
  await a.call('/login',{email:unverified.email,password},401);
  const login=await a.call('/login',{email:admin.email,password});
  assert.match(login.headers.get('set-cookie'),/HttpOnly; SameSite=Lax/);
  assert.ok(!JSON.stringify(login.data).includes('access_token'));
  await b.call('/login',{email:member.email,password});
  await another.call('/login',{email:admin.email,password});
  assert.equal((await a.call('/session')).data.profile.role,'admin');
  assert.equal((await b.call('/session')).data.profile.role,'member');
  await b.call('/invites',{email:'outsider@example.test'},403);
  await b.call('/backend',{path:'/api/settings',method:'GET'},403);
  await a.call('/profile',{display_name:'Test owner',business_name:'Test business',timezone:'America/New_York',currency:'USD'});
  await b.call('/profile',{display_name:'Impersonation',role:'admin'},400);
  const key='niche-research-pwa:stores:v1';
  const payload={[key]:[{slug:'private-test',name:'Private test',niche:'art'}]};
  assert.equal((await a.call('/workspace',{revision:0,payload})).data.revision,1);
  await a.call('/workspace',{revision:0,payload:{}},409);
  assert.deepEqual((await b.call('/workspace')).data.payload,{});
  const backup=(await a.call('/backups',{schema_version:1,created_at:new Date().toISOString(),data:payload},201)).data;
  await b.call('/backups/'+backup.id,undefined,404);
  const direct=client();check(await direct.auth.signInWithPassword({email:member.email,password}));
  assert.deepEqual(check(await direct.from('app_workspaces').select('*').eq('owner_id',admin.id)),[]);
  assert.ok((await direct.from('app_profiles').update({role:'admin'}).eq('id',member.id)).error);
  assert.ok((await direct.from('app_login_sessions').select('*')).error);
  assert.ok((await direct.from('app_workspaces').update({payload}).eq('owner_id',member.id)).error);
  const sessions=(await a.call('/sessions')).data;
  assert.equal(sessions.length,2);
  await a.call('/sessions/revoke',{id:sessions.find(s=>!s.current).id});
  await another.call('/workspace',undefined,401);
  const enrollment=(await a.call('/mfa/enroll',{})).data;
  await a.call('/mfa/verify',{factor_id:enrollment.id,code:totp(enrollment.totp.secret)});
  const challenged=browser();
  assert.equal((await challenged.call('/login',{email:admin.email,password})).data.mfa_required,true);
  await challenged.call('/workspace',undefined,403);
  await challenged.call('/mfa/verify',{factor_id:enrollment.id,code:'invalid'},400);
  console.log('Account isolation and session checks passed. Waiting for the next authenticator code.');
  // Avoid consuming a TOTP twice in the same time step on the provider.
  await new Promise(resolve=>setTimeout(resolve,30050-Date.now()%30000));
  await challenged.call('/mfa/verify',{factor_id:enrollment.id,code:totp(enrollment.totp.secret)});
  await challenged.call('/workspace');
  await challenged.call('/mfa/remove',{factor_id:enrollment.id,current_password:password});
  await a.call('/password',{current_password:'wrong password',password:password+'new'},400);
  assert.ok((await a.call('/session')).data.user);
  const recovery=check(await service.auth.admin.generateLink({type:'recovery',email:member.email}));
  const recovering=browser();
  await recovering.call('/confirm',{type:'recovery',token_hash:recovery.properties.hashed_token});
  await recovering.call('/workspace',undefined,403);
  await recovering.call('/password',{password:password+'new'});
  await b.call('/workspace',undefined,401);
  await recovering.call('/login',{email:member.email,password:password+'new'});
  check(await service.from('app_profiles').update({active:false}).eq('id',member.id));
  await recovering.call('/workspace',undefined,403);
  assert.deepEqual(check(await direct.from('app_workspaces').select('*')),[]);
  check(await service.from('app_profiles').update({active:true}).eq('id',member.id));
  check(await service.from('app_login_sessions').update({last_seen_at:new Date(Date.now()-13*3600000).toISOString()}).eq('user_id',member.id));
  await recovering.call('/workspace',undefined,401);
  await a.call('/logout',{all:true});
  await a.call('/workspace',undefined,401);
  console.log('PASS: invitations, verification, CSRF, cookies, roles, RLS isolation, concurrency, private backups, revocation, MFA challenge, password recovery and logout.');
} finally {
  let failed=false;
  for(const user of users){const result=await service.auth.admin.deleteUser(user.id);if(result.error)failed=true;}
  for(const email of emails){const result=await service.from('app_invites').delete().eq('email',email);if(result.error)failed=true;}
  if(failed)throw new Error('Synthetic-account cleanup needs attention.');
  console.log('Synthetic accounts and invitations removed. No emails were sent.');
}

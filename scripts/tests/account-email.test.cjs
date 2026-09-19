const {test}=require('node:test');
const assert=require('node:assert/strict');
const {randomBytes,createHash}=require('node:crypto');

test('email flow credentials are encrypted, origin-bound, expiring and fail closed',async()=>{
  const {createEmailFlow,readEmailFlow,emailRecipientAllowed}=await import('../../netlify/functions/lib/account-email.mjs');
  const {seal}=await import('../../netlify/functions/lib/account-security.mjs');
  const secret=randomBytes(32).toString('base64'),origin='https://app.example';
  const flow=createEmailFlow('owner@example.com','email',secret,origin);
  const request=new Request(origin,{headers:{cookie:flow.cookie.split(';')[0]}});
  const decoded=readEmailFlow(request,secret,origin);
  assert.equal(createHash('sha256').update(decoded.verifier).digest('base64url'),flow.challenge);
  assert.ok(!flow.cookie.includes(decoded.verifier));
  assert.match(flow.cookie,/^__Host-etgen-email=.*HttpOnly.*SameSite=Lax.*Secure$/);
  assert.throws(()=>readEmailFlow(request,secret,'https://another.example'));
  assert.throws(()=>readEmailFlow(new Request(origin),secret,origin));
  const expired=seal({...decoded,expires:0},secret,`email:${origin}`);
  assert.throws(()=>readEmailFlow(new Request(origin,{headers:{cookie:`__Host-etgen-email=${expired}`}}),secret,origin));
  process.env.ACCOUNT_EMAIL_MODE='team-only';
  delete process.env.ACCOUNT_EMAIL_ALLOWED_RECIPIENTS;
  assert.equal(emailRecipientAllowed('owner@example.com'),false);
  process.env.ACCOUNT_EMAIL_ALLOWED_RECIPIENTS=' Owner@Example.Com ';
  assert.equal(emailRecipientAllowed('owner@example.com'),true);
  assert.equal(emailRecipientAllowed('other@example.com'),false);
});

test('standard email callbacks keep tokens server-side and preserve password/MFA boundaries',async()=>{
  const {default:handler}=await import('../../netlify/functions/account.mjs');
  const origin='https://app.example',email='owner@example.com';
  Object.assign(process.env,{APP_ORIGIN:origin,SUPABASE_URL:'https://auth.example',SUPABASE_ANON_KEY:'test-anon',SUPABASE_SERVICE_ROLE_KEY:'test-service',AUTH_COOKIE_SECRET:randomBytes(32).toString('base64'),ACCOUNT_EMAIL_MODE:'team-only',ACCOUNT_EMAIL_ALLOWED_RECIPIENTS:email,ACCOUNT_EMAIL_READY:'1'});
  const previous=global.fetch, pending=new Map();let sent=0, tokenRequests=0, counter=0, mismatch=false, mfa=false;
  let lastEmail,storedSession;
  const user=()=>({id:'00000000-0000-4000-8000-000000000001',email:mismatch?'other@example.com':email,email_confirmed_at:new Date().toISOString(),factors:mfa?[{id:'factor',status:'verified'}]:[]});
  global.fetch=async(input,init={})=>{
    const url=new URL(typeof input==='string'?input:input.url || input);
    const data=init.body?JSON.parse(init.body):{};
    const ok=body=>Response.json(body);
    if(url.pathname.endsWith('/app_consume_auth_limit'))return ok(true);
    if(url.pathname.endsWith('/app_invites'))return ok({email});
    if(['/auth/v1/otp','/auth/v1/signup','/auth/v1/recover'].includes(url.pathname)){
      sent++;lastEmail={url,data};pending.set('code-'+(++counter),data.code_challenge);return ok({});
    }
    if(url.pathname==='/auth/v1/token'){
      tokenRequests++;
      const challenge=pending.get(data.auth_code);
      if(!challenge || createHash('sha256').update(data.code_verifier).digest('base64url')!==challenge)return Response.json({error:'invalid_grant'},{status:400});
      pending.delete(data.auth_code);
      return ok({access_token:'server-only-access',refresh_token:'server-only-refresh',expires_in:3600,user:user()});
    }
    if(url.pathname==='/auth/v1/user')return ok(user());
    if(url.pathname.endsWith('/app_profiles'))return ok({id:user().id,active:true,role:'admin'});
    if(url.pathname.endsWith('/app_login_sessions')){storedSession=data;return ok(null);}
    if(url.pathname.endsWith('/app_security_events'))return ok(null);
    throw new Error('Unexpected test request '+url.pathname);
  };
  async function call(path,body,cookie=''){
    return handler(new Request(origin+'/api/account'+path,{method:'POST',headers:{Origin:origin,'Content-Type':'application/json','X-Etgen-Request':'1',cookie},body:JSON.stringify(body)}),{ip:'test'});
  }
  try{
    const blocked=await call('/email',{email:'unapproved@example.com'});
    assert.equal(blocked.status,200);assert.equal(sent,0);
    for(const route of ['/email','/signup','/recover']){
      const started=await call(route,{email,password:'a-valid-long-password'});
      assert.equal(started.status,200);
      assert.equal(lastEmail.data.code_challenge_method,'s256');
      assert.equal(lastEmail.url.searchParams.get('redirect_to'),origin+'/auth/confirm');
      const cookie=started.headers.getSetCookie()[0].split(';')[0],code='code-'+counter;
      assert.equal((await call('/confirm',{code})).status,400);
      const other=await call(route,{email,password:'a-valid-long-password'});
      assert.equal((await call('/confirm',{code},other.headers.getSetCookie()[0].split(';')[0])).status,400);
      const confirmed=await call('/confirm',{code,type:'recovery'},cookie);
      assert.equal(confirmed.status,200);
      const content=await confirmed.json();
      assert.equal(content.recovery,route==='/recover');
      assert.ok(!JSON.stringify(content).includes('server-only'));
      assert.ok(!storedSession.encrypted_tokens.includes('server-only'));
      const cookies=confirmed.headers.getSetCookie();
      assert.equal(cookies.length,2);
      assert.ok(cookies.some(c=>c.startsWith('__Host-etgen-session=')));
      assert.ok(cookies.some(c=>c.startsWith('__Host-etgen-email=;')&&c.includes('Max-Age=0')));
      assert.equal((await call('/confirm',{code},cookie)).status,400);
    }
    const start=await call('/email',{email}),cookie=start.headers.getSetCookie()[0].split(';')[0];
    mismatch=true;
    assert.equal((await call('/confirm',{code:'code-'+counter},cookie)).status,403);
    mismatch=false;mfa=true;
    const next=await call('/email',{email});
    const confirmed=await call('/confirm',{code:'code-'+counter},next.headers.getSetCookie()[0].split(';')[0]);
    assert.equal((await confirmed.json()).mfa_required,true);
    assert.ok(tokenRequests>0);
  }finally{global.fetch=previous;}
});

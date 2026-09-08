// Local browser integration test. Requires auth-dev-server and Vite; sends no email.
import {chromium} from 'playwright';
import {createClient} from '@supabase/supabase-js';
import {randomUUID,randomBytes} from 'node:crypto';
import {mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
if(!process.argv.includes('--live'))throw new Error('Pass --live to create an isolated synthetic test account.');
for(const p of ['../.env.local','.env.local']){try{process.loadEnvFile(p);}catch{/* optional */}}
const service=createClient(process.env.SUPABASE_URL,process.env.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false,autoRefreshToken:false}});
const email=`auth-ui-${randomUUID()}@example.test`,password=randomBytes(24).toString('base64url');
let user,browser;
const check=r=>{assert.equal(r.error,null,r.error?.message);return r.data;};
await mkdir('work/account-qa',{recursive:true});
try{
  check(await service.from('app_invites').insert({email,role:'admin'}));
  user=check(await service.auth.admin.createUser({email,password,email_confirm:true})).user;
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext();
  const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const origin='http://127.0.0.1:5173';
  await page.goto(origin+'/workspace');await page.waitForURL('**/signin');
  for(const width of [320,768,1024,1440]){
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:`work/account-qa/signin-${width}.png`,fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Sign-in overflows at ${width}`);
  }
  await page.keyboard.press('Tab');assert.ok(await page.locator('#auth-email').evaluate(el=>el===document.activeElement));
  await page.getByLabel('Email address',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill('deliberately-wrong-password');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'Unable to sign in'}).waitFor();
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.waitForURL('**/account',{timeout:30000});
  await page.getByLabel('Display name',{exact:true}).fill('QA owner');
  await page.getByLabel('Business name').fill('Test studio');
  await page.getByRole('button',{name:'Save profile',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Profile saved.'}).waitFor();
  for(const width of [320,768,1024,1440]){
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:`work/account-qa/profile-${width}.png`,fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Profile overflows at ${width}`);
  }
  await page.getByRole('button',{name:'Security',exact:true}).click();
  await page.getByRole('heading',{name:'Change password',exact:true}).waitFor();
  await page.screenshot({path:'work/account-qa/security.png',fullPage:true});
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await page.getByText('This device',{exact:false}).first().waitFor();
  await page.screenshot({path:'work/account-qa/activity.png',fullPage:true});
  const cookies=await context.cookies();assert.ok(cookies.find(c=>c.name==='etgen-session')?.httpOnly);
  const stored=await page.evaluate(()=>JSON.stringify({...localStorage}));
  assert.ok(!stored.includes(user.id)&&!stored.includes('access_token')&&!stored.includes(email));
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.waitForURL('**/signin');
  assert.deepEqual(errors,[]);
  console.log('PASS: responsive sign-in/profile at 320, 768, 1024, 1440; keyboard focus, failed/successful login, profile save, security/activity, HttpOnly cookie, no local credential storage and logout.');
}finally{
  await browser?.close();
  if(user)check(await service.auth.admin.deleteUser(user.id));
  check(await service.from('app_invites').delete().eq('email',email));
  console.log('UI test account removed. Screenshots: work/account-qa');
}

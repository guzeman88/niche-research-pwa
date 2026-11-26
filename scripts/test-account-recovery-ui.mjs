import assert from 'node:assert/strict'
import {chromium} from 'playwright'
import {mkdir} from 'node:fs/promises'

const origin=process.env.DASHBOARD_UI_ORIGIN||'http://127.0.0.1:4173',site='http://account-recovery.test'
const profile={id:'recovery-owner',display_name:'Preserved owner',business_name:'Saved business',timezone:'America/New_York',currency:'USD',role:'admin'}
const packet={user:{id:profile.id,email:'qa@example.test'},profile,workspace:{payload:{},revision:7}}
const browser=await chromium.launch({headless:true})
await mkdir('work/signin-feedback-qa',{recursive:true})
try{
 for(const scenario of ['stalled-bootstrap','stalled-workspace','signed-out','mfa']){
  const context=await browser.newContext({serviceWorkers:'block'}),page=await context.newPage(),errors=[],mutations=[]
  let checks=0,release=()=>{}
  const gate=new Promise(resolve=>{release=resolve})
  page.on('pageerror',error=>errors.push(error.message))
  await context.route(site+'/**',async route=>{const u=new URL(route.request().url());await route.fulfill({response:await context.request.get(origin+u.pathname+u.search)})})
  await context.route('**/api/account/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.replace('/api/account','')
   if(request.method()!=='GET'){mutations.push(path);return route.fulfill({status:405,json:{error:'Read-only recovery fixture'}})}
   if(path==='/bootstrap'){
    checks++
    if(scenario==='signed-out')return route.fulfill({json:{user:null}})
    if(scenario==='mfa')return route.fulfill({json:{...packet,profile:null,workspace:undefined,mfa_required:true,factors:[{id:'qa-factor'}]}})
    if(checks===1&&scenario==='stalled-bootstrap'){
     await gate
     // A late response from the superseded check cannot replace the retry.
     return route.fulfill({json:{...packet,user:null}}).catch(()=>{})
    }
    return route.fulfill({json:checks===1&&scenario==='stalled-workspace'?{...packet,workspace:undefined}:packet})
   }
   if(path==='/workspace'&&scenario==='stalled-workspace'){await gate;return route.fulfill({json:{payload:{},revision:1}}).catch(()=>{})}
   return route.fulfill({status:503,json:{error:'Not needed for account recovery'}})
  })
  try{
   await page.goto(site+'/account')
   if(scenario==='signed-out'){await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'Account & profile'}).count(),0)}
   else if(scenario==='mfa'){await page.getByRole('heading',{name:'Verify it’s you',exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'Account & profile'}).count(),0)}
   else{
    await page.getByText('Loading your account…',{exact:true}).waitFor()
    if(scenario==='stalled-workspace'){
     await page.getByRole('heading',{name:'Account connection interrupted'}).waitFor({timeout:20000})
     await page.getByRole('alert').filter({hasText:'The account check took too long'}).waitFor()
     assert.equal(checks,1,'A failed check must not automatically replay itself')
    }
    const retry=page.getByRole('button',{name:'Retry connection',exact:true});await retry.waitFor()
    if(scenario==='stalled-workspace'){
     const contrast=await retry.evaluate(element=>{const style=getComputedStyle(element),luminance=color=>{const v=color.match(/[\d.]+/g).slice(0,3).map(x=>Number(x)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};const values=[luminance(style.color),luminance(style.backgroundColor)].sort((a,b)=>a-b);return (values[1]+.05)/(values[0]+.05)})
     assert(contrast>=4.5,'Recovery action text meets normal-text contrast')
    }
    for(const width of [320,1440]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`work/signin-feedback-qa/${scenario}-${width}.png`,fullPage:true})}
    await retry.click();await page.getByRole('heading',{name:'Account & profile'}).waitFor()
    assert.equal(await page.getByLabel('Display name',{exact:true}).inputValue(),'Preserved owner')
    release();await page.getByRole('button',{name:'Save profile',exact:true}).focus()
    assert.equal(await page.getByRole('heading',{name:'Account connection interrupted'}).count(),0)
    assert.equal(checks,2,'A deliberate retry starts exactly one fresh check')
   }
   assert.deepEqual(mutations,[],'Recovery never writes, logs out, or replays credentials')
   assert.deepEqual(errors,[])
  }finally{release();await context.unrouteAll({behavior:'ignoreErrors'});await context.close()}
 }
 console.log('PASS: stalled-check retry, late-response isolation, bounded workspace restore, preserved profile, no write/credential replay, signed-out/MFA gates and mobile/desktop recovery.')
}finally{await browser.close()}

import assert from 'node:assert/strict'
import {chromium} from 'playwright'
import {mkdir} from 'node:fs/promises'
const origin=process.env.DASHBOARD_UI_ORIGIN||'http://127.0.0.1:4173',host='http://startup.etgen.test'
const at=new Date().toISOString(),requests=[],errors=[]
let signedIn=false,omitSnapshot=false,allowBootstrap=()=>{}
const profile={id:'startup-owner',display_name:'QA owner',business_name:'QA',timezone:'America/New_York',currency:'USD',role:'admin'}
const starter={schema_version:1,generated_at:at,input_fingerprint:'qa',projects:{status:'ready',total:1,has_more:false,projects:[{id:'p',name:'Startup reference binder',product_type:'planner',updated_at:at}]},production:{status:'ready',total:0,has_more:false,jobs:[],human_approval_required:true}}
const dashboard={schema_version:2,generated_at:at,input_fingerprint:'qa',source_watermarks:{},stats:{total_seeds:10},evidence:{},sources:[{source:'etsy_open_api',keywords:2,rows:3,latest:at}],feed:{status:'ok'},delivery:{mode:'live'}}
const packet=()=>({user:{id:profile.id,email:'qa@example.test'},profile,workspace:{payload:{},revision:1},...(!omitSnapshot?{startup:starter,dashboard}:{})})
const browser=await chromium.launch({headless:true}),context=await browser.newContext({serviceWorkers:'block'})
await context.route(host+'/**',async route=>{const u=new URL(route.request().url());return route.fulfill({response:await context.request.get(origin+u.pathname+u.search)})})
await context.route('**/api/account/**',async route=>{
 const p=new URL(route.request().url()).pathname.replace('/api/account','');requests.push(p)
 if(p==='/backend/access')requests.push(route.request().postDataJSON().path)
 if(p==='/bootstrap'){
   if(signedIn&&omitSnapshot)await new Promise(resolve=>{allowBootstrap=resolve})
   return route.fulfill({json:signedIn?packet():{user:null}})
 }
 if(p==='/login'){signedIn=true;return route.fulfill({json:packet()})}
 if(p==='/logout'){signedIn=false;return route.fulfill({json:{ok:true}})}
 return route.fulfill({status:503,json:{error:'Private backend intentionally unavailable in startup QA.'}})
})
const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message))
try{
 await mkdir('work/fast-startup-qa',{recursive:true})
 await page.goto(host);await page.getByLabel('Email address',{exact:true}).fill('qa@example.test');await page.getByLabel('Password',{exact:true}).fill('qa-password-only')
 const before=requests.length
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await page.getByRole('link',{name:'Startup reference binder'}).waitFor()
 assert.equal(requests.slice(before).filter(p=>['/bootstrap','/session','/workspace','/startup','/dashboard/summary'].includes(p)).length,0,'Inline verified login packet must avoid dependent account reads')
 assert(!requests.some(p=>['/api/product-validation','/api/production','/api/production/jobs-overview'].includes(p)),'The dashboard and sidebar must not request full evidence or probe providers, including through scoped-ticket requests')
 for(const width of [1440,390]){await page.setViewportSize({width,height:1000});await page.screenshot({path:`work/fast-startup-qa/dashboard-${width}.png`,fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))}
 assert.equal(await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('etgen:startup:v1:')).length),1)
 omitSnapshot=true
 await page.reload({waitUntil:'domcontentloaded'});await page.getByText('Loading your account…',{exact:true}).waitFor()
 assert.equal(await page.getByRole('link',{name:'Startup reference binder'}).count(),0,'Cache must remain hidden before verified authentication')
 allowBootstrap();await page.getByRole('link',{name:'Startup reference binder'}).waitFor()
 assert.equal(await page.locator('.summary-strip').count(),0)
 assert.deepEqual(errors,[])
 console.log('PASS: inline login has no session/workspace/data waterfall; authenticated cache survives reload, stays hidden before auth; Pipeline desktop/mobile layout retained without the private backend.')
}finally{allowBootstrap();await context.unrouteAll({behavior:'wait'});await browser.close()}

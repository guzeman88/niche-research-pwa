import assert from 'node:assert/strict'
import {chromium} from 'playwright'
import {mkdir} from 'node:fs/promises'

const origin=process.env.DASHBOARD_UI_ORIGIN||'http://127.0.0.1:4173'
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({serviceWorkers:'block'})
let releaseBootstrap,releaseLogin,attempts=0
const bootstrapGate=new Promise(resolve=>{releaseBootstrap=resolve})
const loginGate=new Promise(resolve=>{releaseLogin=resolve})
const requests=[],errors=[]
const unavailable='Cloud sign-in and data are blocked by the provider’s database storage limit.'
await context.route('**/api/account/**',async route=>{
 const path=new URL(route.request().url()).pathname.replace('/api/account','')
 if(path==='/bootstrap'){
  await bootstrapGate
  return route.fulfill({status:503,json:{error:unavailable}})
 }
 if(path==='/login'){
  requests.push(route.request().postDataJSON());attempts++
  if(attempts===1)await loginGate
  return route.fulfill({status:attempts===1?503:401,json:{error:attempts===1?unavailable:'Unable to sign in with those credentials.'}})
 }
 return route.fulfill({status:503,json:{error:unavailable}})
})
const page=await context.newPage()
page.on('pageerror',error=>errors.push(error.message))
async function buttonContrast(button){
 const ratio=await button.evaluate(el=>{
  const style=getComputedStyle(el)
  const luminance=color=>{
   const channels=color.match(/[\d.]+/g).slice(0,3).map(v=>Number(v)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
   return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722
  }
  if(style.opacity!=='1')return 0
  const values=[luminance(style.color),luminance(style.backgroundColor)].sort((a,b)=>a-b)
  return (values[1]+.05)/(values[0]+.05)
 })
 assert(ratio>=4.5,`Sign-in button text contrast is ${ratio.toFixed(2)}:1`)
}
try{
 await mkdir('work/signin-feedback-qa',{recursive:true})
 await page.goto(origin+'/signin')
 const checking=page.getByRole('button',{name:'Checking account…',exact:true})
 await checking.waitFor()
 assert(await checking.isDisabled(),'Pending session verification must be explicit, not an inert Sign in button')
 await buttonContrast(checking)
 assert.equal(await page.locator('form').getAttribute('aria-busy'),'true')
 await page.screenshot({path:'work/signin-feedback-qa/checking.png',fullPage:true})
 releaseBootstrap()
 const submit=page.getByRole('button',{name:'Sign in',exact:true})
 await submit.waitFor()
 await page.getByRole('alert').filter({hasText:unavailable}).waitFor()
 assert(await submit.isEnabled())
 await buttonContrast(submit)
 await submit.click()
 await page.getByRole('alert').filter({hasText:'Enter your email address.'}).waitFor()
 await page.getByLabel('Email address',{exact:true}).fill('invalid')
 await submit.click()
 await page.getByRole('alert').filter({hasText:'Enter a valid email address.'}).waitFor()
 await page.getByLabel('Email address',{exact:true}).fill('qa@example.test')
 await submit.click()
 await page.getByRole('alert').filter({hasText:'Enter your password.'}).waitFor()
 assert.equal(requests.length,0,'Invalid native fields must not send credentials')
 // Password managers can fill the DOM without React change events. Read the
 // submitted native form, without persisting or logging any real credentials.
 await page.locator('#auth-email').evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'autofill@example.test')})
 await page.locator('#auth-password').evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'synthetic-test-password')})
 await page.locator('#auth-password').press('Enter')
 await page.getByRole('button',{name:'Please wait…',exact:true}).waitFor()
 assert(await page.getByRole('button',{name:'Please wait…',exact:true}).isDisabled())
 assert.deepEqual(requests,[{email:'autofill@example.test',password:'synthetic-test-password'}])
 releaseLogin()
 await page.getByRole('alert').filter({hasText:unavailable}).waitFor()
 assert(await submit.isEnabled())
 assert.equal(await page.locator('#auth-email').inputValue(),'autofill@example.test')
 assert.equal(await page.locator('#auth-password').inputValue(),'synthetic-test-password')
 for(const width of [320,768,1024,1440]){
  await page.setViewportSize({width,height:900})
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Sign-in overflows at ${width}`)
  await page.screenshot({path:`work/signin-feedback-qa/provider-error-${width}.png`,fullPage:true})
 }
 await submit.click()
 await page.getByRole('alert').filter({hasText:'Unable to sign in with those credentials.'}).waitFor()
 assert.equal(attempts,2,'Failures must permit a deliberate retry without automatic credential replay')
 assert.deepEqual(errors,[])
 console.log('PASS: visible session check, native validation, password-manager DOM submission, keyboard Enter, busy state, provider errors, deliberate retry and responsive sign-in.')
}finally{
 releaseBootstrap();releaseLogin()
 await context.unrouteAll({behavior:'wait'})
 await browser.close()
}

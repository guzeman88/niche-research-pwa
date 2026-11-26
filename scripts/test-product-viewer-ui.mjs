// Controlled UI contract fixtures; backend tests separately parse real customer files.
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
import {chromium} from 'playwright'
const origin=process.env.VALIDATION_UI_ORIGIN||'http://127.0.0.1:4173',site='http://viewer.test',at=new Date().toISOString()
const fingerprint='viewer-fixture',files=['customer.xlsx','instructions.txt','customer.zip']
const job={id:'viewer-job',product_id:'viewer-product',revision:'fixture-revision',status:'needs_review',history:[],spec:{name:'QA complete product',family:'wedding_workbook',purpose:'Controlled viewer fixture',research:{}},result:{manifest:{artifact_fingerprint:fingerprint,files:files.map(name=>({name,bytes:20})),render:{preview_kind:'rasterized_actual_customer_pdf',customer_files:files,previews:Array.from({length:11},(_,i)=>`preview-${i+1}.png`)}},quality:{checks:[]},listing:{blockers:[],description:'QA listing',tags:[]},listing_images:['listing.png']}}
const cell=(address,value,formula=null)=>({address,value,formula,format:'General',bold:false,fill:null})
const sheets=[{name:'Budget',state:'visible',columns:7,merged:[],rows:Array.from({length:201},(_,i)=>[cell('A'+(i+1),i===200?'Final customer row':i===0?'Budget item':i),cell('B'+(i+1),i===1?null:0,i===1?'=SUM(A3:A201)':null),...Array.from({length:5},(_,col)=>cell(String.fromCharCode(67+col)+(i+1),'Worksheet data'))])},{name:'Last worksheet',state:'hidden',columns:1,merged:[],rows:[[cell('A1','All worksheets available')]]}]
const browser=await chromium.launch({headless:true}),context=await browser.newContext({serviceWorkers:'block'})
let failView=true,downloads=0;const errors=[]
await context.route(site+'/**',async route=>{const u=new URL(route.request().url());return route.fulfill({response:await context.request.get(origin+u.pathname+u.search)})})
await context.route('**/api/account/**',route=>{
 const request=route.request(),path=new URL(request.url()).pathname.replace('/api/account','')
 if(path==='/session'||path==='/bootstrap')return route.fulfill({json:{user:{id:'viewer-qa',email:'qa@example.test'},profile:{id:'viewer-qa',role:'admin'},mfa_required:false}})
 if(path==='/workspace')return route.fulfill({json:{payload:{},revision:1}})
 if(path==='/startup')return route.fulfill({json:{schema_version:1,generated_at:at,projects:{status:'ready',total:0,has_more:false,projects:[]},production:{status:'ready',total:1,has_more:false,paused:false,jobs:[{...job,has_preview:true,updated_at:at}]}}})
 if(path==='/backend/access'){const body=request.postDataJSON();return route.fulfill({json:{url:'https://viewer-api.test'+body.path,token:'qa-only-ticket'}})}
 return route.fulfill({status:404,json:{error:'Fixture route not available'}})
})
await context.route('https://viewer-api.test/**',route=>{
 const u=new URL(route.request().url()),path=u.pathname
 if(path.endsWith('/jobs-overview'))return route.fulfill({json:{jobs:[job],paused:false}})
 if(path.endsWith('/jobs/viewer-job'))return route.fulfill({json:job})
 if(path.endsWith('/document'))return route.fulfill({json:{pages:11,previews:job.result.manifest.render.previews,artifact_fingerprint:fingerprint}})
 if(path.endsWith('/view')){
  if(failView)return route.fulfill({status:400,json:{detail:'The product package changed. Reopen its review before viewing files.'}})
  const name=u.searchParams.get('name');assert.equal(u.searchParams.get('fingerprint'),fingerprint)
  return route.fulfill({json:{name,artifact_fingerprint:fingerprint,...(name==='customer.xlsx'?{kind:'workbook',sheets}:name==='instructions.txt'?{kind:'text',text:'Complete customer instructions, without a download.'}:{kind:'package',files:[{name:'customer.xlsx',bytes:100}]})}})
 }
 if(path.includes('/files/')||path.endsWith('/thumbnail'))return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH1sAAAAASUVORK5CYII=','base64')})
 return route.fulfill({status:404,json:{detail:'Fixture route not available'}})
})
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('download',()=>downloads++)
await mkdir('work/product-viewer-qa',{recursive:true})
try{
 await page.goto(site+'/production');await page.getByRole('button',{name:'Review',exact:true}).click()
 const viewer=page.getByRole('region',{name:'Complete product viewer'})
 await viewer.waitFor();await viewer.locator('figure').first().waitFor();assert.equal(await viewer.locator('figure').count(),11)
 await viewer.getByLabel('Page',{exact:true}).selectOption('10');await viewer.getByRole('img',{name:'Page 11 of 11',exact:true}).waitFor()
 await viewer.getByLabel('Zoom',{exact:true}).selectOption('200')
 await viewer.getByLabel('View',{exact:true}).selectOption('customer.xlsx');await viewer.getByRole('alert').waitFor()
 failView=false;await viewer.getByRole('button',{name:'Retry file',exact:true}).click()
 await viewer.getByLabel('Worksheet',{exact:true}).waitFor()
 await viewer.locator('td[data-cell="1-1"]').click();assert.equal(await viewer.getByLabel('Cell contents').innerText(),'=SUM(A3:A201)')
 await page.keyboard.press('ArrowDown');assert.equal(await viewer.locator('td[data-cell="2-1"]').evaluate(e=>e===document.activeElement),true)
 assert.equal(await viewer.getByText('Not calculated',{exact:true}).count(),1)
 await viewer.getByRole('button',{name:'Next rows'}).click();await viewer.getByRole('button',{name:'Next rows'}).click();await viewer.getByRole('gridcell',{name:'Final customer row',exact:true}).waitFor()
 await viewer.getByLabel('Worksheet',{exact:true}).selectOption('1');await viewer.getByRole('gridcell',{name:'All worksheets available',exact:true}).waitFor()
 await viewer.getByLabel('Worksheet',{exact:true}).selectOption('0')
 await viewer.locator('td[data-cell="12-0"]').hover();assert.equal(await viewer.locator('td[data-cell="12-0"]').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)','Inherited row hover must not hide worksheet text')
 for(const width of [1440,390,320]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Viewer fits ${width}`);if(width!==320)await page.screenshot({path:`work/product-viewer-qa/workbook-${width}.png`,fullPage:true})}
 await viewer.getByLabel('View',{exact:true}).selectOption('instructions.txt');await viewer.getByText('Complete customer instructions, without a download.',{exact:true}).waitFor()
 await viewer.getByLabel('View',{exact:true}).selectOption('customer.zip');await viewer.getByText('customer.xlsx',{exact:true}).first().waitFor()
 await viewer.getByLabel('View',{exact:true}).selectOption('listing-images');await viewer.getByRole('img',{name:'Image 1 of 1',exact:true}).waitFor()
 assert.equal(downloads,0);assert.equal(await page.getByRole('form',{name:'Review production files'}).getByRole('checkbox',{checked:true}).count(),0)
 assert.deepEqual(errors,[]);console.log('PASS: all pages, zoom, authenticated file views, retry, complete worksheet pagination, formulas, hidden sheets, keyboard cells, instructions and listing images without downloads; approval stays untouched.')
}catch(error){await writeFile('work/product-viewer-qa/failure.txt',await page.locator('body').innerText());throw error}finally{await context.unrouteAll({behavior:'ignoreErrors'});await browser.close()}

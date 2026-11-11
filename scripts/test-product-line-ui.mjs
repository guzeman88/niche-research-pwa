// Isolated real API: starting briefs, v2 authoring, privacy and responsive UI.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'

async function freePort(){const server=net.createServer();await new Promise(done=>server.listen(0,'127.0.0.1',done));const port=server.address().port;await new Promise(done=>server.close(done));return port}
const temp=await mkdtemp(join(tmpdir(),'etgen-product-lines-ui-'))
const apiPort=await freePort();const uiPort=await freePort()
const api=`http://127.0.0.1:${apiPort}`;const origin=`http://127.0.0.1:${uiPort}`
const env={...process.env,BACKEND_DIR:temp,KEYWORD_DB_PATH:join(temp,'research.sqlite'),VALIDATION_DB_PATH:join(temp,'ledger.sqlite'),PRODUCTION_ROOT:join(temp,'production'),
  APP_PRODUCTION_ENABLED:'0',APP_KEYWORD_FEED_ENABLED:'0',AUTO_START_SCHEDULER:'0',SUPABASE_URL:'',SUPABASE_SERVICE_ROLE_KEY:'',SUPABASE_ANON_KEY:'',
  PRODUCTION_OLLAMA_URL:'http://127.0.0.1:9',PRODUCTION_COMFY_URL:'http://127.0.0.1:9'}
const backend=spawn(process.env.VALIDATION_QA_PYTHON || 'python',['-m','uvicorn','main:app','--host','127.0.0.1','--port',String(apiPort)],{cwd:resolve('backend'),env,stdio:'pipe'})
const preview=spawn(process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port',String(uiPort),'--strictPort'],{stdio:'pipe'})
let browser
try{
  for(const url of [`${api}/api/health`,origin]){let ready=false;for(let attempt=0;attempt<60;attempt++){try{if((await fetch(url)).ok){ready=true;break}}catch{}await delay(500)}assert(ready,`server ready: ${url}`)}
  browser=await chromium.launch({headless:true});const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message))
  await page.goto(`${origin}/validation`)
  await page.getByLabel('Research server address').fill(api);await page.getByRole('button',{name:'Connect workspace',exact:true}).click()
  await page.getByText('Start a birthday or wedding product',{exact:true}).click()
  for(const name of ['Birthday magazine','Milestone birthday newspaper','Photo memory book','Coordinated birthday party set','Wedding budget and guest workbook','Wedding-day coordination binder','Complete wedding planning suite'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),1)
  await page.getByRole('button',{name:'Birthday magazine',exact:true}).click()
  const form=page.getByRole('form',{name:'Production specification'})
  assert.equal(await form.getByRole('combobox',{name:/Product family/}).inputValue(),'birthday_magazine')
  await form.getByLabel('Your creative direction').fill('Authored editorial layout with generous margins and original headings.')
  await form.getByLabel('Human-authored customer instructions').fill('Open the editable document, replace the example wording and export the verified print PDF.')
  await form.getByLabel('Page text',{exact:false}).fill('Your birthday story.\n\nYour favorite memories.\n\nMessages to treasure.\n\nLooking ahead.')
  await form.getByRole('button',{name:'Queue product revision',exact:true}).focus();await page.keyboard.press('Enter')
  await page.getByRole('form',{name:'Production specification'}).waitFor({state:'detached'})
  const overview=await (await fetch(`${api}/api/production`)).json();assert.equal(overview.jobs.length,1)
  const job=overview.jobs[0];assert.equal(job.spec.schema_version,2);assert.equal(job.spec.family,'birthday_magazine');assert.equal(job.spec.product_data.pages.length,4)
  assert.equal(job.spec.creative_note.startsWith('Authored editorial'),true);assert.equal(job.spec.research.qualification_credit,false)
  await page.getByRole('button',{name:'Wedding budget and guest workbook',exact:true}).click()
  const workbook=page.getByRole('form',{name:'Production specification'})
  assert.equal(await workbook.getByLabel('Product name',{exact:true}).inputValue(),'Wedding budget and guest workbook')
  await workbook.getByLabel('Supported guest rows').fill('200');await workbook.getByLabel('Example budget rows').fill('Venue | Room hire | 2500 | 2400 | 500')
  await page.getByText('Private order personalization',{exact:true}).click()
  await page.getByText('Approve a product-line revision before adding customer work.',{exact:true}).waitFor()
  await mkdir('work/ui-product-lines',{recursive:true})
  for(const width of [320,768,1024,1440]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`No horizontal overflow at ${width}`);await page.screenshot({path:`work/ui-product-lines/${width}.png`,fullPage:true})}
  await workbook.getByRole('combobox',{name:/Product family/}).selectOption('crochet_pattern')
  const tested=workbook.getByRole('checkbox',{name:/documented maker test used these exact/})
  await tested.check();await workbook.getByLabel('Human-written pattern instructions').fill('Changed human-authored instructions.')
  assert.equal(await tested.isChecked(),false,'Changing the actual source clears maker-test attestation')
  await workbook.getByRole('combobox',{name:/Product family/}).selectOption('pet_portrait')
  assert.equal(await workbook.getByRole('checkbox',{name:/verified the pet.s identity and likeness/}).isChecked(),false)
  assert.deepEqual(errors,[])
  console.log('Product-line UI: seven briefs, real v2 API handoff, original-content fields, workbook controls, private-order boundary and four responsive widths passed.')
}finally{
  if(browser)await browser.close()
  for(const process of [backend,preview]){if(process.pid){if(globalThis.process.platform==='win32')spawnSync('taskkill',['/PID',String(process.pid),'/T','/F'],{stdio:'ignore'});else process.kill()}}
}

// Isolated synthetic references and temporary backend; no real provider/account use.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join, resolve} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'

const temporary = await mkdtemp(join(tmpdir(), 'etgen-intelligence-ui-'))
const socket = net.createServer()
await new Promise(done => socket.listen(0, '127.0.0.1', done))
const port = socket.address().port
await new Promise(done => socket.close(done))
const api = `http://127.0.0.1:${port}`
const python = process.env.VALIDATION_QA_PYTHON || 'python'
const env = {...process.env, BACKEND_DIR: temporary, VALIDATION_DB_PATH: join(temporary, 'ledger.sqlite'),
  KEYWORD_DB_PATH: join(temporary, 'keywords.sqlite'), SALES_INTELLIGENCE_ROOT: join(temporary, 'archive'),
  APP_KEYWORD_FEED_ROOT: join(temporary, 'native'), APP_KEYWORD_FEED_ENABLED: '0', APP_SALES_INTELLIGENCE_ENABLED: '0',
  APP_PRODUCTION_ENABLED: '0', AUTO_START_SCHEDULER: '0', PIPELINE_API_TOKEN: '',
  SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: ''}
const fixture = spawnSync(python, ['-c', `
from pathlib import Path
from datetime import timedelta
import json,os,sqlite3
from services.sales_intelligence import store,registry,ingestion,estimator
from services import selling_discovery
store.counts(); at=store.now()-timedelta(hours=1)
grants={s:{'reference':'Synthetic isolated test permission, not a provider grant','account_ref':'fixture','issued_at':(at-timedelta(days=90)).isoformat(),'expires_at':(at+timedelta(days=1)).isoformat(),'free_only':True,'capabilities':['storage','comparison','training','export']} for s in ('muadzo','hive')}
(store.root()/'access.json').write_text(json.dumps(grants))
for source,value in [('muadzo',20),('hive',24)]:
 row={'source_id':source,'listing_id':'123','metric':'estimated_sales','value':value,'unit':'purchases','basis':'period','period_start':(at-timedelta(days=30)).isoformat(),'period_end':at.isoformat(),'captured_at':at.isoformat(),'available_at':at.isoformat(),'source_ref':'Synthetic UI reference fixture','metadata':{'listing_id':'123','title':'Synthetic fixture planner','shop':'Synthetic shop','captured_at':at.isoformat(),'available_at':at.isoformat(),'source_ref':'Synthetic UI metadata','price':8,'currency':'USD'}}
 data={'source_id':source,'format':'json','content':json.dumps([row])}; preview=ingestion.preview(data);ingestion.commit({**data,'expected_fingerprint':preview['fingerprint']})
with store.database(True) as c:
 store.add_metadata(c,{'listing_id':'456','title':'Synthetic fixture without sales','shop':'Synthetic shop B','captured_at':at.isoformat(),'available_at':at.isoformat(),'source_ref':'Synthetic fixture','price':None,'currency':''})
native=Path(os.environ['APP_KEYWORD_FEED_ROOT']);(native/'data').mkdir(parents=True);p=native/'data/catalog.sqlite'
with sqlite3.connect(p) as c:
 c.execute('CREATE TABLE keyword_listing_snapshots(id INTEGER PRIMARY KEY,listing_id TEXT,title TEXT,keyword TEXT,shop_name TEXT,observed_at TEXT,price REAL,currency_code TEXT,favorites INTEGER,review_count INTEGER,collection_run_id TEXT)')
 c.execute('INSERT INTO keyword_listing_snapshots VALUES(1,?,?,?,?,?,?,?,?,?,?)',('123','Synthetic fixture planner','teacher planner','Synthetic shop',at.isoformat(),8,'USD',10,None,'synthetic-ui'))
(native/'installation.json').write_text(json.dumps({'database':str(p)}));selling_discovery.sync_catalog()
from models.selling_products import Listing,Packet
fixture_packet=Packet(listings=[Listing(listing_id='123',title='Synthetic fixture planner',shop='Synthetic shop',source_ref='Isolated UI fixture')]).model_dump(mode='json')
review_window={'start':(at-timedelta(days=30)).isoformat(),'end':at.isoformat(),'review_times':[(at-timedelta(days=2)).isoformat()], 'complete':True,'observed_reviews':1,'reported_count':1,'limit':100,'source_ref':'Synthetic review-window fixture','completeness_basis':'isolated_fixture'}
estimator.record_capture(fixture_packet,at,review_window);estimator.refresh()
`], {cwd: resolve('backend'), env, encoding: 'utf8'})
assert.equal(fixture.status, 0, fixture.stderr)
const backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'pipe'})
let log = '', browser, page
backend.stderr.on('data', chunk => {log += chunk.toString()})
try {
  let ready = false
  for (let i = 0; i < 60; i++) {try {if ((await fetch(`${api}/api/health`)).ok) {ready = true; break}} catch {} await delay(500)}
  assert(ready, log)
  browser = await chromium.launch({headless: true})
  page = await browser.newPage({viewport: {width: 1440, height: 1000}})
  const errors = [], providerRequests = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {if (/https:\/\/(?:www\.)?(?:etsy|muadzo|ehunt|exto)\./.test(request.url())) providerRequests.push(request.url())})
  await page.goto(`${process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'}/selling`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  const intelligence = page.getByRole('region', {name: 'Sales intelligence', exact: true})
  await intelligence.getByRole('button', {name: 'Open sales intelligence', exact: true}).click()
  await intelligence.getByLabel('Compare Etsy listing ID').fill('123')
  await intelligence.getByLabel('Compare Etsy listing ID').press('Enter')
  await intelligence.getByText('Provider center 22', {exact: false}).waitFor()
  await intelligence.getByText('2 providers / 2 method groups.', {exact: false}).waitFor()
  await intelligence.getByText('EtGen student: no active model', {exact: false}).waitFor()
  await intelligence.getByLabel('Compare Etsy listing ID').fill('456')
  await intelligence.getByLabel('Compare Etsy listing ID').press('Enter')
  await intelligence.getByText('No eligible compatible sales estimates.', {exact: false}).waitFor()
  const tabs = intelligence.getByRole('navigation', {name: 'Sales intelligence sections'})
  await tabs.getByRole('button', {name: 'estimates', exact: true}).click()
  await intelligence.getByRole('heading', {name: 'Our automatic sales estimates', exact: true}).waitFor()
  await intelligence.getByText('10 estimated purchases / 30 days', {exact: false}).waitFor()
  await intelligence.getByLabel('With estimates only', {exact: true}).check()
  await intelligence.getByRole('button', {name: 'Recalculate estimates', exact: true}).click()
  await intelligence.getByText('Calculation queued.', {exact: false}).waitFor()
  const automaticCaptures = []
  for (const width of [1440, 320]) {
    await page.setViewportSize({width, height: 1000})
    await page.evaluate(() => window.scrollTo(0, 0))
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `estimate overflow at ${width}`)
    await mkdir('.impeccable/review', {recursive: true})
    const path = `.impeccable/review/automatic-estimates-${width}.png`
    await page.screenshot({path, fullPage: true}); automaticCaptures.push(path)
  }
  await page.setViewportSize({width: 1440, height: 1000})
  await tabs.getByRole('button', {name: 'sources', exact: true}).click()
  await intelligence.getByRole('link', {name: 'MuaDzo', exact: true}).waitFor()
  assert.equal(await intelligence.getByRole('button', {name: /^Check /}).count(), 24)
  await intelligence.getByRole('button', {name: 'Pause research worker', exact: true}).click()
  await intelligence.getByRole('button', {name: 'Resume research worker', exact: true}).waitFor()
  await intelligence.getByRole('button', {name: 'Resume research worker', exact: true}).click()
  await tabs.getByRole('button', {name: 'import', exact: true}).click()
  const form = intelligence.getByRole('form', {name: 'Import provider references'})
  await form.getByLabel('Export contents', {exact: true}).fill('[]')
  await form.getByRole('button', {name: 'Preview references'}).click()
  await form.getByRole('alert').waitFor()
  const captureTime = new Date(Date.now() - 60000).toISOString()
  await form.getByLabel('Export contents', {exact: true}).fill(JSON.stringify([{source_id: 'muadzo', listing_id: '789', metric: 'estimated_sales', value: 30, basis: 'provider_monthly', unit: 'unknown', captured_at: captureTime, available_at: captureTime, source_ref: 'Synthetic UI import, not real sales'}]))
  await form.getByRole('button', {name: 'Preview references'}).click()
  await form.getByLabel('Normalized import preview').getByText('Listing 789', {exact: false}).waitFor()
  await form.getByRole('button', {name: 'Save reference history'}).click()
  await form.getByText('Reference history imported.', {exact: false}).waitFor()
  await tabs.getByRole('button', {name: 'coverage', exact: true}).click()
  await intelligence.getByText('What the collected evidence covers', {exact: true}).waitFor()
  await tabs.getByRole('button', {name: 'opportunities', exact: true}).click()
  await intelligence.getByRole('button', {name: 'Synthetic fixture planner', exact: true}).click()
  await intelligence.getByText('Provider center 22', {exact: false}).waitFor()
  await intelligence.getByText('Preserved reference history', {exact: false}).click()
  await intelligence.getByRole('img', {name: /^Reference estimates/}).waitFor()
  const investigation = page.waitForResponse(response => response.url().endsWith('/api/sales-intelligence/listings/123/investigate'))
  await intelligence.getByRole('button', {name: 'Investigate this product', exact: true}).click()
  assert((await investigation).ok(), 'Investigation request must succeed')
  const saved = await (await fetch(`${api}/api/selling-products`)).json()
  assert(JSON.stringify(saved).includes('discovered-123'), 'Investigation must open the existing private opportunity workflow')
  await tabs.getByRole('button', {name: 'learning', exact: true}).click()
  await intelligence.getByText('No fitted consensus model.', {exact: false}).waitFor()
  await intelligence.getByRole('button', {name: 'Queue 30-day purchase model', exact: true}).click()
  await intelligence.getByText('Request queued.', {exact: false}).waitFor()
  const queued = await (await fetch(`${api}/api/sales-intelligence/jobs`)).json()
  assert(queued.items.some(job => job.status === 'queued'))
  await tabs.getByRole('button', {name: 'compare', exact: true}).click()
  await intelligence.getByLabel('Compare Etsy listing ID').fill('123')
  await intelligence.getByLabel('Compare Etsy listing ID').press('Enter')
  await intelligence.getByText('Provider center 22', {exact: false}).waitFor()
  await intelligence.getByRole('button', {name: 'Compare', exact: true}).focus()
  assert(await intelligence.getByRole('button', {name: 'Compare', exact: true}).evaluate(element => element === document.activeElement))
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent === 'Refresh saved history' && !button.disabled))
  await intelligence.getByText('Preserved reference history', {exact: false}).click()
  await mkdir('.impeccable/review', {recursive: true})
  const captures = []
  for (const width of [1440, 1024, 768, 651, 320]) {
    await page.setViewportSize({width, height: 1000})
    await page.evaluate(() => window.scrollTo(0, 0))
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow at ${width}`)
    const path = `.impeccable/review/intelligence-${width}.png`
    await page.screenshot({path, fullPage: true}); captures.push(path)
  }
  await page.setViewportSize({width: 1440, height: 1000})
  await tabs.getByRole('button', {name: 'sources', exact: true}).click()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({path: '.impeccable/review/intelligence-sources.png', fullPage: true})
  for (const tab of ['coverage', 'learning', 'opportunities', 'import']) {
    await tabs.getByRole('button', {name: tab, exact: true}).click()
    const headings = {coverage: 'What the collected evidence covers', learning: 'Learning from reference estimates', opportunities: 'Opportunities supported by reference estimates', import: 'Import dated provider estimates'}
    await intelligence.getByRole('heading', {name: headings[tab], exact: true}).waitFor()
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({path: `.impeccable/review/intelligence-${tab}.png`, fullPage: true})
  }
  assert.deepEqual(errors, [])
  assert.deepEqual(providerRequests, [])
  await writeFile(join(temporary, 'ui-verification.json'), JSON.stringify({isolated_synthetic: true, captures, provider_requests: 0, source_count: 24,
    matched_consensus: true, unknown_sales_preserved: true, pause_resume: true, import_errors: true, training_queued: true, responsive_widths: [1440, 1024, 768, 651, 320]}, null, 2))
  console.log(`Sales intelligence UI passed: isolated reference comparison, unknowns, 24 sources, pause/resume, import errors, durable training and five widths. Evidence: ${temporary}`)
} catch (error) {
  if (page) {await mkdir('work/ui-intelligence', {recursive: true}); await writeFile('work/ui-intelligence/failure.txt', await page.locator('body').innerText())}
  console.error(log.slice(-2200)); throw error
} finally {
  if (browser) await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], {stdio: 'ignore'})
  else backend.kill()
}

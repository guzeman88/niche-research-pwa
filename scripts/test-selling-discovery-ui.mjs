// End-to-end discovery using isolated fixtures. No live ledger or Etsy requests.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'

const temp = await mkdtemp(join(tmpdir(), 'etgen-discovery-qa-'))
const socket = net.createServer(); await new Promise(done => socket.listen(0, '127.0.0.1', done))
const port = socket.address().port; await new Promise(done => socket.close(done))
const api = `http://127.0.0.1:${port}`, python = process.env.VALIDATION_QA_PYTHON || 'python'
const env = {...process.env, BACKEND_DIR: temp, KEYWORD_DB_PATH: join(temp, 'research.sqlite'),
  VALIDATION_DB_PATH: join(temp, 'ledger.sqlite'), APP_KEYWORD_FEED_ROOT: join(temp, 'native'),
  APP_KEYWORD_FEED_ENABLED: '0', APP_PRODUCTION_ENABLED: '0', AUTO_START_SCHEDULER: '0', PIPELINE_API_TOKEN: '',
  SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: ''}
const fixture = spawnSync(python, ['-c', `
from pathlib import Path
from contextlib import closing
import sqlite3,json,os
from services import selling_discovery as f
from services.selling_discovery_worker import cycle
from models.selling_products import Listing, Observation, Review, Packet
r=Path(os.environ['APP_KEYWORD_FEED_ROOT']);p=r/'data/catalog.sqlite';p.parent.mkdir(parents=True)
(r/'installation.json').write_text(json.dumps({'database':str(p)}))
with sqlite3.connect(p) as c:
 c.execute('CREATE TABLE keyword_listing_snapshots(id INTEGER PRIMARY KEY,listing_id TEXT,title TEXT,keyword TEXT,shop_name TEXT,observed_at TEXT,price REAL,currency_code TEXT,favorites INTEGER,review_count INTEGER,collection_run_id TEXT)')
 c.executemany('INSERT INTO keyword_listing_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)',[(i,str(100+i),('Focus product ' if i<=3 else 'Other product ')+str(i),'teacher planner','Fixture shop',f.now().isoformat(),8,'USD',i,None,'isolated-fixture') for i in range(1,26)])
cycle()
with closing(f.connect()) as c,c:
 for i in (1,2):
  ident=str(100+i)
  listing=Listing(listing_id=ident,title='Focus product '+str(i),url='https://www.etsy.com/listing/'+ident,source_ref='Isolated fixture listing')
  obs=[Observation(listing_id=ident,metric='purchase_message',value=12,observed_at=f.now(),source='etsy_public',source_ref=listing.url,unit='buyers',raw_message='12 people bought this in the past 24 hours')] if i==1 else []
  reviews=[Review(review_id='fixture-review',listing_id=ident,reviewed_on=f.now().date(),rating=2,text='Please add larger writing areas and a worked example.',source_ref='Isolated public review')] if i==2 else []
  f._upsert(c,Packet(listings=[listing],observations=obs,reviews=reviews).model_dump(mode='json'),'teacher planner',f.now().isoformat())
`], {cwd: resolve('backend'), env, encoding: 'utf8'})
assert.equal(fixture.status, 0, fixture.stderr)
const backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'pipe'})
let log = ''; backend.stderr.on('data', chunk => {log += chunk.toString()})
let browser, page
try {
  let ready = false
  for (let i = 0; i < 60; i++) {try {if ((await fetch(`${api}/api/health`)).ok) {ready = true; break}} catch {} await delay(500)}
  assert(ready, log)
  browser = await chromium.launch({headless: true}); page = await browser.newPage(); const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'}/selling`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  await page.getByText('25 indexed listings', {exact: false}).waitFor()
  const list = page.getByRole('list', {name: 'Discovered listings'})
  assert.equal(await list.getByRole('listitem').count(), 20)
  await page.getByRole('button', {name: 'Next products'}).click()
  await page.getByText('21–25 of 25', {exact: false}).waitFor()
  assert.equal(await list.getByRole('listitem').count(), 5)
  await page.getByLabel('Activity evidence').selectOption('purchase_report')
  await page.getByText('1–1 of 1', {exact: false}).waitFor()
  await list.getByText('Recent purchase report', {exact: true}).waitFor()
  await page.getByLabel('Activity evidence').selectOption('review_activity')
  await list.getByText('Recent review activity · purchase timing unknown', {exact: true}).waitFor()
  await page.getByLabel('Activity evidence').selectOption('unknown')
  await page.getByText('1–20 of 24', {exact: false}).waitFor()
  assert.equal(await list.getByText('Recent purchase report', {exact: true}).count(), 0)
  await page.getByLabel('Activity evidence').selectOption('all')
  await page.getByLabel('Search products, shops or keywords').fill('Focus product')
  await page.getByText('1–3 of 3', {exact: false}).waitFor()
  await page.getByRole('button', {name: 'Refresh discovery', exact: true}).click()
  await page.getByText('Refresh queued.', {exact: false}).waitFor()
  await mkdir('.impeccable/review', {recursive: true})
  await mkdir('work/ui-discovery', {recursive: true})
  const responsive = []
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 950}); await page.evaluate(() => window.scrollTo(0, 0))
    await delay(200)
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow ${width}`)
    const action = list.getByRole('button', {name: 'Investigate Focus product 1', exact: true})
    await action.focus(); assert(await action.evaluate(el => el === document.activeElement))
    const ratio = await action.evaluate(el => {
      const c = getComputedStyle(el); const lum = s => {const rgb = s.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4}); return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]}
      const a = lum(c.color), b = lum(c.backgroundColor); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
    })
    assert(ratio >= 4.5, `Action contrast ${width}: ${ratio}`)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({path: `work/ui-discovery/${width}.png`, fullPage: true})
    if (width === 320 || width === 1440) await page.screenshot({path: `.impeccable/review/${width === 320 ? 'mobile' : 'desktop'}.png`, fullPage: true})
    responsive.push({width, action_contrast: ratio})
  }
  await list.getByRole('button', {name: 'Investigate Focus product 1', exact: true}).press('Enter')
  await page.getByRole('heading', {name: 'Focus product 1', exact: true}).waitFor()
  const overview = await (await fetch(`${api}/api/selling-products`)).json()
  assert.equal(overview.items.length, 1)
  const discovery = await (await fetch(`${api}/api/selling-products/discovery?q=Focus%20product%201`)).json()
  const item = discovery.items[0]
  const repeat = await fetch(`${api}/api/selling-products/discovery/101/investigate`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({expected_fingerprint: item.fingerprint})})
  assert.equal(repeat.status, 200)
  assert.equal((await repeat.json()).id, overview.items[0].id)
  await page.getByRole('button', {name: 'sales model', exact: true}).click()
  await page.getByText('12 people bought this in the past 24 hours', {exact: false}).first().waitFor()
  assert.deepEqual(errors, [])
  await writeFile('work/ui-discovery/verification.json', JSON.stringify({isolated: true, fixture_directory: temp, responsive, pagination: true, evidence_filters: true, keyboard_promotion: true, idempotent: true, sales_model_evidence: true}, null, 2))
  console.log('Discovery UI: pagination, evidence filters, unknown sales, refresh, 4 widths, keyboard/contrast, idempotent promotion and sales-model evidence passed.')
} catch (error) {
  await mkdir('work/ui-discovery', {recursive: true})
  if (page) {await page.screenshot({path: 'work/ui-discovery/failure.png', fullPage: true}); await writeFile('work/ui-discovery/failure.txt', await page.locator('body').innerText())}
  console.error(log.slice(-2500)); throw error
} finally {
  if (browser) await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], {stdio: 'ignore'})
  else backend.kill()
}

// Real isolated API + ledger + production UI. No live providers or user data.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'

const temp = await mkdtemp(join(tmpdir(), 'etgen-supported-qa-'))
const socket = net.createServer()
await new Promise(done => socket.listen(0, '127.0.0.1', done))
const port = socket.address().port
await new Promise(done => socket.close(done))
const api = `http://127.0.0.1:${port}`
const python = process.env.VALIDATION_QA_PYTHON || 'python'
const env = {...process.env, BACKEND_DIR: temp, KEYWORD_DB_PATH: join(temp, 'research.sqlite'),
  VALIDATION_DB_PATH: join(temp, 'ledger.sqlite'), AUTO_START_SCHEDULER: '0', APP_KEYWORD_FEED_ENABLED: '0',
  SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: '', ETSY_API_KEYSTRING: '', ETSY_SHARED_SECRET: ''}
const seed = spawnSync(python, ['-c', `
from datetime import datetime,timezone,timedelta
from pipeline import keyword_database as db
from services import supported_keywords as support
db.init_db()
at=datetime.now(timezone.utc)-timedelta(minutes=1)
with db._conn() as con:
 support.refresh(con,at-timedelta(minutes=1))
 con.execute("INSERT INTO seeds VALUES('teacher mug','product','qa',?)",(at.isoformat(),))
 for source,metric,value,geo in [('etsy_open_api','listing_count',12,None),('google_ads_keyword_planner','monthly_searches',1000,'US')]:
  con.execute("INSERT INTO keyword_observations(keyword,source,observed_at,metric,value,unit,geography,period_start,period_end,collection_run_id) VALUES('teacher mug',?,?,?,?,'count',?,?,?,'qa-run')",(source,at.isoformat(),metric,value,geo,(at-timedelta(days=365)).date().isoformat(),(at-timedelta(days=30)).date().isoformat()))
 for i in range(12):
  con.execute("INSERT INTO keyword_listing_snapshots(keyword,source,observed_at,listing_id,title,shop_name,collection_run_id,price,currency_code) VALUES('teacher mug','etsy_open_api',?,?,'Personalized teacher mug','qa-shop','qa-run',18.5,'USD')",(at.isoformat(),str(i)))
 support.refresh(con,at)
`], {cwd: resolve('backend'), env, encoding: 'utf8'})
assert.equal(seed.status, 0, seed.stderr)
const backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'pipe'})
let browser
try {
  let ready = false
  for (let i = 0; i < 60; i++) {
    try {if ((await fetch(`${api}/api/product-validation/supported-keywords`)).ok) {ready = true; break}} catch { /* boot */ }
    await delay(500)
  }
  assert(ready, 'Isolated API must start')
  browser = await chromium.launch({headless: true})
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'}/validation`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  await page.getByRole('heading', {name: 'Supported keywords → product drafts'}).waitFor()
  await page.getByRole('button', {name: 'Prepare product', exact: true}).click()
  await page.getByLabel('Descriptive product name').fill('Personalized Ceramic Teacher Mug')
  await page.getByPlaceholder('Ceramic mug, door hanger, printable…').fill('mug')
  await page.getByLabel('Product details', {exact: true}).fill('A teacher mug personalized with the chosen name.')
  await page.getByLabel('Material · if applicable').fill('ceramic')
  await page.getByLabel('I checked that this actual product matches the selected buyer keyword.').check()
  await page.getByRole('button', {name: 'Save listing draft and product concept'}).click()
  await page.getByText('Draft saved. Use the product concept below', {exact: false}).waitFor()
  const response = await fetch(`${api}/api/product-validation/supported-keywords`)
  const goal = await response.json()
  assert.equal(goal.qualified_this_month, 1)
  assert.equal(goal.drafts.length, 1)
  assert.equal(goal.drafts[0].audit.can_publish, false)
  assert.equal(goal.drafts[0].facts.price, null)
  await page.getByText('Saved listing drafts · 1', {exact: true}).click()
  await page.getByRole('button', {name: 'Export draft for review'}).focus()
  const downloaded = page.waitForEvent('download')
  await page.keyboard.press('Enter')
  await downloaded
  await mkdir('work/ui-supported-keywords', {recursive: true})
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 1000})
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `No page overflow at ${width}`)
    await page.screenshot({path: `work/ui-supported-keywords/${width}.png`, fullPage: true})
  }
  assert.deepEqual(errors, [])
  console.log('Supported keyword UI: actual draft save/export, unknown costs, keyboard action and four responsive widths passed.')
} finally {
  if (browser) await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], {stdio: 'ignore'})
  else backend.kill()
}

// Real private API/worker/files; isolated data and no live marketplace providers.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'
const temp = await mkdtemp(join(tmpdir(), 'etgen-production-qa-'))
const socket = net.createServer(); await new Promise(done => socket.listen(0, '127.0.0.1', done))
const port = socket.address().port; await new Promise(done => socket.close(done))
const api = `http://127.0.0.1:${port}`
const env = {...process.env, BACKEND_DIR: temp, KEYWORD_DB_PATH: join(temp, 'research.sqlite'),
  VALIDATION_DB_PATH: join(temp, 'ledger.sqlite'), PRODUCTION_ROOT: join(temp, 'production'),
  APP_PRODUCTION_ENABLED: '1', APP_KEYWORD_FEED_ENABLED: '0', AUTO_START_SCHEDULER: '0',
  SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: '',
  PRODUCTION_OLLAMA_URL: 'http://127.0.0.1:9', PRODUCTION_COMFY_URL: 'http://127.0.0.1:9'}
const backend = spawn(process.env.VALIDATION_QA_PYTHON || 'python', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'pipe'})
let browser
try {
  let ready = false
  for (let i = 0; i < 60; i++) {try {if ((await fetch(`${api}/api/health`)).ok) {ready = true; break}} catch {} await delay(500)}
  assert(ready)
  browser = await chromium.launch({headless: true}); const page = await browser.newPage(); const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'}/validation`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  await page.getByRole('heading', {name: 'Production queue', exact: true}).waitFor()
  await page.getByRole('button', {name: 'Create product specification'}).click()
  const form = page.getByRole('form', {name: 'Production specification'})
  await form.getByLabel('Product name', {exact: true}).fill('Workday Planning Sheets')
  await form.getByLabel('Buyer keyword', {exact: true}).fill('work day planner')
  await form.getByLabel('Buyer', {exact: true}).fill('People planning a workday')
  await form.getByLabel('Purpose and promised contents').fill('Printable writing areas for priorities, appointments and daily notes.')
  await form.getByLabel('Original content', {exact: false}).fill('Monday\nTuesday')
  await form.getByLabel('Actual selling price').fill('8')
  await form.getByLabel('Total variable cost').fill('1')
  await form.getByLabel('Verified Etsy taxonomy ID').fill('123')
  await form.getByLabel('Delivery, processing and return terms').fill('Download the PDF. Contact seller for support.')
  await form.getByLabel('Artwork and content rights provenance').fill('Original authored template and customer content.')
  await form.getByLabel('Thirteen curated tags').fill('work planner,daily planner,weekly planner,work week,work notes,daily notes,planner pages,planning pdf,planner download,priority planner,work priorities,daily schedule,work schedule')
  await form.getByRole('button', {name: 'Queue product revision', exact: true}).click()
  await page.getByRole('heading', {name: 'Actual file checks'}).waitFor({timeout: 60000})
  const jobs = await (await fetch(`${api}/api/production`)).json()
  assert.equal(jobs.jobs.length, 1); assert.equal(jobs.jobs[0].status, 'needs_review')
  assert.equal(jobs.jobs[0].spec.research.status, 'unvalidated_operator_concept')
  assert.equal((await fetch(`${api}/api/production/jobs/${jobs.jobs[0].id}/files/customer.pdf`)).status, 200)
  const review = page.getByRole('form', {name: 'Review production files'})
  for (const checkbox of await review.getByRole('checkbox').all()) await checkbox.check()
  await review.getByLabel('Review note').fill('Inspected actual customer PDF, wording, rights and factual product details.')
  await review.getByRole('button', {name: 'Approve exact package'}).click()
  await page.getByRole('button', {name: 'Export approved package'}).waitFor()
  await page.getByRole('button', {name: 'Export approved package'}).focus(); await page.keyboard.press('Enter')
  await delay(1000)
  const after = await (await fetch(`${api}/api/production`)).json()
  assert.equal(after.jobs[0].status, 'exported')
  await mkdir('work/ui-production', {recursive: true})
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 1000})
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `No overflow at ${width}`)
    await page.screenshot({path: `work/ui-production/${width}.png`, fullPage: true})
  }
  assert.deepEqual(errors, [])
  console.log('Production UI: actual PDF generation, private files, approval, keyboard export, four responsive widths passed.')
} finally {
  if (browser) await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], {stdio: 'ignore'})
  else backend.kill()
}

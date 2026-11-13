// Full research-to-original-PDF workflow. All records and files are isolated fixtures.
import assert from 'node:assert/strict'
import {spawn, spawnSync} from 'node:child_process'
import {mkdtemp, mkdir, readFile, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'
import {chromium} from 'playwright'

const temp = await mkdtemp(join(tmpdir(), 'etgen-selling-qa-'))
const socket = net.createServer(); await new Promise(done => socket.listen(0, '127.0.0.1', done))
const port = socket.address().port; await new Promise(done => socket.close(done))
const api = `http://127.0.0.1:${port}`
const env = {...process.env, BACKEND_DIR: temp, KEYWORD_DB_PATH: join(temp, 'research.sqlite'),
  VALIDATION_DB_PATH: join(temp, 'ledger.sqlite'), PRODUCTION_ROOT: join(temp, 'production'),
  APP_KEYWORD_FEED_ROOT: join(temp, 'absent-feed'), APP_PRODUCTION_ENABLED: '1',
  APP_KEYWORD_FEED_ENABLED: '0', AUTO_START_SCHEDULER: '0', PIPELINE_API_TOKEN: '',
  SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: '',
  PRODUCTION_OLLAMA_URL: 'http://127.0.0.1:9', PRODUCTION_COMFY_URL: 'http://127.0.0.1:9'}
const backend = spawn(process.env.VALIDATION_QA_PYTHON || 'python', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'pipe'})
let log = ''; backend.stderr.on('data', chunk => { log += chunk.toString() })
const day = days => new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
const observation = (id, value, days) => ({listing_id: id, metric: 'estimated_sales', value,
  basis: 'period', observed_at: new Date(Date.now() - days * 86400000).toISOString(),
  period_start: day(days + 6), period_end: day(days), source: 'manual', source_ref: 'Isolated fixture report'})
const packet = {listings: ['one', 'two'].map((id, index) => ({listing_id: id, title: 'Weekly Teacher Planner',
  shop: `Fixture shop ${index + 1}`, tags: ['teacher planner'], source_ref: 'Isolated fixture listing'})),
  observations: [observation('one', 20, 8), observation('one', 30, 1), observation('two', 16, 1),
    {...observation('one', 1500, 1), metric: 'keyword_searches', keyword: 'teacher planner', geography: 'US', source: 'google_ads'}],
  reviews: ['one', 'two'].map(id => ({listing_id: id, review_id: `review-${id}`, reviewed_on: day(2), rating: 2,
    text: 'I wish the font was larger and readable, and the instructions were clearer.', source_ref: 'Isolated fixture review'})),
  patterns: ['one', 'two'].map(id => ({listing_id: id, typography: 'sans_serif', layout: 'structured',
    features: ['weekly grid', 'letter'], readability: 2, source_ref: 'Isolated operator inspection'}))}
let browser, page
try {
  let ready = false
  for (let i = 0; i < 60; i++) {try {if ((await fetch(`${api}/api/health`)).ok) {ready = true; break}} catch {} await delay(500)}
  assert(ready, log)
  browser = await chromium.launch({headless: true}); page = await browser.newPage(); const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const origin = process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'
  await page.goto(`${origin}/selling`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  await page.getByRole('heading', {name: 'Opportunity watchlist'}).waitFor()
  await page.getByRole('button', {name: 'New opportunity'}).click()
  const create = page.getByRole('form', {name: 'New selling-product opportunity'})
  await create.getByLabel('Opportunity name').fill('Teacher planning opportunity')
  await create.getByLabel('Buyer keyword').fill('teacher planner')
  await create.getByLabel('Product family').selectOption('planner')
  await create.getByRole('button', {name: 'Save opportunity', exact: true}).click()
  await page.getByRole('heading', {name: 'Teacher planning opportunity', exact: true}).waitFor()
  await page.getByText('Needs evidence', {exact: false}).first().waitFor()
  await page.getByRole('button', {name: 'evidence', exact: true}).click()
  await page.getByText('Import a research file', {exact: true}).click()
  await page.getByLabel('Research data').fill('{broken')
  await page.getByRole('button', {name: 'Preview import', exact: true}).click()
  await page.getByRole('alert').filter({hasText: 'JSON'}).waitFor()
  await page.getByLabel('Research data').fill(JSON.stringify(packet))
  await page.getByRole('button', {name: 'Preview import', exact: true}).click()
  await page.getByRole('heading', {name: 'Review this import'}).waitFor()
  const get = path => fetch(`${api}/api/selling-products${path}`).then(r => r.json())
  const watchlist = await get(''); const id = watchlist.items[0].id
  assert.equal((await get(`/opportunities/${id}`)).record_count, 1, 'Preview must not write')
  await page.getByRole('button', {name: 'Import reviewed evidence', exact: true}).click()
  await page.getByText('Evidence saved locally.', {exact: false}).waitFor()
  let detail = await get(`/opportunities/${id}`)
  assert.equal(detail.analysis.independent_selling_shops, 2)
  assert(Object.values(detail.analysis.methods).every(method => method.status === 'available'))
  const count = detail.record_count
  await page.getByLabel('Research data').fill(JSON.stringify(packet))
  await page.getByRole('button', {name: 'Preview import', exact: true}).click()
  await page.getByText(`0 new records · 0 corrections · ${count - 1} duplicates`).waitFor()
  await page.getByRole('button', {name: 'Import reviewed evidence', exact: true}).click()
  await page.getByText('Evidence saved locally.', {exact: false}).waitFor()
  assert.equal((await get(`/opportunities/${id}`)).record_count, count)
  await page.getByRole('button', {name: 'analysis', exact: true}).click()
  await page.getByRole('heading', {name: 'Recent period figures', exact: true}).waitFor()
  await page.getByRole('button', {name: 'Momentum Available', exact: true}).focus(); await page.keyboard.press('Enter')
  await page.getByText('20 → 30 · Change: 10', {exact: true}).waitFor()
  await page.getByRole('button', {name: 'Buyer feedback Available', exact: true}).click()
  await page.getByRole('heading', {name: 'readability · Repeated across listings', exact: true}).waitFor()
  await page.getByRole('button', {name: 'Keywords Available', exact: true}).click()
  await page.getByRole('cell', {name: /1,500/}).waitFor()
  await page.getByRole('button', {name: 'Product patterns Available', exact: true}).click()
  await page.getByRole('table', {name: 'Manually inspected design attributes'}).waitFor()
  await mkdir('work/ui-selling', {recursive: true})
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 1000})
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `No overflow at ${width}`)
    await page.screenshot({path: `work/ui-selling/${width}.png`, fullPage: true})
  }
  await page.setViewportSize({width: 1440, height: 1000})
  // Exercise model inputs through the actual forms, in this isolated ledger only.
  await page.getByRole('button', {name: 'evidence', exact: true}).click()
  await page.getByRole('button', {name: 'observations', exact: true}).click()
  const observationForm = page.getByRole('form', {name: 'Record observations'})
  await observationForm.getByLabel('Metric').selectOption('purchase_message')
  await observationForm.getByLabel('Original purchase message', {exact: true}).fill('In 20 carts')
  await observationForm.getByLabel('Saved report, source URL or inspection reference').fill('Isolated Etsy message fixture')
  await observationForm.getByRole('button', {name: 'Save observation', exact: true}).click()
  await page.getByRole('alert').filter({hasText: 'Message not recognized'}).waitFor()
  await observationForm.getByLabel('Original purchase message', {exact: true}).fill('7 people bought this in the past 24 hours')
  await observationForm.getByRole('button', {name: 'Save observation', exact: true}).click()
  await page.getByText('Source record saved.', {exact: false}).waitFor()
  const messageDetail = await get(`/opportunities/${id}`)
  assert.equal(messageDetail.evidence.observations.find(r => r.metric === 'purchase_message').unit, 'buyers')
  await page.getByRole('button', {name: 'sales model', exact: true}).click()
  await page.getByRole('heading', {name: 'EtGen sales model', exact: true}).waitFor()
  assert(await page.getByText('Insufficient evidence', {exact: true}).count())
  await page.getByText('Model assumptions', {exact: true}).click()
  const assumptions = page.getByRole('form', {name: 'Sales model assumptions'})
  await assumptions.getByLabel('Comparable baseline · purchases/day', {exact: true}).fill('3')
  await assumptions.getByLabel('Purchases per displayed buyer · 1 or more', {exact: true}).fill('1')
  await assumptions.getByLabel('Basis for these assumptions', {exact: true}).fill('Synthetic baseline and buyer conversion for this isolated browser test.')
  await assumptions.getByRole('button', {name: 'Save model assumptions', exact: true}).click()
  await page.getByText('Assumptions saved.', {exact: false}).waitFor()
  await page.getByRole('button', {name: 'Past 30 days', exact: true}).focus(); await page.keyboard.press('Enter')
  assert.equal(await page.getByRole('button', {name: 'Past 30 days', exact: true}).getAttribute('aria-pressed'), 'true')
  const periodButton = page.getByRole('button', {name: 'Past 30 days', exact: true})
  for (const hover of [false, true]) {
    if (hover) await periodButton.hover(); else await page.mouse.move(0, 0)
    await delay(200) // Shared buttons animate colors for 150 ms; measure settled states.
    const ratio = await periodButton.evaluate(button => {
      const style = getComputedStyle(button)
      const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0)
      const a = luminance(style.color), b = luminance(style.backgroundColor)
      return (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
    })
    assert(ratio >= 4.5, `Period button contrast (${hover ? 'hover' : 'default'}): ${ratio}`)
  }
  await page.mouse.move(0, 0)
  await page.getByText('Calibration and held-out results', {exact: true}).click()
  await page.getByRole('button', {name: 'Fit and evaluate model', exact: true}).click()
  await page.getByRole('alert').filter({hasText: '32 completed'}).waitFor()
  await page.getByText('Calibration and held-out results', {exact: true}).click()
  await page.getByText('Model assumptions', {exact: true}).click()
  await mkdir('work/ui-sales-model', {recursive: true})
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 1000})
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Model overflow at ${width}`)
    await page.screenshot({path: `work/ui-sales-model/${width}.png`, fullPage: true})
  }
  await page.setViewportSize({width: 1440, height: 1000})
  await page.getByRole('button', {name: 'improvement brief', exact: true}).click()
  const brief = page.getByRole('form', {name: 'Original improvement brief'})
  await brief.getByLabel('Original product name').fill('Clear Week Teaching Planner')
  await brief.getByLabel('Intended buyer').fill('Teachers planning a weekly timetable')
  await brief.getByLabel('Purpose and buyer task').fill('Organize weekly teaching priorities with usable writing areas and clear instructions.')
  await brief.getByLabel('Specific improvements').fill('Larger print and writing spaces\nClear original instructions')
  await brief.getByLabel('Your original design direction').fill('Create an original spacious weekly grid with a distinct heading system and authored examples.')
  await brief.getByRole('button', {name: 'Save original brief', exact: true}).click()
  await page.getByRole('link', {name: 'Review in production', exact: true}).waitFor()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', {name: 'Export evidence', exact: true}).click()
  const download = await downloaded; const file = join(temp, 'evidence.json'); await download.saveAs(file)
  const exported = JSON.parse(await readFile(file, 'utf8'))
  assert.equal(exported.can_publish, false); assert(exported.checksum)
  await page.getByRole('link', {name: 'Review in production', exact: true}).click()
  await page.getByRole('button', {name: 'Review selling-product specification', exact: true}).click()
  const form = page.getByRole('form', {name: 'Production specification'})
  assert.equal(await form.getByLabel('Product name', {exact: true}).inputValue(), 'Clear Week Teaching Planner')
  assert.equal(await form.getByLabel('Original content', {exact: false}).inputValue(), '')
  assert.equal(await form.getByLabel('Actual selling price').inputValue(), '')
  await form.getByLabel('Original content', {exact: false}).fill('Teaching priorities\nWeekly timetable\nReflections')
  await form.getByLabel('Actual selling price').fill('8')
  await form.getByLabel('Total variable cost').fill('1')
  await form.getByLabel('Verified Etsy taxonomy ID').fill('123')
  await form.getByLabel('Delivery, processing and return terms').fill('PDF digital download. Contact the seller for support.')
  await form.getByLabel('Artwork and content rights provenance').fill('Original authored contents and template for this isolated test.')
  await form.getByLabel('Thirteen curated tags').fill('teacher planner,weekly planner,lesson planner,teacher notes,class schedule,school planner,weekly schedule,teaching notes,class planner,planner pages,lesson notes,weekly teaching,teacher worksheet')
  await form.getByRole('button', {name: 'Queue product revision', exact: true}).click()
  await page.getByRole('heading', {name: 'Actual file checks'}).waitFor({timeout: 60000})
  const jobs = await (await fetch(`${api}/api/production`)).json()
  assert.equal(jobs.jobs.length, 1, log)
  assert.equal(jobs.jobs[0].spec.research.selling_products.selling_opportunity, id)
  assert.equal(jobs.jobs[0].spec.research.selling_products.qualification_credit, false)
  assert.equal((await fetch(`${api}/api/production/jobs/${jobs.jobs[0].id}/files/customer.pdf`)).status, 200)
  detail = await get(`/opportunities/${id}`)
  await writeFile('work/ui-selling/verification.json', JSON.stringify({isolated: true, methods: Object.keys(detail.analysis.methods), responsive: [320, 768, 1024, 1440], fixture_directory: temp, original_pdf: true}, null, 2))
  assert.deepEqual(errors, [])
  console.log('Selling products UI: sales model, parsed purchase evidence, explicit assumptions, calibration guard, keyboard/4 widths, five methods, preservation, export and original PDF handoff passed.')
} catch (error) {
  await mkdir('work/ui-selling', {recursive: true})
  if (page) { await page.screenshot({path: 'work/ui-selling/failure.png', fullPage: true}); await writeFile('work/ui-selling/failure.txt', await page.locator('body').innerText()) }
  console.error(log.slice(-3500)); throw error
} finally {
  if (browser) await browser.close()
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], {stdio: 'ignore'})
  else backend.kill()
}

// Exercise the real forms against an isolated backend ledger; no marketplace writes.
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
import {chromium} from 'playwright'

const origin = process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:5174'
const api = process.env.VALIDATION_QA_API
if (!api || !new URL(api).hostname.match(/^(127\.0\.0\.1|localhost)$/)) throw new Error('An isolated loopback QA API is required')
await mkdir('work/validation-qa', {recursive: true})
const browser = await chromium.launch({headless: true})
const context = await browser.newContext({serviceWorkers: 'block'})
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))
const today = new Date().toISOString().slice(0, 10)
try {
  await page.goto(`${origin}/validation`)
  await page.getByLabel('Research server address').fill(api)
  await page.getByRole('button', {name: 'Connect workspace'}).click()
  await page.getByLabel('Product concept', {exact: true}).first().fill('QA teacher tote')
  await page.getByLabel('Product type', {exact: true}).fill('tote')
  await page.getByLabel('Buyer keywords').fill('teacher tote')
  await page.getByRole('button', {name: 'Create validation queue'}).click()
  await page.getByRole('heading', {name: 'QA teacher tote', exact: true}).waitFor()
  await page.reload()
  await page.getByRole('heading', {name: 'QA teacher tote', exact: true}).waitFor()
  await page.getByLabel('Period start', {exact: true}).fill(today)
  await page.getByLabel('Period end', {exact: true}).fill(today)
  await page.getByLabel('Etsy searches', {exact: true}).fill('500')
  await page.getByLabel('Competing listings', {exact: true}).fill('1000')
  await page.getByLabel('Source note or saved evidence reference').fill('Synthetic QA evidence')
  await page.getByRole('button', {name: 'Save evidence'}).click()
  await page.getByText('500 / 1,000', {exact: false}).waitFor()
  await page.getByRole('button', {name: 'Competitors', exact: true}).click()
  await page.getByLabel('Sample source', {exact: true}).fill('Synthetic QA')
  await page.getByLabel('Search filters and relevance review').fill('Reviewed comparable QA products')
  await page.getByLabel('I reviewed these samples').check()
  const samples = 'listing_id,shop_id,title,price,currency\n' + Array.from({length: 20}, (_, i) => `${i},shop${i % 5},Teacher tote,25,USD`).join('\n')
  await page.getByLabel('Competitor CSV').fill(samples)
  await page.getByRole('button', {name: 'Save evidence'}).click()
  await page.getByText('20 listings · 5 shops').waitFor()
  await page.getByRole('button', {name: 'Costs', exact: true}).click()
  await page.getByLabel('Cost and fee sources').fill('Synthetic cost quotes')
  for (const scenario of ['conservative', 'base', 'optimistic']) {
    await page.getByLabel(`${scenario} Sale price`, {exact: true}).fill('25')
    for (const field of ['Production', 'Shipping', 'Packaging', 'Marketplace and payment fees', 'Advertising', 'Refund allowance', 'Variable labor', 'Design and setup', 'Monthly fixed expenses']) {
      await page.getByLabel(`${scenario} ${field}`, {exact: true}).fill(field === 'Design and setup' ? '90' : '1')
    }
  }
  await page.getByRole('button', {name: 'Save evidence'}).click()
  await page.getByText('Ready for a controlled test', {exact: true}).waitFor()
  await page.getByRole('button', {name: 'Outcomes', exact: true}).click()
  await page.getByLabel('Your shop ID', {exact: true}).fill('qa-shop')
  await page.getByLabel('Your listing ID', {exact: true}).fill('qa-listing')
  await page.getByLabel('Results period start').fill(today)
  await page.getByLabel('Results period end').fill(today)
  await page.getByLabel('Results source', {exact: true}).fill('Synthetic results')
  await page.getByLabel('Observed orders', {exact: true}).fill('3')
  await page.getByLabel('Observed revenue', {exact: true}).fill('75')
  await page.getByRole('button', {name: 'Save evidence', exact: true}).click()
  await page.getByRole('heading', {name: 'Observed test results · inconclusive'}).waitFor()
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({width, height: 1000})
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Page overflow at ${width}`)
    await page.screenshot({path: `work/validation-qa/outcomes-${width}.png`, fullPage: true})
  }
  const ledger = await (await fetch(`${api}/api/product-validation/export`)).json()
  assert.equal(ledger.payload.records.filter(row => row.kind === 'outcome').length, 1)
  assert.equal(errors.length, 0, errors.join('\n'))
  console.log('Real form flow passed: demand, competitors, costs, incomplete results, ledger export, and four responsive widths.')
} finally {await browser.close()}

// Synthetic UI contract fixtures only. No live backend, account or provider use.
import assert from 'node:assert/strict'
import {mkdir, writeFile} from 'node:fs/promises'
import {chromium} from 'playwright'

const origin = process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'
const api = origin
const at = '2026-10-27T20:00:00+00:00'
const window = {start: '2026-10-25T20:00:00+00:00', end: at, days: 2, counter_delta: 30}
const product = {listing_id: '123', title: 'Synthetic anchored planner', value: 12, low: 2, high: 22, status: 'ambiguous_allocation'}
const shop = {shop_id: '42', shop_label: 'Synthetic shop', status: 'experimental_allocation', window,
  products: [product, {...product, listing_id: '456', title: 'Synthetic second product', value: 8, low: 0, high: 17}],
  unobserved: {value: 10, low: 3, high: 28}, catalog_complete: false,
  issues: ['catalog_coverage_unknown', 'review_delay_assumed'], priority: [{listing_id: '123', reason: 'review_window_incomplete'}]}
let mode = 'valid'
const overview = () => ({summary: {at, shops: mode === 'empty' ? 0 : 1, anchored_shops: mode === 'valid' ? 1 : 0, allocated_products: mode === 'valid' ? 2 : 0},
  shops: mode === 'empty' ? [] : [{...shop, ...(mode === 'valid' ? {} : {status: mode === 'stale' ? 'stale_counter' : 'counter_conflict', window: null, products: [{...product, value: null, low: null, high: null, status: 'unknown'}]})}],
  assumptions: ['Synthetic review-rate and lag assumptions.'], schedule: 'Synthetic saved-evidence test; no provider calls.', accuracy: 'unvalidated', validation: {status: 'no_compatible_actual_outcomes', matched_cases: 0, mae: null}})
const browser = await chromium.launch({headless: true})
// Intercept only synthetic requests; a PWA worker would send its own requests
// outside page.route and could accidentally contact an actual local backend.
const page = await browser.newPage({serviceWorkers: 'block', viewport: {width: 1440, height: 1000}})
const errors = [], providerRequests = []
const requests = []
page.on('requestfailed', value => {if (value.url().includes('/api/')) requests.push({event:'failed', url:value.url(), error:value.failure()?.errorText})})
page.on('request', value => {if (value.url().includes('/api/')) requests.push({event:'request',method:value.method(),url:value.url()})})
page.on('response', value => {if (value.url().includes('/api/')) requests.push({event:'response',status:value.status(),url:value.url()})})
page.on('pageerror', error => errors.push(error.message))
page.on('request', request => {if (/https:\/\/(?:www\.)?(?:etsy|muadzo|ehunt|exto)\./.test(request.url())) providerRequests.push(request.url())})
await page.route(`${api}/api/**`, async route => {
  requests.push({event:'route',url:route.request().url()})
  const headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'content-type', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'}
  if (route.request().method() === 'OPTIONS') return route.fulfill({status: 204, headers})
  const path = new URL(route.request().url()).pathname
  let data
  if (path === '/api/selling-products') data = {items: []}
  else if (path === '/api/selling-products/discovery') data = {items: [], total: 0, page: 0, limit: 20, counts: {indexed: 0, purchase_reports: 0, review_activity: 0}, access: {status: 'recorded', scopes: []}, catalog: {}, last_run: null}
  else if (path === '/api/sales-intelligence/sources') data = {items: []}
  else if (path === '/api/sales-intelligence/estimates') data = {items: [], summary: {tracked: 2, estimated: 0, at}, assumptions: 'Synthetic review assumptions.', schedule: 'No provider calls.', panel_limit: 600}
  else if (path === '/api/sales-intelligence/anchored') {
    if (mode === 'error') return route.fulfill({status: 503, contentType: 'application/json', headers, body: JSON.stringify({detail: 'Synthetic temporary evidence read failure'})})
    data = overview()
  } else if (path.endsWith('/comparison')) data = {listing_id: '123', metadata: null, history: [], consensus: {cohorts: [], excluded: []}, student: {status: 'no_active_model', value: null}, outcome_model: {status: 'no_active_model', value: null}, independent_model: {status: 'needs_evidence', value: null}, shop_allocation: {...product, window, feasible_low: 0, feasible_high: 30}}
  else if (path === '/api/sales-intelligence') data = {items: [], total: 0, page: 0, limit: 20, source_count: 0, automated_provider_feeds: 0, coverage: {reference_listings: 0, observations: 0, outcomes: 0, models: 0, listings: 0, paused: false, worker: {status: 'disabled'}, catalog: {}}}
  else data = {status: 'queued'}
  return route.fulfill({contentType: 'application/json', headers, body: JSON.stringify(data)})
})
const open = async () => {
  await page.goto(`${origin}/selling`)
  await page.getByRole('heading', {name: 'Selling products', exact: true}).waitFor()
  const address = page.getByLabel('Research server address', {exact: true})
  await address.waitFor({state: 'attached'})
  if (!(await address.isVisible())) await page.getByText('Private research connection', {exact: true}).click()
  await address.fill(api)
  await page.getByRole('button', {name: 'Connect workspace', exact: true}).click()
  const intelligence = page.getByRole('region', {name: 'Sales intelligence', exact: true})
  await intelligence.getByRole('button', {name: 'Open sales intelligence', exact: true}).click()
  const button = intelligence.getByRole('button', {name: 'Shop-anchored allocations', exact: true})
  await button.focus(); await page.keyboard.press('Enter')
  assert.equal(await button.getAttribute('aria-pressed'), 'true')
  return intelligence.getByRole('region', {name: 'Shop-anchored allocations', exact: true})
}
try {
  const report = await open()
  await report.getByText('12 allocated counter increments', {exact: true}).waitFor()
  await report.getByText('2–22 sensitivity range', {exact: false}).waitFor()
  assert.equal(await report.getByText('Unresolved feasible range: 0–30 counter increments.', {exact: true}).count(), 2)
  await report.getByText('Observed shop-counter increase', {exact: true}).waitFor()
  await report.getByText('Unobserved-product allowance', {exact: true}).waitFor()
  await report.getByText('Product accuracy is unvalidated.', {exact: false}).waitFor()
  assert((await report.innerText()).includes('Catalog coverage incomplete or unverified'))
  const select = report.getByLabel('Inspect a shop', {exact: true})
  await select.focus(); assert(await select.evaluate(element => element === document.activeElement))
  await report.getByText('Evidence limits · 2', {exact: true}).focus(); await page.keyboard.press('Enter')
  await report.getByText('review delay assumed', {exact: true}).waitFor()
  await report.getByText('Evidence to improve next', {exact: true}).click()
  await report.getByText('Listing 123 · review window incomplete', {exact: true}).waitFor()
  await report.getByText('Method and collection limits', {exact: true}).click()
  await report.getByText('Individual range endpoints need not add up.', {exact: false}).waitFor()
  await mkdir('.impeccable/review', {recursive: true})
  for (const width of [1440, 1024, 768, 320]) {
    await page.setViewportSize({width, height: 1000})
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `shop allocation overflow at ${width}`)
    await report.screenshot({path: `.impeccable/review/shop-allocations-${width}.png`})
  }
  await report.getByRole('button', {name: 'Synthetic anchored planner', exact: true}).click()
  await page.getByRole('heading', {name: 'Listing 123', exact: true}).waitFor()
  await page.getByRole('region', {name: 'Selected product shop allocation', exact: true}).getByText('12 allocated counter increments', {exact: false}).waitFor()
  for (const state of ['empty', 'invalid', 'stale', 'error']) {
    mode = state
    const view = await open()
    if (state === 'empty') await view.getByText('No shop allocation is available yet.', {exact: false}).waitFor()
    else if (state === 'error') {
      await view.getByText('Synthetic temporary evidence read failure', {exact: true}).waitFor()
      mode = 'valid'; await view.getByRole('button', {name: 'Retry shop allocations', exact: true}).click()
      await view.getByText('12 allocated counter increments', {exact: true}).waitFor()
    } else {
      await view.getByText('Product allocations are unknown for this shop.', {exact: false}).waitFor()
      await view.getByText('Allocation unknown', {exact: true}).waitFor()
      assert.equal(await view.getByText('Observed shop-counter increase', {exact: true}).count(), 0)
    }
  }
  assert.deepEqual(errors, [])
  assert.deepEqual(providerRequests, [])
  await writeFile('.impeccable/review/shop-allocations-verification.json', JSON.stringify({synthetic: true, backend_requests: 'intercepted_fixtures_only', provider_requests: 0, keyboard: true, unknown_states: ['empty', 'invalid', 'stale', 'error_retry'], selected_product_comparison: true, responsive_widths: [1440, 1024, 768, 320]}, null, 2))
  console.log('Shop allocations UI passed: observed interval, uncertainty, missing catalog, unknown/error states, keyboard, product selection and four widths.')
} catch (error) {
  await mkdir('.impeccable/review', {recursive: true})
  await writeFile('.impeccable/review/shop-allocations-failure.txt', await page.locator('body').innerText())
  await writeFile('.impeccable/review/shop-allocations-requests.json', JSON.stringify(requests,null,2))
  console.error(errors)
  throw error
} finally {await browser.close()}

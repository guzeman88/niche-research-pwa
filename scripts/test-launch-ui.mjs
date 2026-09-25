// Browser regression test for the evidence-to-product workflow. No live account,
// provider, or marketplace mutation is used; every network boundary is mocked.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.LAUNCH_UI_ORIGIN || 'http://127.0.0.1:5173'
const now = '2026-09-25T12:00:00+00:00'
const decision = {
  keyword: 'teacher appreciation printable',
  product_type: 'digital_download',
  model_version: 'etgen-decision-v1.0.0',
  evaluated_at: now,
  status: 'advance',
  score: 74.2,
  confidence: 90,
  ready_to_advance: true,
  components: { demand: 77, market_balance: 58, contribution_margin: 88, sample_depth: 25 },
  evidence: {
    keyword: 'teacher appreciation printable', product_type: 'digital_download',
    market_pair: {
      source: 'etsy_marketplace_insights', geography: 'US', period_start: '2026-08-01', period_end: '2026-08-31',
      observed_at: '2026-08-31', demand: 1200, demand_metric: 'searches', demand_unit: 'searches',
      supply: 4500, supply_metric: 'listing_count', supply_unit: 'listings',
    },
    unit_economics: {
      source: 'launch cost worksheet', observed_at: now, product_type: 'digital_download', sale_price_usd: 18,
      production_cost_usd: 2, shipping_cost_usd: 0, marketplace_fees_usd: 3,
      advertising_cost_usd: 2, refund_allowance_usd: 1, contribution_profit_usd: 10,
    },
    listing_sample_count: 25,
    trend: { source: 'google_trends', point_count: 8, period_start: '2026-07-01', period_end: '2026-09-01', change_pct: 18 },
    outcome_period_count: 0,
    evidence_age_days: 25,
  },
  blockers: [],
  cautions: ['No own-shop outcome exists; this is a pre-launch decision, not a sales prediction.'],
  input_fingerprint: '8f9d2cd3f71b0bdb30a14f1aefb4cf55b293fce7f27c3dfdcf65ef219a35c132',
  model_notes: [
    'Demand and supply must share a provider and reporting period.',
    'Score weights: demand 35%, market balance 25%, contribution margin 30%, sample depth 10%.',
    'Confidence describes evidence completeness; it is not a probability of success.',
    'The score does not estimate revenue and must be reviewed by an operator before launch.',
  ],
  economics: { contribution_profit_usd: 10, contribution_margin_rate: 0.5556 },
}

await mkdir('work/launch-qa', { recursive: true })
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ serviceWorkers: 'block' })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))

await context.route('**/api/account/**', async route => {
  const request = route.request()
  const path = new URL(request.url()).pathname.replace('/api/account', '')
  if (path === '/session') {
    return route.fulfill({ json: {
      user: { id: 'launch-qa-user', email: 'qa@example.test' },
      profile: { id: 'launch-qa-user', display_name: 'QA Owner', business_name: 'EtGen QA', timezone: 'America/New_York', currency: 'USD', role: 'admin', created_at: now },
      mfa_required: false, recovery: false,
    } })
  }
  if (path === '/workspace' && request.method() === 'GET') return route.fulfill({ json: { payload: {}, revision: 1 } })
  if (path === '/workspace' && request.method() === 'POST') return route.fulfill({ json: { revision: 2 } })
  if (path === '/backend') {
    const body = request.postDataJSON()
    if (String(body.path).includes('/decision')) return route.fulfill({ json: decision })
    if (body.path === '/api/evidence/economics') return route.fulfill({ json: { status: 'recorded', contribution_profit_usd: 10 } })
    return route.fulfill({ status: 404, json: { detail: 'Unhandled QA backend route' } })
  }
  return route.fulfill({ status: 404, json: { error: 'Unhandled QA account route' } })
})
await context.route('**/api/keywords/search**', route => route.fulfill({ json: [{
  keyword: decision.keyword, domain: 'digital downloads', source: 'qa', added_at: now,
  scanned: true, evidence_status: 'verified', sampled_listing_count: 25,
}] }))

try {
  await page.goto(`${origin}/launch`)
  await page.getByRole('heading', { name: 'Launch Lab' }).waitFor()
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    await page.screenshot({ path: `work/launch-qa/keyword-${width}.png`, fullPage: true })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Keyword stage overflows at ${width}`)
  }

  await page.getByLabel('Exact keyword').fill(decision.keyword)
  await page.getByRole('button', { name: 'Open evidence record' }).click()
  await page.getByRole('heading', { name: 'Verify market evidence' }).waitFor()
  await page.screenshot({ path: 'work/launch-qa/evidence.png', fullPage: true })
  await page.getByRole('button', { name: 'Economics' }).click()
  await page.getByLabel('Sale price (USD)').fill('18')
  await page.getByLabel('Marketplace fees (USD)').fill('3')
  await page.getByRole('button', { name: 'Record economics and evaluate' }).click()
  await page.getByRole('heading', { name: 'Review the decision' }).waitFor()
  await page.getByLabel('Operator decision note').fill('Advance one digital product while preserving the pre-launch evidence boundary.')
  await page.getByText('I reviewed the source period').click()
  await page.getByRole('button', { name: 'Approve product development' }).click()
  await page.getByRole('heading', { name: 'Shape the product' }).waitFor()
  await page.waitForTimeout(900)
  await page.getByText('Workspace saved to your account', { exact: true }).waitFor()
  await page.screenshot({ path: 'work/launch-qa/product.png', fullPage: true })
  assert.ok(await page.getByRole('button', { name: 'Use this concept' }).count() >= 3)
  assert.deepEqual(errors, [])
  console.log('PASS: Launch Lab renders responsively and advances through keyword, evidence, economics, decision, and product gates.')
} catch (error) {
  await page.screenshot({ path: 'work/launch-qa/failure.png', fullPage: true })
  console.error(await page.locator('body').innerText())
  throw error
} finally {
  await browser.close()
}

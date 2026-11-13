// Responsive regression check for the live dashboard status contract.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.DASHBOARD_UI_ORIGIN || 'http://127.0.0.1:4173'
const generatedAt = new Date().toISOString()
const summary = {
  schema_version: 2,
  snapshot_version: 7,
  generated_at: generatedAt,
  data_status: 'healthy',
  input_fingerprint: 'dashboard-qa',
  source_watermarks: { observations_at: generatedAt, latest_collection_at:generatedAt },
  duration_ms: 21,
  stats: {
    attempted: 3251, successful: 3251, evidence_backed: 2822, failed: 0, no_data: 0, stale: 0,
    total_seeds: 30693, scanned: 3251, unscanned: 27442, total_scans: 394, coverage_pct: 10.6,
    avg_opportunity: null, avg_gap_score: null, breakout_count: 0, expansion_edges: 25422,
    top_gap_keyword: null, domains: [{ domain: 'discovered', cnt: 24246 }],
  },
  evidence: { versioned_scores: 0, versioned_gaps: 0, marketplace_insights_rows: 39, marketplace_insights_keywords: 14, shop_stats_rows: 0 },
  providers: [],
  delivery: { mode: 'live', refresh_interval_seconds: 60 },
  feed:{status:'needs_attention',last_completed:generatedAt,errors:['GoogleNeedsAttention']},
  coverage:{as_of:generatedAt,active_current_competition:2021,active_paired_keywords:152,providers:[{provider:'etsy_open_api',attempts:1996,useful_attempts:1900,failed_attempts:1}]},
  sources:[{source:'etsy_marketplace_insights',rows:39,keywords:14,latest:generatedAt}],
  supported:{status:'tracking',target:3000,qualified_this_month:0,available_supported_groups:0},
  intelligence:{status:'provisional_estimates_not_verified_sales',listings:2617148,observations:0,outcomes:0,automatic_estimator:{tracked:600,estimated:514}},
  production:{status:'connected',jobs:0,review_queue:0,starting_recipes:7},
  validation:{records:178,projects:3},
  score_distribution:[],research_leads:[],breakouts:{status:'not_available',items:[],reason:'A comparable-window detector has not been validated.'},
}

await mkdir('work/dashboard-qa', { recursive: true })
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ serviceWorkers: 'block' })
await context.route('**/api/account/**', async route => {
  const path = new URL(route.request().url()).pathname.replace('/api/account', '')
  if (path === '/session') return route.fulfill({ json: {
    user: { id: 'dashboard-qa', email: 'qa@example.test' },
    profile: { id: 'dashboard-qa', display_name: 'QA Owner', business_name: 'EtGen QA', timezone: 'America/New_York', currency: 'USD', role: 'admin' },
    mfa_required: false, recovery: false,
  } })
  if (path === '/workspace' && route.request().method() === 'GET') return route.fulfill({ json: { payload: {}, revision: 1, updated_at: generatedAt } })
  if (path === '/workspace' && route.request().method() === 'POST') return route.fulfill({ json: { payload: {}, revision: 2, updated_at: generatedAt } })
  if (path === '/dashboard/summary' || path === '/dashboard/refresh') return route.fulfill({ json: summary })
  if (path === '/backend') return route.fulfill({ status: 503, json: { error: 'Not needed for dashboard QA.' } })
  return route.fulfill({ status: 404, json: { error: 'Unhandled dashboard QA route.' } })
})
const page = await context.newPage()
const errors = []
const staticRequests=[]
page.on('request',request=>{if(/\/data\/(opportunities|gaps|reports|breakouts)\.json/.test(request.url()))staticRequests.push(request.url())})
page.on('pageerror', error => errors.push(error.message))
try {
  await page.goto(origin)
  await page.getByRole('heading', { name: 'Dashboard' }).waitFor()
  await page.getByRole('heading',{name:'Connected to active research'}).waitFor()
  await page.getByRole('heading',{name:'Collection status'}).waitFor()
  await page.getByText('2,617,148 saved listing identities.',{exact:true}).waitFor()
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    await page.screenshot({ path: `work/dashboard-qa/dashboard-${width}.png`, fullPage: true })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Dashboard overflows at ${width}`)
  }
  await page.getByRole('button', { name: 'Refresh dashboard',exact:true }).focus()
  await page.keyboard.press('Enter')
  await page.getByRole('heading',{name:'Connected to active research'}).waitFor()
  summary.generated_at=new Date(Date.now()-600000).toISOString();summary.delivery.stale=true
  await page.getByRole('button', { name: 'Refresh dashboard',exact:true }).click()
  await page.getByRole('heading',{name:'Backend sync delayed'}).waitFor()
  assert.deepEqual(staticRequests,[],'Dashboard sections must not mix old static files into active reporting')
  assert.deepEqual(errors, [])
  console.log('PASS: live dashboard status renders and refreshes at mobile, tablet, and desktop widths.')
} catch (error) {
  await page.screenshot({ path: 'work/dashboard-qa/failure.png', fullPage: true })
  console.error(await page.locator('body').innerText())
  throw error
} finally {
  await browser.close()
}

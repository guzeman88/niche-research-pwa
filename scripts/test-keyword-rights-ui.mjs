// Advisory flags against fixture responses only; no provider calls or live writes.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.VALIDATION_UI_ORIGIN || 'http://127.0.0.1:4173'
const keywords = ['ted baker london shirt', 'baker mayfield shirt', 'basketball goodie bags']
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ serviceWorkers: 'block' })
const mutations = []
await context.route('**/api/account/**', route => {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/session')) return route.fulfill({ json: {
    user: { id: 'rights-qa', email: 'qa@example.test' },
    profile: { id: 'rights-qa', display_name: 'QA', role: 'admin' },
  } })
  if (path.endsWith('/workspace')) return route.fulfill({ json: { payload: {}, revision: 1 } })
  return route.fulfill({ status: 503, json: { error: 'Fixture backend is idle.' } })
})
await context.route('**/data/keywords.json*', route => route.fulfill({ json: keywords.map(keyword => ({
  keyword, domain: 'fixture', scanned: false, evidence_status: 'unverified',
})) }))
await context.route('**/api/product-validation**', route => {
  if (route.request().method() !== 'GET') mutations.push(route.request().url())
  return route.fulfill({ json: route.request().url().endsWith('/supported-keywords') ? {
    status: 'tracking', month: '2026-10', timezone: 'UTC', target: 3000,
    qualified_this_month: 3, available_supported_groups: 3, drafts: [],
    candidates: keywords.map(keyword => ({ keyword, status: 'google_supported',
      google_monthly_searches: 1000, google_geography: 'US', etsy_listing_count: 100,
      sample_count: 50, automated_relevance: 0.8 })),
  } : { projects: [], pending_sync: 0 } })
})
await context.route('**/api/production', route => route.fulfill({ status: 503, json: { detail: 'No production engine in this fixture.' } }))
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))
await mkdir('work/keyword-rights-qa', { recursive: true })
try {
  await page.goto(`${origin}/keywords`)
  await page.getByRole('heading', { name: 'Keywords', exact: true }).waitFor()
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    const flags = page.locator('summary:visible').filter({ hasText: 'Possible rights issue' })
    await flags.first().waitFor()
    assert.equal(await flags.count(), 2, 'Flag names but keep the ordinary keyword unflagged')
    await flags.first().focus()
    await page.keyboard.press('Enter')
    await page.getByText('“Ted Baker” · brand name', { exact: true }).filter({ visible: true }).waitFor()
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Keyword page fits ${width}`)
    await page.screenshot({ path: `work/keyword-rights-qa/keywords-${width}.png`, fullPage: true })
    await page.keyboard.press('Enter')
  }
  await page.goto(`${origin}/validation`)
  await page.getByRole('button', { name: 'Connect workspace', exact: true }).click()
  const table = page.getByRole('table', { name: 'Supported research candidates for product preparation' })
  await table.waitFor()
  assert.equal(await table.getByText('Possible rights issue', { exact: true }).count(), 2)
  const row = table.getByRole('row').filter({ hasText: 'ted baker london shirt' })
  assert(await row.getByRole('button', { name: 'Prepare product' }).isEnabled())
  await row.locator('summary').focus()
  await page.keyboard.press('Enter')
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Validation fits ${width}`)
    await page.screenshot({ path: `work/keyword-rights-qa/validation-${width}.png`, fullPage: true })
  }
  await row.getByRole('button', { name: 'Prepare product' }).click()
  await page.getByRole('form', { name: 'Research listing product facts' }).waitFor()
  assert.equal(await page.getByRole('form', { name: 'Research listing product facts' }).getByText('Possible rights issue', { exact: true }).count(), 1)
  assert.deepEqual(mutations, [], 'Opening a flag or preparing a form does not write records')
  assert.deepEqual(errors, [])
  console.log('PASS: advisory keyword flags, matched reasons, keyboard disclosure, nonblocking preparation and responsive layouts.')
} finally {
  await browser.close()
}

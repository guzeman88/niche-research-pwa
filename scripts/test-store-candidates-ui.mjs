// Browser regression for provisional candidate rendering. Account boundaries
// are mocked; the candidate payload is the real generated static snapshot.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.CANDIDATE_UI_ORIGIN || 'http://127.0.0.1:5173'
const now = '2026-09-27T12:00:00+00:00'

await mkdir('work/candidate-qa', { recursive: true })
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ serviceWorkers: 'block' })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))

await context.route('**/api/account/**', async route => {
  const request = route.request()
  const path = new URL(request.url()).pathname.replace('/api/account', '')
  if (path === '/session') return route.fulfill({ json: {
    user: { id: 'candidate-qa-user', email: 'qa@example.test' },
    profile: { id: 'candidate-qa-user', display_name: 'QA Owner', business_name: 'EtGen QA', timezone: 'America/New_York', currency: 'USD', role: 'admin', created_at: now },
    mfa_required: false, recovery: false,
  } })
  if (path === '/workspace' && request.method() === 'GET') return route.fulfill({ json: { payload: {}, revision: 1 } })
  if (path === '/workspace' && request.method() === 'POST') return route.fulfill({ json: { revision: 2 } })
  return route.fulfill({ status: 404, json: { error: 'Unhandled QA account route' } })
})

try {
  await page.goto(`${origin}/store-generator`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.getByRole('heading', { name: 'Store Idea Generator' }).waitFor()
  await page.getByRole('heading', { name: 'Ranked experiments, not promised winners' }).waitFor()
  await page.getByText('Thanksgiving & November Decor', { exact: true }).first().waitFor()
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 })
    await page.screenshot({ path: `work/candidate-qa/store-candidates-${width}.png`, fullPage: true })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Store candidates overflow at ${width}`)
  }
  assert.match(await page.locator('body').innerText(), /Test priority \d+\.\d+\/65/)
  assert.ok(await page.getByRole('link', { name: 'Connect volume and outcomes' }).count() === 1)
  await page.getByRole('button', { name: 'Details' }).first().click()
  await page.getByText('Launch sequence', { exact: true }).first().waitFor()
  assert.ok(await page.getByText('Risk notes', { exact: true }).count() >= 1)
  assert.deepEqual(errors, [])
  console.log('PASS: controlled test candidates render with evidence labels, responsive layout, and validation actions.')
} catch (error) {
  await page.screenshot({ path: 'work/candidate-qa/failure.png', fullPage: true })
  console.error(await page.locator('body').innerText())
  throw error
} finally {
  await browser.close()
}

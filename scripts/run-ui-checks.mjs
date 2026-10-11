// Run the browser regressions against the same production bundle that deploys.
import { spawn, spawnSync } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const origin = 'http://127.0.0.1:4173'
const server = spawn(process.execPath, [
  'node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1',
  '--port', '4173', '--strictPort',
], { stdio: 'inherit' })

try {
  let ready = false
  for (let attempt = 0; attempt < 60; attempt++) {
    if (server.exitCode !== null) throw new Error('Vite preview exited before becoming ready')
    try {
      const response = await fetch(origin)
      if (response.ok) {
        ready = true
        break
      }
    } catch {
      // Preview is still starting.
    }
    await delay(500)
  }
  if (!ready) throw new Error('Vite preview did not become ready within 30 seconds')

  const env = {
    ...process.env,
    DASHBOARD_UI_ORIGIN: origin,
    CANDIDATE_UI_ORIGIN: origin,
    LAUNCH_UI_ORIGIN: origin,
    VALIDATION_UI_ORIGIN: origin,
  }
  for (const script of [
    'scripts/test-dashboard-ui.mjs',
    'scripts/test-store-candidates-ui.mjs',
    'scripts/test-launch-ui.mjs',
    'scripts/run-validation-ui-check.mjs',
  ]) {
    const result = spawnSync(process.execPath, [script], { env, stdio: 'inherit' })
    if (result.error) throw result.error
    if (result.status !== 0) throw new Error(`${script} failed with exit code ${result.status}`)
  }
} finally {
  server.kill()
}

// Independent ledger and ephemeral loopback port: no production data or credentials.
import {spawn} from 'node:child_process'
import {mkdtemp} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {resolve, join} from 'node:path'
import net from 'node:net'
import {setTimeout as delay} from 'node:timers/promises'

const temp = await mkdtemp(join(tmpdir(), 'etgen-validation-qa-'))
const listener = net.createServer()
await new Promise(done => listener.listen(0, '127.0.0.1', done))
const port = listener.address().port
await new Promise(done => listener.close(done))
const api = `http://127.0.0.1:${port}`
const env = {...process.env, BACKEND_DIR: temp, VALIDATION_DB_PATH: join(temp, 'ledger.sqlite'), AUTO_START_SCHEDULER: '0', SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '', SUPABASE_ANON_KEY: '', ETSY_API_KEYSTRING: '', ETSY_SHARED_SECRET: '', VALIDATION_QA_API: api}
const backend = spawn(process.env.VALIDATION_QA_PYTHON || 'python', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {cwd: resolve('backend'), env, stdio: 'inherit'})
try {
  let ready = false
  for (let i = 0; i < 60; i++) {
    if (backend.exitCode !== null) throw new Error('Isolated validation backend exited')
    try {if ((await fetch(`${api}/api/product-validation`)).ok) {ready = true; break}} catch { /* starting */ }
    await delay(500)
  }
  if (!ready) throw new Error('Validation backend did not start')
  const check = spawn(process.execPath, ['scripts/test-product-validation-ui.mjs'], {env, stdio: 'inherit'})
  const code = await new Promise((done, reject) => {check.on('error', reject); check.on('exit', done)})
  if (code !== 0) throw new Error(`Validation browser check failed: ${code}`)
} finally {backend.kill()}

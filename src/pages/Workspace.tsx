import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {accountRequest} from '../lib/accountApi'
import {useAuth} from '../lib/auth'
import {flushAccountWorkspace} from '../lib/accountWorkspace'
import {downloadBackup, mergeBackup, parseBackup, previewMerge, readBackup, type WorkspaceBackup} from '../lib/workspaceBackup'

export default function Workspace() {
  const client = useQueryClient()
  const auth = useAuth()
  const [pending, setPending] = useState<WorkspaceBackup | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revisions, setRevisions] = useState<Array<{id: number; created_at: string}>>([])
  const [revision, setRevision] = useState('')
  const preview = pending ? previewMerge(pending) : null

  async function run(action: () => Promise<void> | void) {
    setBusy(true); setError(''); setMessage('')
    try { await action() } catch (failure) { setError(failure instanceof Error ? failure.message : 'The action failed. Your existing work is preserved.') }
    finally { setBusy(false) }
  }

  return <div className="page max-w-3xl">
    <div className="page-header"><h1 className="text-xl font-bold">Workspace & backups</h1></div>
    <p className="text-sm text-surface-200">Stores, products, listings and imported scans are saved to your private account. Sign in on another device to continue. Download backups for an additional copy.</p>
    <section className="panel p-4 space-y-4 mt-6" aria-labelledby="backup-title">
      <h2 id="backup-title" className="font-semibold">Protect your work</h2>
      <button className="btn-primary text-surface-950" disabled={busy} onClick={() => run(() => downloadBackup())}>Download backup</button>
      <div>
        <label htmlFor="backup-file" className="block text-sm font-semibold mb-2">Import a backup</label>
        <input id="backup-file" type="file" accept=".json,application/json" disabled={busy} className="block w-full text-sm" onChange={event => {
          const file = event.target.files?.[0]
          setPending(null)
          if (file) void run(async () => {
            if (file.size > 16 * 1024 * 1024) throw new Error('Backup exceeds 16 MB.')
            const backup = parseBackup(await file.text())
            previewMerge(backup)
            setPending(backup)
          })
        }}/>
      </div>
      {preview && <div className="space-y-3 text-sm">
        <p>{preview.added} records to add. {preview.conflicts} conflicting records will keep this browser’s version.</p>
        <p className="text-surface-200">Save a backup first if you want a copy of the current workspace. Existing records are preserved when merging.</p>
        <button className="btn-primary text-surface-950" disabled={busy} onClick={() => run(async () => {
          const result = mergeBackup(pending!)
          await flushAccountWorkspace()
          setPending(null); await client.invalidateQueries()
          setMessage(`Added ${result.added} records. Kept ${result.conflicts} existing versions.`)
        })}>Merge backup</button>
        <button className="btn-secondary ml-3" onClick={() => setPending(null)}>Cancel</button>
      </div>}
    </section>
    {auth.profile?.role === 'admin' && <section className="panel p-4 space-y-4 mt-6">
      <h2 className="font-semibold">Bring in earlier browser work</h2>
      <p className="text-sm text-surface-200">Your earlier browser workspace has been preserved. Preview an import into this account; nothing is moved automatically.</p>
      <button className="btn-secondary" disabled={busy} onClick={() => run(() => {
        const backup = readBackup(window.localStorage)
        if (!Object.keys(backup.data).length) {setMessage('No earlier workspace was found in this browser.'); return}
        previewMerge(backup); setPending(backup); setMessage('Earlier workspace loaded. Review the merge above.')
      })}>Preview earlier workspace</button>
    </section>}
    <section className="panel p-4 space-y-4 mt-6" aria-labelledby="connection-title">
      <h2 id="connection-title" className="font-semibold">Account backups</h2>
      <p className="text-sm text-surface-200">Save a point in time. Earlier backups stay available only to your account.</p>
      <div className="flex flex-wrap gap-3">
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const result = await accountRequest<{id:number}>('/backups', readBackup())
          setMessage(`Saved account backup ${result.id}. Previous account backups are preserved.`)
        })}>Save account backup</button>
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const backups = await accountRequest<typeof revisions>('/backups')
          setRevisions(backups); setRevision(String(backups[0]?.id || ''))
          if (!backups.length) setMessage('No account backups yet.')
        })}>Browse account backups</button>
      </div>
      {revisions.length > 0 && <div className="space-y-3">
        <label htmlFor="server-backup" className="block text-sm">Account backup</label>
        <select id="server-backup" value={revision} className="input w-full" onChange={event => setRevision(event.target.value)}>
          {revisions.map(item => <option key={item.id} value={item.id}>{item.id} · {new Date(item.created_at).toLocaleString()}</option>)}
        </select>
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const backup = parseBackup(JSON.stringify(await accountRequest(`/backups/${revision}`)))
          previewMerge(backup); setPending(backup); setMessage('Account backup loaded. Review the merge above.')
        })}>Preview merge</button>
      </div>}
    </section>
    {busy && <p role="status" className="mt-4 text-sm">Working…</p>}
    {message && <p role="status" className="mt-4 text-sm text-surface-100">{message}</p>}
    {error && <p role="alert" className="mt-4 text-sm text-red-200">{error}</p>}
  </div>
}

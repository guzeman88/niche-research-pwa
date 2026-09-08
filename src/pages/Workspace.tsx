import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import {clearConnection, operatorRequest, readConnection, saveConnection} from '../lib/operatorConnection'
import {downloadBackup, mergeBackup, parseBackup, previewMerge, readBackup, type WorkspaceBackup} from '../lib/workspaceBackup'

export default function Workspace() {
  const client = useQueryClient()
  const [connection, setConnection] = useState(readConnection)
  const [pending, setPending] = useState<WorkspaceBackup | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revisions, setRevisions] = useState<Array<{revision: number; created_at: string}>>([])
  const [revision, setRevision] = useState('')
  const preview = pending ? previewMerge(pending) : null

  async function run(action: () => Promise<void> | void) {
    setBusy(true); setError(''); setMessage('')
    try { await action() } catch (failure) { setError(failure instanceof Error ? failure.message : 'The action failed. Your existing work is preserved.') }
    finally { setBusy(false) }
  }

  return <div className="page max-w-3xl">
    <div className="page-header"><h1 className="text-xl font-bold">Workspace & backups</h1></div>
    <p className="text-sm text-surface-200">Stores, products, listings and imported scans are saved in this browser. Transfer a backup to another device to bring your work with you.</p>
    <section className="panel p-4 space-y-4 mt-6" aria-labelledby="backup-title">
      <h2 id="backup-title" className="font-semibold">Protect your work</h2>
      <button className="btn-primary" disabled={busy} onClick={() => run(() => downloadBackup())}>Download backup</button>
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
        <button className="btn-primary" disabled={busy} onClick={() => run(async () => {
          const result = mergeBackup(pending!)
          setPending(null); await client.invalidateQueries()
          setMessage(`Added ${result.added} records. Kept ${result.conflicts} existing versions.`)
        })}>Merge backup</button>
        <button className="btn-secondary ml-3" onClick={() => setPending(null)}>Cancel</button>
      </div>}
    </section>
    <section className="panel p-4 space-y-4 mt-6" aria-labelledby="connection-title">
      <h2 id="connection-title" className="font-semibold">Connect your backend</h2>
      <p className="text-sm text-surface-200">A connection enables private actions and server backups. The token stays in this tab’s session and is excluded from backups.</p>
      <form className="space-y-4" onSubmit={event => {event.preventDefault(); void run(async () => {
        saveConnection(connection)
        await operatorRequest('/api/settings')
        setMessage('Backend connection verified.')
      })}}>
        <div><label htmlFor="backend-url" className="block text-sm mb-2">Backend URL</label>
          <input id="backend-url" type="url" required placeholder="https://api.example.com" className="input w-full" value={connection.url} onChange={event => setConnection({...connection, url:event.target.value})}/></div>
        <div><label htmlFor="backend-token" className="block text-sm mb-2">Operator token</label>
          <input id="backend-token" type="password" autoComplete="off" className="input w-full" value={connection.token} onChange={event => setConnection({...connection, token:event.target.value})}/></div>
        <button className="btn-primary" disabled={busy}>Connect</button>
        <button type="button" className="btn-secondary ml-3" disabled={busy} onClick={() => {clearConnection(); setConnection({url:'',token:''}); setRevisions([]); setMessage('Disconnected.')}}>Disconnect</button>
      </form>
      <div className="flex flex-wrap gap-3">
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const result = await operatorRequest<{revision:number}>('/api/workspace/backups', readBackup())
          setMessage(`Saved server backup ${result.revision}. Previous server backups are preserved.`)
        })}>Save server backup</button>
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const backups = await operatorRequest<typeof revisions>('/api/workspace/backups')
          setRevisions(backups); setRevision(String(backups[0]?.revision || ''))
          if (!backups.length) setMessage('No server backups yet.')
        })}>Browse server backups</button>
      </div>
      {revisions.length > 0 && <div className="space-y-3">
        <label htmlFor="server-backup" className="block text-sm">Server backup</label>
        <select id="server-backup" value={revision} className="input w-full" onChange={event => setRevision(event.target.value)}>
          {revisions.map(item => <option key={item.revision} value={item.revision}>{item.revision} · {new Date(item.created_at).toLocaleString()}</option>)}
        </select>
        <button className="btn-secondary" disabled={busy} onClick={() => run(async () => {
          const backup = parseBackup(JSON.stringify(await operatorRequest(`/api/workspace/backups/${revision}`)))
          previewMerge(backup); setPending(backup); setMessage('Server backup loaded. Review the merge above.')
        })}>Preview merge</button>
      </div>}
    </section>
    {busy && <p role="status" className="mt-4 text-sm">Working…</p>}
    {message && <p role="status" className="mt-4 text-sm text-surface-100">{message}</p>}
    {error && <p role="alert" className="mt-4 text-sm text-red-200">{error}</p>}
  </div>
}

import {accountRequest} from './accountApi'

let owner = '', revision = 0, change = 0, saved = 0, generation = 0
let rows = new Map<string, string>()
let saving: Promise<void> | null = null
let message = ''
const listeners = new Set<() => void>()
// Keep interrupted edits only in this tab's memory, keyed to their verified owner.
const interrupted = new Map<string, {rows:Map<string,string>;revision:number}>()
export const hasInterruptedEdits = () => interrupted.size > 0
const notify = () => listeners.forEach(fn => fn())
export const subscribeWorkspace = (fn: () => void) => { listeners.add(fn); return () => {listeners.delete(fn)} }
export const workspaceStatus = () => ({owner, dirty:change !== saved, saving:Boolean(saving), error:message})
export function activateWorkspace(userId: string, payload: Record<string, unknown>, nextRevision: number) {
  if (owner && change !== saved) interrupted.set(owner, {rows:new Map(rows), revision})
  generation++; owner = userId; revision = nextRevision; rows = new Map(Object.entries(payload).map(([k,v])=>[k,JSON.stringify(v)]))
  change = 0; saved = 0; saving = null; message = ''
  const pending = interrupted.get(userId)
  if (pending) {
    rows = pending.rows; revision = pending.revision; change = 1
    message = 'Your interrupted edits were preserved in this tab. Download a backup, then retry saving.'
    interrupted.delete(userId)
  }
  notify()
}
export function clearAccountWorkspace() { activateWorkspace('', {}, 0) }
export const accountStorage: Storage = {
  get length() { return rows.size },
  key(index: number) { return [...rows.keys()][index] ?? null },
  getItem(key: string) { return owner ? rows.get(key) ?? null : null },
  setItem(key: string, value: string) {
    if (!owner) throw new Error('Sign in before saving work.')
    if (rows.get(key) === value) return
    rows.set(key,value); change++; notify()
  },
  removeItem(key: string) { if (!owner) throw new Error('Sign in before changing work.'); if (rows.delete(key)) {change++; notify()} },
  clear() { if (!owner) throw new Error('Sign in before changing work.'); rows.clear(); change++; notify() },
}
export async function flushAccountWorkspace(): Promise<void> {
  if (saving) return saving
  if (!owner || change === saved) return
  const started = generation
  saving = (async () => {
    try {
      while (change !== saved && started === generation) {
        const sequence = change
        const payload = Object.fromEntries([...rows].map(([k,v])=>[k,JSON.parse(v)]))
        const result = await accountRequest<{revision:number}>('/workspace',{revision,payload})
        if (started !== generation) return
        revision = result.revision; saved = sequence; message = ''
      }
    } catch (error) {
      if (started === generation) message = error instanceof Error ? error.message : 'Your changes have not been saved.'
      throw error
    } finally { if (started === generation) {saving = null; notify()} }
  })()
  notify(); return saving
}

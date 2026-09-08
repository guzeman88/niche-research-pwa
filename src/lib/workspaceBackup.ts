import {accountStorage} from './accountWorkspace'
const PREFIX = 'niche-research-pwa:'
const KINDS = ['stores', 'store-workspace', 'user-keywords', 'user-scan-batches'] as const
export interface WorkspaceBackup {schema_version: 1; created_at: string; data: Record<string, unknown>}
type Row = Record<string, unknown>
const isRecord = (value: unknown): value is Row => Boolean(value && typeof value === 'object' && !Array.isArray(value))
const identity = (row: Row) => String(row.id ?? row.slug ?? row.keyword ?? '')
const keyFor = (kind: string) => `${PREFIX}${kind}:v1`

export function readBackup(storage: Storage = accountStorage): WorkspaceBackup {
  const data: Record<string, unknown> = {}
  for (const kind of KINDS) {
    const raw = storage.getItem(keyFor(kind))
    if (raw) data[keyFor(kind)] = JSON.parse(raw)
  }
  return parseBackup(JSON.stringify({schema_version: 1, created_at: new Date().toISOString(), data}))
}

export function parseBackup(text: string): WorkspaceBackup {
  if (text.length > 16 * 1024 * 1024) throw new Error('Backup exceeds 16 MB.')
  const value: unknown = JSON.parse(text)
  if (!isRecord(value) || value.schema_version !== 1 || typeof value.created_at !== 'string' || !isRecord(value.data)) {
    throw new Error('Choose an EtGen workspace backup (version 1).')
  }
  for (const [key, data] of Object.entries(value.data)) {
    if (!KINDS.some(kind => key === keyFor(kind))) throw new Error('Backup contains an unsupported data section.')
    if (key === keyFor('store-workspace')) {
      if (!isRecord(data)) throw new Error('Invalid store workspace.')
      for (const [slug, workspace] of Object.entries(data)) {
        if (['__proto__', 'constructor', 'prototype'].includes(slug) || !isRecord(workspace)) throw new Error('Invalid store identifier.')
        validateRows(workspace.products); validateRows(workspace.listings)
      }
    } else validateRows(data)
  }
  return value as unknown as WorkspaceBackup
}

function validateRows(value: unknown): asserts value is Row[] {
  if (!Array.isArray(value) || !value.every(row => isRecord(row) && identity(row))) throw new Error('Backup contains invalid records.')
}

export function previewMerge(backup: WorkspaceBackup, storage: Storage = accountStorage) {
  const current = readBackup(storage)
  let added = 0, conflicts = 0
  const mergeRows = (existing: unknown, incoming: unknown) => {
    const local = (existing || []) as Row[]
    const map = new Map(local.map(row => [identity(row), row]))
    for (const row of (incoming || []) as Row[]) {
      const old = map.get(identity(row))
      if (!old) { map.set(identity(row), row); added++ }
      else if (JSON.stringify(old) !== JSON.stringify(row)) conflicts++
    }
    return [...map.values()]
  }
  const data = {...current.data}
  for (const [key, incoming] of Object.entries(backup.data)) {
    if (key === keyFor('store-workspace')) {
      const workspaces = {...(data[key] || {}) as Record<string, Row>}
      for (const [slug, workspace] of Object.entries(incoming as Record<string, Row>)) {
        workspaces[slug] = {products: mergeRows(workspaces[slug]?.products, workspace.products),
          listings: mergeRows(workspaces[slug]?.listings, workspace.listings)}
      }
      data[key] = workspaces
    } else data[key] = mergeRows(data[key], incoming)
  }
  return {added, conflicts, data, previous: current}
}

export function mergeBackup(backup: WorkspaceBackup, storage: Storage = accountStorage) {
  const result = previewMerge(parseBackup(JSON.stringify(backup)), storage)
  const previous = new Map(Object.keys(result.data).map(key => [key, storage.getItem(key)]))
  try {
    for (const [key, data] of Object.entries(result.data)) storage.setItem(key, JSON.stringify(data))
  } catch (error) {
    for (const [key, raw] of previous) { if (raw === null) storage.removeItem(key); else storage.setItem(key, raw) }
    throw error
  }
  window.dispatchEvent(new Event('niche-research-pwa:user-data-updated'))
  return result
}

export function downloadBackup(backup = readBackup()) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(backup, null, 2)], {type: 'application/json'}))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = `etgen-workspace-${backup.created_at.replace(/[:.]/g, '-')}.json`
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}

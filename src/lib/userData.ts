import type { StatsResponse, KeywordItem } from '../types/api'
import type { GapReport } from '../types/gaps'
import { generateStoreIdeas, type StoreIdea } from './storeIdeas'
import { USER_DATA_EVENT } from './appMode'
import {accountStorage} from './accountWorkspace'

export type UserScanSource = 'erank' | 'semrush' | 'csv' | 'manual'

export interface UserKeywordItem extends KeywordItem, Record<string, unknown> {
  user_scan_id: string
  user_scan_name: string
  user_source: UserScanSource
  search_volume?: number | null
  competition_value?: number | null
  competition_kind?: 'score' | 'density' | 'count' | 'unknown'
  cpc?: number | null
  trend_value?: number | null
  demand_score?: number | null
  competition_ease?: number | null
  buyer_intent_score?: number | null
}

export interface UserScanBatch {
  id: string
  name: string
  source: UserScanSource
  created_at: string
  row_count: number
  keyword_count: number
  scored_count: number
}

export interface UserImportResult {
  batch: UserScanBatch
  imported: number
  skipped: number
  totalKeywords: number
}

const USER_KEYWORDS_KEY = 'niche-research-pwa:user-keywords:v1'
const USER_BATCHES_KEY = 'niche-research-pwa:user-scan-batches:v1'

const KEYWORD_HEADERS = [
  'keyword', 'keywords', 'search term', 'search terms', 'phrase', 'term', 'query',
]
const VOLUME_HEADERS = [
  'volume', 'search volume', 'avg monthly searches', 'average searches', 'avg searches',
  'monthly searches', 'etsy searches', 'searches', 'us search volume',
]
const COMPETITION_HEADERS = [
  'competition', 'competitive density', 'competition score', 'seo difficulty',
  'keyword difficulty', 'difficulty', 'competing listings', 'listing count', 'results',
]
const CPC_HEADERS = ['cpc', 'cost per click', 'avg cpc', 'average cpc']
const TREND_HEADERS = ['trend', 'change', 'growth', 'delta', 'trend score']
const DOMAIN_HEADERS = ['category', 'domain', 'niche', 'tag group', 'market']

interface ParsedRow {
  keyword: string
  domain: string
  volume: number | null
  competition: number | null
  competitionKind: UserKeywordItem['competition_kind']
  cpc: number | null
  trend: number | null
}

export function getUserScanBatches(): UserScanBatch[] {
  return readJson<UserScanBatch[]>(USER_BATCHES_KEY, []).filter(isUserScanBatch)
}

export function listUserKeywords(limit = 15000): UserKeywordItem[] {
  return readUserKeywords().slice(0, limit)
}

export function getUserDomains(): string[] {
  return Array.from(new Set(readUserKeywords().map((keyword) => keyword.domain).filter(Boolean))).sort()
}

export function getUserOpportunities(limit = 100): UserKeywordItem[] {
  void limit
  return []
}

export function getUserBreakouts(limit = 20): { keyword: string; breakout: boolean }[] {
  void limit
  return []
}

export function getUserStats(): StatsResponse {
  const keywords = readUserKeywords()
  const scanned = keywords.filter((keyword) => keyword.scanned).length
  const opportunities = keywords
    .map((keyword) => keyword.opportunity_score)
    .filter((value): value is number => Number.isFinite(value))
  const gaps = keywords
    .map((keyword) => keyword.gap_score)
    .filter((value): value is number => Number.isFinite(value))
  const domainCounts = new Map<string, number>()
  for (const keyword of keywords) {
    domainCounts.set(keyword.domain || 'user scan', (domainCounts.get(keyword.domain || 'user scan') || 0) + 1)
  }
  const topGap = [...keywords]
    .filter((keyword) => Number.isFinite(keyword.gap_score))
    .sort((a, b) => Number(b.gap_score) - Number(a.gap_score))[0]

  return {
    total_seeds: keywords.length,
    scanned,
    unscanned: Math.max(0, keywords.length - scanned),
    total_scans: scanned,
    coverage_pct: keywords.length ? Number(((scanned / keywords.length) * 100).toFixed(1)) : null,
    avg_opportunity: opportunities.length ? roundAverage(opportunities) : null,
    avg_gap_score: gaps.length ? roundAverage(gaps) : null,
    breakout_count: 0,
    expansion_edges: getUserScanBatches().length,
    top_gap_keyword: topGap?.gap_score == null ? null : { keyword: topGap.keyword, gap_score: topGap.gap_score },
    domains: Array.from(domainCounts.entries())
      .map(([domain, cnt]) => ({ domain, cnt }))
      .sort((a, b) => b.cnt - a.cnt),
  }
}

export function getUserGaps(limit = 100): Array<Partial<GapReport> & { keyword: string; composite_gap_score: number }> {
  void limit
  return []
}

export function getUserStoreIdeas(limit = 12): StoreIdea[] {
  return generateStoreIdeas(getUserOpportunities(1000), getUserGaps(1000) as GapReport[]).slice(0, limit)
}

export function importUserScan(input: { source: UserScanSource; name?: string; text: string }): UserImportResult {
  const parsed = parseUserScan(input.text)
  const id = uniqueId('scan')
  const createdAt = new Date().toISOString()
  const scoredRows = toUserKeywords(parsed.rows, {
    id,
    source: input.source,
    name: input.name?.trim() || labelForSource(input.source),
    createdAt,
  })
  const existing = readUserKeywords()
  const byKeyword = new Map(existing.map((keyword) => [keyword.keyword.toLowerCase(), keyword]))
  for (const keyword of scoredRows) {
    const key = keyword.keyword.toLowerCase()
    byKeyword.set(key, mergeKeyword(byKeyword.get(key), keyword))
  }
  const keywords = Array.from(byKeyword.values()).sort((a, b) => a.keyword.localeCompare(b.keyword))
  writeJson(USER_KEYWORDS_KEY, keywords)

  const batch: UserScanBatch = {
    id,
    name: input.name?.trim() || labelForSource(input.source),
    source: input.source,
    created_at: createdAt,
    row_count: parsed.rowCount,
    keyword_count: scoredRows.length,
    scored_count: scoredRows.filter((keyword) => keyword.scanned).length,
  }
  writeJson(USER_BATCHES_KEY, [batch, ...getUserScanBatches()].slice(0, 60))
  emitUserDataChanged()
  return {
    batch,
    imported: scoredRows.length,
    skipped: parsed.skipped,
    totalKeywords: keywords.length,
  }
}

export function clearUserKeywordData(): void {
  if (!hasStorage()) return
  accountStorage.removeItem(USER_KEYWORDS_KEY)
  accountStorage.removeItem(USER_BATCHES_KEY)
  emitUserDataChanged()
}

function parseUserScan(text: string): { rows: ParsedRow[]; rowCount: number; skipped: number } {
  const table = parseTable(text)
  if (table.length === 0) return { rows: [], rowCount: 0, skipped: 0 }

  const header = table[0].map(normalizeHeader)
  const hasHeaders = header.some((cell) => KEYWORD_HEADERS.includes(cell))
  const rows = hasHeaders ? table.slice(1) : table
  const headerMap = hasHeaders ? buildHeaderMap(header) : new Map<string, number>([['keyword', 0]])
  const parsedRows = rows
    .map((row) => rowFromCells(row, headerMap))
    .filter((row): row is ParsedRow => Boolean(row))
  return {
    rows: parsedRows,
    rowCount: rows.length,
    skipped: Math.max(0, rows.length - parsedRows.length),
  }
}

function parseTable(text: string): string[][] {
  const clean = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  if (!clean) return []
  const firstLine = clean.split('\n')[0] || ''
  const delimiter = (firstLine.match(/\t/g) || []).length > (firstLine.match(/,/g) || []).length ? '\t' : ','
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < clean.length; index += 1) {
    const char = clean[index]
    const next = clean[index + 1]
    if (char === '"') {
      if (quoted && next === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
    } else if (char === delimiter && !quoted) {
      row.push(cell.trim())
      cell = ''
    } else if (char === '\n' && !quoted) {
      row.push(cell.trim())
      if (row.some(Boolean)) rows.push(row)
      row = []
      cell = ''
    } else {
      cell += char
    }
  }
  row.push(cell.trim())
  if (row.some(Boolean)) rows.push(row)
  return rows
}

function buildHeaderMap(headers: string[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const [index, header] of headers.entries()) {
    if (!map.has('keyword') && KEYWORD_HEADERS.includes(header)) map.set('keyword', index)
    if (!map.has('volume') && VOLUME_HEADERS.includes(header)) map.set('volume', index)
    if (!map.has('competition') && COMPETITION_HEADERS.includes(header)) map.set('competition', index)
    if (!map.has('cpc') && CPC_HEADERS.includes(header)) map.set('cpc', index)
    if (!map.has('trend') && TREND_HEADERS.includes(header)) map.set('trend', index)
    if (!map.has('domain') && DOMAIN_HEADERS.includes(header)) map.set('domain', index)
  }
  return map
}

function rowFromCells(cells: string[], headerMap: Map<string, number>): ParsedRow | null {
  const keyword = cell(cells, headerMap.get('keyword')).trim()
  if (!keyword) return null
  const competitionHeader = findCompetitionHeaderKind(cells, headerMap)
  return {
    keyword,
    domain: cell(cells, headerMap.get('domain')).trim() || inferDomain(keyword),
    volume: parseNumber(cell(cells, headerMap.get('volume'))),
    competition: parseNumber(cell(cells, headerMap.get('competition'))),
    competitionKind: competitionHeader,
    cpc: parseNumber(cell(cells, headerMap.get('cpc'))),
    trend: parseNumber(cell(cells, headerMap.get('trend'))),
  }
}

function toUserKeywords(rows: ParsedRow[], batch: { id: string; source: UserScanSource; name: string; createdAt: string }): UserKeywordItem[] {
  return rows.map((row) => {
    const hasObservation = [row.volume, row.competition, row.cpc, row.trend].some(Number.isFinite)
    return {
      keyword: row.keyword,
      domain: row.domain,
      source: `user:${batch.source}`,
      priority: 0,
      added_at: batch.createdAt,
      scanned: hasObservation,
      last_scanned_at: hasObservation ? batch.createdAt : null,
      opportunity_score: null,
      gap_score: null,
      trajectory: null,
      breakout: false,
      evidence_status: hasObservation ? 'imported' : 'unverified',
      score_version: null,
      user_scan_id: batch.id,
      user_scan_name: batch.name,
      user_source: batch.source,
      search_volume: row.volume,
      competition_value: row.competition,
      competition_kind: row.competitionKind,
      cpc: row.cpc,
      trend_value: row.trend,
      demand_score: null,
      competition_ease: null,
      buyer_intent_score: null,
    }
  })
}

function mergeKeyword(existing: UserKeywordItem | undefined, incoming: UserKeywordItem): UserKeywordItem {
  if (!existing) return incoming
  return {
    ...incoming,
    added_at: existing.added_at,
    source: uniqueText([existing.source, incoming.source], ', '),
    user_scan_name: uniqueText([existing.user_scan_name, incoming.user_scan_name], ', '),
    opportunity_score: null,
    gap_score: null,
    score_version: null,
    breakout: false,
  }
}

function readUserKeywords(): UserKeywordItem[] {
  return readJson<UserKeywordItem[]>(USER_KEYWORDS_KEY, [])
    .filter(isUserKeyword)
    .map((keyword) => ({
      ...keyword,
      opportunity_score: null,
      gap_score: null,
      demand_score: null,
      competition_ease: null,
      buyer_intent_score: null,
      trajectory: null,
      breakout: false,
      score_version: null,
      evidence_status: keyword.scanned ? 'imported' : 'unverified',
    }))
    .sort((a, b) => a.keyword.localeCompare(b.keyword))
}

function readJson<T>(key: string, fallback: T): T {
  if (!hasStorage()) return fallback
  try {
    const raw = accountStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function writeJson(key: string, value: unknown): void {
  if (!hasStorage()) return
  accountStorage.setItem(key, JSON.stringify(value))
}

function hasStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function emitUserDataChanged(): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(USER_DATA_EVENT))
}

function isUserKeyword(value: unknown): value is UserKeywordItem {
  if (!value || typeof value !== 'object') return false
  const keyword = value as Partial<UserKeywordItem>
  return typeof keyword.keyword === 'string' && typeof keyword.domain === 'string'
}

function isUserScanBatch(value: unknown): value is UserScanBatch {
  if (!value || typeof value !== 'object') return false
  const batch = value as Partial<UserScanBatch>
  return typeof batch.id === 'string' && typeof batch.name === 'string' && typeof batch.source === 'string'
}

function findCompetitionHeaderKind(cells: string[], headerMap: Map<string, number>): UserKeywordItem['competition_kind'] {
  const index = headerMap.get('competition')
  if (index == null || !cells[index]) return 'unknown'
  const value = parseNumber(cells[index])
  if (value == null) return 'unknown'
  if (value <= 1) return 'density'
  if (value > 100) return 'count'
  return 'score'
}

function parseNumber(value: string): number | null {
  const trimmed = value.trim().toLowerCase()
  if (!trimmed || trimmed === '-' || trimmed === 'n/a') return null
  const multiplier = trimmed.endsWith('k') ? 1000 : trimmed.endsWith('m') ? 1_000_000 : 1
  const cleaned = trimmed.replace(/[$,%]/g, '').replace(/[km]$/, '').replace(/,/g, '').trim()
  const numeric = Number(cleaned)
  return Number.isFinite(numeric) ? numeric * multiplier : null
}

function cell(cells: string[], index: number | undefined): string {
  return index == null ? '' : cells[index] || ''
}

function normalizeHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
}

function inferDomain(keyword: string): string {
  const text = keyword.toLowerCase()
  if (/mug|cup|tumbler/.test(text)) return 'drinkware'
  if (/shirt|tee|hoodie|sweatshirt|apparel/.test(text)) return 'apparel'
  if (/print|poster|wall art|decor|canvas/.test(text)) return 'wall art'
  if (/sticker|decal/.test(text)) return 'stickers'
  if (/svg|png|cricut|sublimation/.test(text)) return 'digital downloads'
  return 'user scan'
}

function labelForSource(source: UserScanSource): string {
  if (source === 'erank') return 'eRank scan'
  if (source === 'semrush') return 'Semrush scan'
  if (source === 'manual') return 'Manual keywords'
  return 'Keyword scan'
}

function roundAverage(values: number[]): number {
  if (!values.length) return 0
  return Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1))
}

function uniqueText(values: string[], joiner: string): string {
  return Array.from(new Set(values.flatMap((value) => value.split(joiner)).map((value) => value.trim()).filter(Boolean))).join(joiner)
}

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

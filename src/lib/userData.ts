import type { StatsResponse, KeywordItem } from '../types/api'
import type { GapReport } from '../types/gaps'
import { generateStoreIdeas, type StoreIdea } from './storeIdeas'
import { USER_DATA_EVENT } from './appMode'

export type UserScanSource = 'erank' | 'semrush' | 'csv' | 'manual'

export interface UserKeywordItem extends KeywordItem, Record<string, unknown> {
  user_scan_id: string
  user_scan_name: string
  user_source: UserScanSource
  search_volume?: number | null
  competition_value?: number | null
  competition_kind?: 'score' | 'density' | 'count' | 'unknown'
  cpc?: number | null
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
  return readUserKeywords()
    .filter((keyword) => Number(keyword.opportunity_score) > 0 || Number(keyword.gap_score) > 0)
    .sort((a, b) => userKeywordStrength(b) - userKeywordStrength(a))
    .slice(0, limit)
}

export function getUserBreakouts(limit = 20): { keyword: string; breakout: boolean }[] {
  return readUserKeywords()
    .filter((keyword) => keyword.breakout)
    .sort((a, b) => userKeywordStrength(b) - userKeywordStrength(a))
    .slice(0, limit)
    .map((keyword) => ({ keyword: keyword.keyword, breakout: true }))
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
    coverage_pct: keywords.length ? Number(((scanned / keywords.length) * 100).toFixed(1)) : 0,
    avg_opportunity: roundAverage(opportunities),
    avg_gap_score: roundAverage(gaps),
    breakout_count: keywords.filter((keyword) => keyword.breakout).length,
    expansion_edges: getUserScanBatches().length,
    top_gap_keyword: topGap?.gap_score == null ? null : { keyword: topGap.keyword, gap_score: topGap.gap_score },
    domains: Array.from(domainCounts.entries())
      .map(([domain, cnt]) => ({ domain, cnt }))
      .sort((a, b) => b.cnt - a.cnt),
  }
}

export function getUserGaps(limit = 100): Array<Partial<GapReport> & { keyword: string; composite_gap_score: number }> {
  return readUserKeywords()
    .filter((keyword) => Number.isFinite(keyword.gap_score))
    .sort((a, b) => Number(b.gap_score) - Number(a.gap_score))
    .slice(0, limit)
    .map((keyword) => ({
      keyword: keyword.keyword,
      analyzed_at: keyword.last_scanned_at || keyword.added_at,
      volume_gap_score: keyword.demand_score ?? undefined,
      quality_gap_score: keyword.competition_ease ?? undefined,
      buyer_intent_score: keyword.buyer_intent_score ?? undefined,
      profit_gap_score: keyword.cpc == null ? undefined : keyword.buyer_intent_score ?? undefined,
      composite_gap_score: Number(keyword.gap_score),
      entry_angle: 'Imported keyword scan',
      listings_analyzed: keyword.competition_kind === 'count' ? Number(keyword.competition_value || 0) : 0,
    }))
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
  const keywords = Array.from(byKeyword.values()).sort((a, b) => userKeywordStrength(b) - userKeywordStrength(a))
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
  window.localStorage.removeItem(USER_KEYWORDS_KEY)
  window.localStorage.removeItem(USER_BATCHES_KEY)
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
  const demandScores = normalizedLogScores(rows.map((row) => row.volume))
  const cpcScores = normalizedLogScores(rows.map((row) => row.cpc))
  const competitionEaseScores = competitionEase(rows)

  return rows.map((row, index) => {
    const demand = demandScores[index]
    const ease = competitionEaseScores[index]
    const buyerIntent = cpcScores[index]
    const opportunity = weightedScore([
      [demand, 0.58],
      [ease, 0.3],
      [buyerIntent, 0.12],
    ])
    const gap = demand == null || ease == null ? null : Math.round(demand * 0.64 + ease * 0.36)
    return {
      keyword: row.keyword,
      domain: row.domain,
      source: `user:${batch.source}`,
      priority: Math.round(userPriority(opportunity, gap)),
      added_at: batch.createdAt,
      scanned: opportunity != null || gap != null,
      last_scanned_at: opportunity != null || gap != null ? batch.createdAt : null,
      opportunity_score: opportunity,
      gap_score: gap,
      trajectory: trajectoryFromTrend(row.trend),
      breakout: Number.isFinite(row.trend) ? Number(row.trend) > 20 : false,
      user_scan_id: batch.id,
      user_scan_name: batch.name,
      user_source: batch.source,
      search_volume: row.volume,
      competition_value: row.competition,
      competition_kind: row.competitionKind,
      cpc: row.cpc,
      demand_score: demand,
      competition_ease: ease,
      buyer_intent_score: buyerIntent,
    }
  })
}

function mergeKeyword(existing: UserKeywordItem | undefined, incoming: UserKeywordItem): UserKeywordItem {
  if (!existing) return incoming
  const opportunity = bestNumber(existing.opportunity_score, incoming.opportunity_score)
  const gap = bestNumber(existing.gap_score, incoming.gap_score)
  return {
    ...existing,
    ...incoming,
    added_at: existing.added_at,
    source: uniqueText([existing.source, incoming.source], ', '),
    user_scan_name: uniqueText([existing.user_scan_name, incoming.user_scan_name], ', '),
    opportunity_score: opportunity,
    gap_score: gap,
    scanned: existing.scanned || incoming.scanned,
    last_scanned_at: latestDate(existing.last_scanned_at, incoming.last_scanned_at),
    search_volume: bestNumber(existing.search_volume, incoming.search_volume),
    competition_value: bestNumber(existing.competition_value, incoming.competition_value),
    cpc: bestNumber(existing.cpc, incoming.cpc),
    demand_score: bestNumber(existing.demand_score, incoming.demand_score),
    competition_ease: bestNumber(existing.competition_ease, incoming.competition_ease),
    buyer_intent_score: bestNumber(existing.buyer_intent_score, incoming.buyer_intent_score),
    priority: Math.max(existing.priority || 0, incoming.priority || 0),
    breakout: existing.breakout || incoming.breakout,
  }
}

function competitionEase(rows: ParsedRow[]): Array<number | null> {
  const countValues = rows.map((row) => row.competitionKind === 'count' ? row.competition : null)
  const countScores = normalizedLogScores(countValues)
  return rows.map((row, index) => {
    if (row.competition == null) return null
    if (row.competitionKind === 'count') {
      const score = countScores[index]
      return score == null ? null : Math.round(100 - score)
    }
    if (row.competitionKind === 'density' || row.competition <= 1) {
      return clampScore(Math.round(100 - row.competition * 100))
    }
    if (row.competition <= 100) return clampScore(Math.round(100 - row.competition))
    const score = countScores[index]
    return score == null ? null : Math.round(100 - score)
  })
}

function normalizedLogScores(values: Array<number | null>): Array<number | null> {
  const logs = values.map((value) => Number.isFinite(value) && Number(value) > 0 ? Math.log10(Number(value) + 1) : null)
  const usable = logs.filter((value): value is number => Number.isFinite(value))
  if (usable.length === 0) return values.map(() => null)
  const min = Math.min(...usable)
  const max = Math.max(...usable)
  return logs.map((value) => {
    if (value == null) return null
    if (max === min) return 65
    return clampScore(Math.round(35 + ((value - min) / (max - min)) * 65))
  })
}

function weightedScore(parts: Array<[number | null, number]>): number | null {
  let weighted = 0
  let weight = 0
  for (const [score, factor] of parts) {
    if (!Number.isFinite(score)) continue
    weighted += Number(score) * factor
    weight += factor
  }
  return weight ? Math.round(weighted / weight) : null
}

function readUserKeywords(): UserKeywordItem[] {
  return readJson<UserKeywordItem[]>(USER_KEYWORDS_KEY, [])
    .filter(isUserKeyword)
    .sort((a, b) => userKeywordStrength(b) - userKeywordStrength(a))
}

function readJson<T>(key: string, fallback: T): T {
  if (!hasStorage()) return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function writeJson(key: string, value: unknown): void {
  if (!hasStorage()) return
  window.localStorage.setItem(key, JSON.stringify(value))
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

function userKeywordStrength(keyword: Pick<UserKeywordItem, 'opportunity_score' | 'gap_score' | 'demand_score' | 'competition_ease'>): number {
  return weightedScore([
    [keyword.opportunity_score ?? null, 0.45],
    [keyword.gap_score ?? null, 0.35],
    [keyword.demand_score ?? null, 0.12],
    [keyword.competition_ease ?? null, 0.08],
  ]) ?? -1
}

function userPriority(opportunity: number | null, gap: number | null): number {
  const score = weightedScore([[opportunity, 0.6], [gap, 0.4]])
  if (score == null) return 1
  if (score >= 80) return 10
  if (score >= 70) return 8
  if (score >= 60) return 6
  return 4
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

function trajectoryFromTrend(value: number | null): string | null {
  if (!Number.isFinite(value)) return null
  if (Number(value) > 5) return 'rising'
  if (Number(value) < -5) return 'declining'
  return 'stable'
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

function bestNumber(a?: number | null, b?: number | null): number | null {
  const aOk = Number.isFinite(a)
  const bOk = Number.isFinite(b)
  if (aOk && bOk) return Math.max(Number(a), Number(b))
  if (aOk) return Number(a)
  if (bOk) return Number(b)
  return null
}

function latestDate(a?: string | null, b?: string | null): string | null {
  if (!a) return b || null
  if (!b) return a
  return Date.parse(a) >= Date.parse(b) ? a : b
}

function uniqueText(values: string[], joiner: string): string {
  return Array.from(new Set(values.flatMap((value) => value.split(joiner)).map((value) => value.trim()).filter(Boolean))).join(joiner)
}

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, value))
}

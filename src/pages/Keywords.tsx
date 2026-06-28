import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listKeywords, getDomains, runDiscovery } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { KeywordsSkeleton } from '../components/Skeleton'
import { fmtDate } from '../lib/utils'
import type { KeywordItem } from '../types/api'

type SortKey = 'keyword' | 'domain' | 'status' | 'opportunity' | 'gap' | 'trajectory'
type SortDir = 'asc' | 'desc'

const COLUMNS: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
  { key: 'keyword', label: 'Keyword', align: 'left' },
  { key: 'domain', label: 'Domain', align: 'left' },
  { key: 'status', label: 'Status', align: 'left' },
  { key: 'opportunity', label: 'Opp', align: 'right' },
  { key: 'gap', label: 'Gap', align: 'right' },
  { key: 'trajectory', label: 'Trend', align: 'right' },
]

const PAGE_SIZE = 100

export default function Keywords() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [sortBy, setSortBy] = useState<SortKey>('gap')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)

  const { data: apiDomains } = useQuery<string[]>({ queryKey: ['domains'], queryFn: getDomains })
  const { data: keywords, isLoading } = useQuery<KeywordItem[]>({
    queryKey: ['keywords'],
    queryFn: () => listKeywords(undefined, 15000),
  })

  const domains = useMemo(() => {
    const fromKeywords = Array.from(new Set((keywords || []).map(kw => kw.domain).filter(Boolean))).sort()
    return fromKeywords.length ? fromKeywords : (apiDomains || [])
  }, [apiDomains, keywords])

  const filtered = useMemo(() => {
    if (!keywords) return []
    const q = search.trim().toLowerCase()
    return keywords.filter(kw => {
      const matchesSearch = !q || kw.keyword.toLowerCase().includes(q)
      const matchesDomain = !domain || kw.domain === domain
      return matchesSearch && matchesDomain
    })
  }, [keywords, search, domain])

  const sorted = useMemo(() => {
    const list = [...filtered]
    list.sort((a, b) => {
      let va: string | number
      let vb: string | number
      switch (sortBy) {
        case 'keyword': va = a.keyword; vb = b.keyword; break
        case 'domain': va = a.domain; vb = b.domain; break
        case 'status': va = a.scanned ? 1 : 0; vb = b.scanned ? 1 : 0; break
        case 'opportunity': va = a.opportunity_score ?? -999; vb = b.opportunity_score ?? -999; break
        case 'gap': va = a.gap_score ?? -999; vb = b.gap_score ?? -999; break
        case 'trajectory': {
          const order: Record<string, number> = { rising: 3, stable: 2, declining: 1 }
          va = order[a.trajectory || ''] ?? 0
          vb = order[b.trajectory || ''] ?? 0
          break
        }
        default: return 0
      }
      if (va < vb) return sortDir === 'asc' ? -1 : 1
      if (va > vb) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return list
  }, [filtered, sortBy, sortDir])

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageStart = sorted.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0
  const pageEnd = Math.min(sorted.length, currentPage * PAGE_SIZE)
  const visibleKeywords = useMemo(
    () => sorted.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [currentPage, sorted],
  )

  useEffect(() => {
    setPage(1)
  }, [search, domain, sortBy, sortDir])

  const discoverMutation = useMutation({
    mutationFn: runDiscovery,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keywords'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const handleSort = (key: SortKey) => {
    if (sortBy === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else {
      setSortBy(key)
      setSortDir('desc')
    }
  }

  const refresh = () => queryClient.refetchQueries({ type: 'active' })

  if (!keywords && !isLoading) return <KeywordsSkeleton />
  if (isLoading && !keywords) return <KeywordsSkeleton />

  return (
    <PullToRefresh onRefresh={refresh}>
      <div className="page">
        <div className="page-header">
          <div>
            <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Keywords</h2>
            <p className="text-[13px] text-surface-200 mt-0.5">{keywords ? `${sorted.length} keywords` : 'Loading...'}</p>
          </div>
          <button
            onClick={() => discoverMutation.mutate({})}
            disabled={discoverMutation.isPending}
            className="btn-primary text-[13px]"
          >
            <Icon name="plus-circle" size={16} />
            {discoverMutation.isPending ? 'Discovering...' : 'Discover'}
          </button>
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-300" />
            <input type="text" className="input pl-9 text-[13px] font-medium" placeholder="Search keywords..." value={search} onChange={e => { setSearch(e.target.value); setDomain('') }} />
          </div>
          <select className="input w-auto min-w-36 text-[13px] font-medium" value={domain} onChange={e => { setDomain(e.target.value); setSearch('') }}>
            <option value="">All domains</option>
            {domains.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        <div className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-surface-600 bg-surface-900/65">
                  {COLUMNS.map(({ key, label, align }) => (
                    <th
                      key={key}
                      onClick={() => handleSort(key)}
                      className={`px-4 py-3 text-[10px] font-bold uppercase tracking-wider text-surface-200 cursor-pointer select-none hover:text-surface-50 transition-colors ${align === 'right' ? 'text-right' : 'text-left'}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {label}
                        <span className={`text-[8px] ${sortBy === key ? 'text-primary-200' : 'text-surface-400'}`}>
                          {sortBy === key ? (sortDir === 'asc' ? 'up' : 'down') : 'down'}
                        </span>
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading && <tr><td colSpan={6} className="px-4 py-12 text-center text-surface-300">Loading...</td></tr>}
                {visibleKeywords.map(kw => {
                  const oppScore = finiteScore(kw.opportunity_score)
                  const gapScore = finiteScore(kw.gap_score)
                  const oppColor = oppScore == null ? 'text-surface-400' : oppScore >= 70 ? 'text-accent-green' : oppScore >= 50 ? 'text-accent-amber' : 'text-accent-red'
                  const gapColor = gapScore == null ? 'text-surface-400' : gapScore >= 70 ? 'text-accent-green' : gapScore >= 50 ? 'text-accent-amber' : 'text-accent-red'
                  return (
                    <tr key={kw.keyword} className="border-b border-surface-600/35 hover:bg-surface-700/35 transition-colors">
                      <td className="px-4 py-3 text-surface-50 font-semibold whitespace-nowrap">{kw.keyword}</td>
                      <td className="px-4 py-3"><span className="tag bg-accent-violet/10 text-accent-violet border-accent-violet/20 whitespace-nowrap">{kw.domain}</span></td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {kw.scanned ? <span className="text-[11px] text-accent-green font-medium">Scanned {fmtDate(kw.last_scanned_at)}</span> : <span className="text-[11px] text-accent-amber font-medium">Pending</span>}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="progress-track w-10 hidden sm:inline-block">{oppScore != null && <span className="block h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, oppScore)}%` }} />}</span>
                          <span className={`font-bold tabular-nums ${oppColor}`}>{oppScore != null ? oppScore.toFixed(0) : '-'}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="progress-track w-10 hidden sm:inline-block">{gapScore != null && <span className="block h-full rounded-full bg-gradient-to-r from-accent-green to-accent-green/80" style={{ width: `${Math.min(100, gapScore)}%` }} />}</span>
                          <span className={`font-bold tabular-nums ${gapColor}`}>{gapScore != null ? gapScore.toFixed(0) : '-'}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        {kw.trajectory === 'rising' && <span className="text-[11px] font-semibold text-accent-green">rising</span>}
                        {kw.trajectory === 'declining' && <span className="text-[11px] font-semibold text-accent-red">declining</span>}
                        {kw.trajectory === 'stable' && <span className="text-[11px] text-surface-300">stable</span>}
                        {!kw.trajectory && <span className="text-[11px] text-surface-400">-</span>}
                      </td>
                    </tr>
                  )
                })}
                {sorted.length === 0 && !isLoading && <tr><td colSpan={6} className="px-4 py-12 text-center text-surface-300">No keywords found</td></tr>}
              </tbody>
            </table>
          </div>
          {sorted.length > PAGE_SIZE && (
            <div className="flex flex-col gap-3 border-t border-surface-600/60 bg-surface-900/45 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[12px] font-medium text-surface-300">
                Showing {pageStart.toLocaleString()}-{pageEnd.toLocaleString()} of {sorted.length.toLocaleString()}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary h-8 px-3 text-[12px]"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  <Icon name="chevron-left" size={14} />
                  Prev
                </button>
                <span className="min-w-20 text-center text-[12px] font-semibold text-surface-200">
                  {currentPage.toLocaleString()} / {totalPages.toLocaleString()}
                </span>
                <button
                  type="button"
                  className="btn-secondary h-8 px-3 text-[12px]"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                  <Icon name="chevron-right" size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </PullToRefresh>
  )
}

function finiteScore(value: number | null | undefined): number | null {
  return Number.isFinite(value) ? Number(value) : null
}

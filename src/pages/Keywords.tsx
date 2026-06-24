import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listKeywords, searchKeywords, getDomains, runDiscovery } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { KeywordsSkeleton } from '../components/Skeleton'
import { fmtDate, scoreColor } from '../lib/utils'
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

export default function Keywords() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [sortBy, setSortBy] = useState<SortKey>('gap')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: domains } = useQuery<string[]>({ queryKey: ['domains'], queryFn: getDomains })
  const { data: keywords, isLoading } = useQuery<KeywordItem[]>({
    queryKey: ['keywords', search, domain],
    queryFn: () => search ? searchKeywords(search, 200) : listKeywords(domain || undefined, 2000),
  })

  const sorted = useMemo(() => {
    if (!keywords) return []
    const list = [...(keywords || [])]
    list.sort((a, b) => {
      let va: any, vb: any
      switch (sortBy) {
        case 'keyword': va = a.keyword; vb = b.keyword; break
        case 'domain': va = a.domain; vb = b.domain; break
        case 'status': va = a.scanned ? 1 : 0; vb = b.scanned ? 1 : 0; break
        case 'opportunity': va = a.opportunity_score ?? -999; vb = b.opportunity_score ?? -999; break
        case 'gap': va = a.gap_score ?? -999; vb = b.gap_score ?? -999; break
        case 'trajectory': { const o: Record<string, number> = { rising: 3, stable: 2, declining: 1 }; va = o[a.trajectory || ''] ?? 0; vb = o[b.trajectory || ''] ?? 0; break }
        default: return 0
      }
      if (va < vb) return sortDir === 'asc' ? -1 : 1
      if (va > vb) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return list
  }, [keywords, sortBy, sortDir])

  const discoverMutation = useMutation({
    mutationFn: runDiscovery,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['keywords'] }); queryClient.invalidateQueries({ queryKey: ['stats'] }) },
  })

  const handleSort = (key: SortKey) => {
    if (sortBy === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortBy(key); setSortDir('desc') }
  }

  const refresh = () => { queryClient.invalidateQueries(); return Promise.resolve() }

  if (!keywords && !isLoading) return <KeywordsSkeleton />
  if (isLoading && !keywords) return <KeywordsSkeleton />

  return (
    <PullToRefresh onRefresh={refresh}>
    <div className="p-4 lg:p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Keywords</h2>
          <p className="text-[13px] text-surface-200 mt-0.5">{keywords ? `${sorted.length} keywords` : 'Loading…'}</p>
        </div>
        <button
          onClick={() => discoverMutation.mutate({})}
          disabled={discoverMutation.isPending}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-400 hover:bg-primary-500 disabled:opacity-50 text-surface-50 text-[13px] font-semibold rounded-xl transition-colors"
        >
          <Icon name="plus-circle" size={16} />
          {discoverMutation.isPending ? 'Discovering…' : 'Discover'}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-300" />
          <input type="text" className="w-full bg-surface-800 border border-surface-500 rounded-xl pl-9 pr-3 py-2.5 text-[13px] text-surface-50 placeholder:text-surface-300 focus:outline-none focus:border-primary-500/50 font-medium" placeholder="Search keywords…" value={search} onChange={e => { setSearch(e.target.value); setDomain('') }} />
        </div>
        <select className="bg-surface-800 border border-surface-500 rounded-xl px-3 py-2.5 text-[13px] text-surface-100 focus:outline-none focus:border-primary-500/50 font-medium" value={domain} onChange={e => { setDomain(e.target.value); setSearch('') }}>
          <option value="">All domains</option>
          {domains?.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="bg-surface-700/80 border border-surface-500/60 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b-2 border-surface-500 bg-surface-800/50">
                {COLUMNS.map(({ key, label, align }) => (
                  <th
                    key={key}
                    onClick={() => handleSort(key)}
                    className={`px-4 py-3 text-[10px] font-bold uppercase tracking-wider text-surface-200 cursor-pointer select-none hover:text-surface-50 transition-colors ${align === 'right' ? 'text-right' : 'text-left'}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {label}
                      <span className={`text-[8px] ${sortBy === key ? 'text-primary-200' : 'text-surface-400'}`}>
                        {sortBy === key ? (sortDir === 'asc' ? '▲' : '▼') : '▼'}
                      </span>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={6} className="px-4 py-12 text-center text-surface-300">Loading…</td></tr>}
              {sorted.map(kw => {
                const oppScore = kw.opportunity_score || 0
                const gapScore = kw.gap_score || 0
                const oppColor = oppScore >= 70 ? 'text-accent-green' : oppScore >= 50 ? 'text-accent-amber' : 'text-accent-red'
                const gapColor = gapScore >= 70 ? 'text-accent-green' : gapScore >= 50 ? 'text-accent-amber' : 'text-accent-red'
                return (
                  <tr key={kw.keyword} className="border-b border-surface-500/30 hover:bg-surface-600/20 transition-colors">
                    <td className="px-4 py-3 text-surface-50 font-semibold whitespace-nowrap">{kw.keyword}</td>
                    <td className="px-4 py-3"><span className="text-[10px] px-2.5 py-0.5 rounded-lg bg-accent-violet/10 text-accent-violet font-semibold border border-accent-violet/15 whitespace-nowrap">{kw.domain}</span></td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {kw.scanned ? <span className="text-[11px] text-accent-green font-medium">Scanned {fmtDate(kw.last_scanned_at)}</span> : <span className="text-[11px] text-accent-amber font-medium">Pending</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-10 h-1 bg-surface-700 rounded-full overflow-hidden hidden sm:inline-block"><span className="block h-full rounded-full bg-gradient-to-r from-primary-400 to-primary-200" style={{ width: `${Math.min(100, oppScore)}%` }} /></span>
                        <span className={`font-bold tabular-nums ${oppColor}`}>{kw.opportunity_score != null ? oppScore.toFixed(0) : '—'}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-10 h-1 bg-surface-700 rounded-full overflow-hidden hidden sm:inline-block"><span className="block h-full rounded-full bg-gradient-to-r from-accent-green to-accent-green/80" style={{ width: `${Math.min(100, gapScore)}%` }} /></span>
                        <span className={`font-bold tabular-nums ${gapColor}`}>{kw.gap_score != null ? gapScore.toFixed(0) : '—'}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {kw.trajectory === 'rising' && <span className="text-[11px] font-semibold text-accent-green">↑ rising</span>}
                      {kw.trajectory === 'declining' && <span className="text-[11px] font-semibold text-accent-red">↓ declining</span>}
                      {kw.trajectory === 'stable' && <span className="text-[11px] text-surface-300">→ stable</span>}
                      {!kw.trajectory && <span className="text-[11px] text-surface-400">—</span>}
                    </td>
                  </tr>
                )
              })}
              {sorted.length === 0 && !isLoading && <tr><td colSpan={6} className="px-4 py-12 text-center text-surface-300">No keywords found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </PullToRefresh>
  )
}

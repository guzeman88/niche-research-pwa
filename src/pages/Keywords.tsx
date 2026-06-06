import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listKeywords, searchKeywords, getDomains, runDiscovery } from '../lib/api'
import { fmtDate, scoreColor } from '../lib/utils'
import type { KeywordItem } from '../types/api'

export default function Keywords() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('')

  const { data: domains } = useQuery<string[]>({
    queryKey: ['domains'],
    queryFn: getDomains,
  })

  const { data: keywords, isLoading } = useQuery<KeywordItem[]>({
    queryKey: ['keywords', search, domain],
    queryFn: () => search ? searchKeywords(search, 200) : listKeywords(domain || undefined, 1000),
  })

  const discoverMutation = useMutation({
    mutationFn: runDiscovery,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keywords'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Keywords</h2>
          <p className="text-sm text-slate-500 mt-1">
            {keywords ? `${keywords.length} keywords` : 'Loading…'}
          </p>
        </div>
        <button
          onClick={() => discoverMutation.mutate({})}
          disabled={discoverMutation.isPending}
          className="btn-primary"
        >
          {discoverMutation.isPending ? 'Discovering…' : 'Discover Seeds'}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <input
          type="text"
          className="input w-64"
          placeholder="Search keywords…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setDomain('') }}
        />
        <select
          className="input w-48"
          value={domain}
          onChange={(e) => { setDomain(e.target.value); setSearch('') }}
        >
          <option value="">All domains</option>
          {domains?.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700 bg-surface-800/50">
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Keyword</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Domain</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-400">Status</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-400">Opportunity</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-400">Gap</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-400">Trajectory</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
              )}
              {keywords?.map((kw) => (
                <tr key={kw.keyword} className="border-b border-surface-700/50 hover:bg-surface-700/30 transition-colors">
                  <td className="px-4 py-2.5 text-slate-300 font-medium">{kw.keyword}</td>
                  <td className="px-4 py-2.5 text-xs">
                    <span className="px-2 py-0.5 rounded-full bg-surface-700 text-slate-400">{kw.domain}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    {kw.scanned ? (
                      <span className="text-xs text-emerald-400">Scanned {fmtDate(kw.last_scanned_at)}</span>
                    ) : (
                      <span className="text-xs text-amber-400">Pending</span>
                    )}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${scoreColor(kw.opportunity_score || 0)}`}>
                    {kw.opportunity_score != null ? `${kw.opportunity_score.toFixed(0)}` : '—'}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${scoreColor(kw.gap_score || 0)}`}>
                    {kw.gap_score != null ? `${kw.gap_score.toFixed(0)}` : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs">
                    {kw.trajectory === 'rising' && <span className="text-emerald-400">↑ rising</span>}
                    {kw.trajectory === 'declining' && <span className="text-red-400">↓ declining</span>}
                    {kw.trajectory === 'stable' && <span className="text-slate-500">→ stable</span>}
                    {!kw.trajectory && <span className="text-slate-600">—</span>}
                  </td>
                </tr>
              ))}
              {keywords?.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No keywords found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

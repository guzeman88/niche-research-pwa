import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { getOpportunities } from '../lib/api'
import Icon from './Icon'
import { useAppMode } from '../lib/appMode'
import { getUserOpportunities } from '../lib/userData'

const BUCKETS = [
  { min: 0, max: 20, label: '0-19', color: '#5e81ac' },
  { min: 20, max: 40, label: '20-39', color: '#5e81ac' },
  { min: 40, max: 60, label: '40-59', color: '#5e81ac' },
  { min: 60, max: 80, label: '60-79', color: '#5e81ac' },
  { min: 80, max: 101, label: '80-100', color: '#5e81ac' },
]

export default function ScoreDistribution() {
  const { mode, isUserMode, userDataVersion } = useAppMode()
  const { data: opps } = useQuery({
    queryKey: ['opportunities', 'distribution', mode, userDataVersion],
    queryFn: () => isUserMode ? getUserOpportunities(500) : getOpportunities(undefined, 500),
  })

  const chartData = useMemo(() => {
    const counts = BUCKETS.map(b => ({ ...b, count: 0 }))
    if (!opps || !Array.isArray(opps)) return counts
    for (const o of opps) {
      const row = o as Record<string, unknown>
      const score = finiteScore(row.primary_score ?? row.opportunity_score ?? row.gap_score)
      if (score == null) continue
      for (const b of counts) {
        if (score >= b.min && score < b.max) { b.count++; break }
      }
    }
    return counts
  }, [opps])

  const hasVerifiedScores = chartData.some(bucket => bucket.count > 0)

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="bar-chart" size={14} className="text-primary-200" />
        <span className="section-label">Score Distribution</span>
      </div>
      {hasVerifiedScores ? (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
            <XAxis dataKey="label" tick={{ fill: '#5e81ac', fontSize: 9, fontWeight: 500 }} axisLine={false} tickLine={false} />
            <YAxis hide />
            <Tooltip contentStyle={{ background: '#303948', border: '1px solid #465365', borderRadius: '8px', fontSize: 11 }} labelStyle={{ color: '#d9e1ec' }} formatter={(v: number) => [`${v} keywords`, 'Count']} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-40 items-center justify-center text-center text-xs text-surface-400">
          Score distribution TBD until a versioned ranking model produces verified scores.
        </div>
      )}
    </div>
  )
}

function finiteScore(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

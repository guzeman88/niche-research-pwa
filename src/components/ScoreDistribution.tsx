import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { getOpportunities } from '../lib/api'
import Icon from './Icon'
import { useAppMode } from '../lib/appMode'
import { getUserOpportunities } from '../lib/userData'

const BUCKETS = [
  { min: 0, max: 45, label: '<45', color: '#bf616a' },
  { min: 45, max: 50, label: '45-49', color: '#bf616a' },
  { min: 50, max: 55, label: '50-54', color: '#ebcb8b' },
  { min: 55, max: 60, label: '55-59', color: '#ebcb8b' },
  { min: 60, max: 65, label: '60-64', color: '#81a1c1' },
  { min: 65, max: 70, label: '65-69', color: '#81a1c1' },
  { min: 70, max: 75, label: '70-74', color: '#5e81ac' },
  { min: 75, max: 80, label: '75-79', color: '#5e81ac' },
  { min: 80, max: 101, label: '80+', color: '#4c6d96' },
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
      const score = finiteScore((o as any).opportunity_score)
      if (score == null) continue
      for (const b of counts) {
        if (score >= b.min && score < b.max) { b.count++; break }
      }
    }
    return counts
  }, [opps])

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="bar-chart" size={14} className="text-primary-200" />
        <span className="section-label">Score Distribution</span>
      </div>
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
    </div>
  )
}

function finiteScore(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { SeasonalityPoint } from '../types/research'
import { monthName } from '../lib/utils'

interface Props {
  data: SeasonalityPoint[]
  peakMonths?: number[]
}

export default function SeasonalityChart({ data, peakMonths = [] }: Props) {
  if (!data.length) {
    return <p className="text-sm text-surface-300">No seasonality data available</p>
  }

  const chartData = data.map((d) => ({
    name: monthName(d.month),
    interest: d.relative_interest,
    isPeak: peakMonths.includes(d.month),
  }))

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-surface-100 mb-3">Seasonality (5-year avg)</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: -20 }}>
          <XAxis dataKey="name" tick={{ fill: '#81a1c1', fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis hide />
          <Tooltip
            contentStyle={{ background: '#434c5e', border: '1px solid #434c5e', borderRadius: '8px', fontSize: '12px' }}
            labelStyle={{ color: '#d8dee9' }}
          />
          <Bar dataKey="interest" radius={[3, 3, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.isPeak ? '#81a1c1' : '#4c6d96'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

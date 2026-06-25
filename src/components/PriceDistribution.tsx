import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { KeywordSearchData } from '../types/research'
import { fmtPrice } from '../lib/utils'
import Icon from './Icon'

interface Props { data: KeywordSearchData | null }

const BARS = [
  { key: 'min', label: 'Min', color: '#5e81ac' },
  { key: 'p25', label: '25th %', color: '#81a1c1' },
  { key: 'median', label: 'Median', color: '#5e81ac' },
  { key: 'p75', label: '75th %', color: '#81a1c1' },
  { key: 'max', label: 'Max', color: '#5e81ac' },
]

export default function PriceDistribution({ data }: Props) {
  if (!data || !data.avg_price_usd) return null

  const chartData = BARS
    .map(b => ({
      name: b.label,
      price: positiveNumber((data as any)[`price_${b.key}`]),
      color: b.color,
    }))
    .filter((item): item is { name: string; price: number; color: string } => item.price != null)

  if (chartData.length === 0) return null

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon name="dollar-sign" size={14} className="text-accent-green" />
        <span className="section-label">Price Distribution</span>
        <span className="text-[10px] text-surface-400 ml-auto">{data.total_listing_count ? `${data.total_listing_count.toLocaleString()} listings` : 'No listing count'}</span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
          <XAxis dataKey="name" tick={{ fill: '#5e81ac', fontSize: 9 }} axisLine={false} tickLine={false} />
          <YAxis hide />
          <Tooltip contentStyle={{ background: '#303948', border: '1px solid #465365', borderRadius: '8px', fontSize: 11 }} formatter={(v: number) => [`$${v.toFixed(2)}`, '']} />
          <Bar dataKey="price" radius={[3, 3, 0, 0]}>
            {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-2 mt-2 text-[10px] text-surface-200">
        <span>Sweet spot:</span>
        <span className="font-bold text-surface-50">{data.price_sweet_spot}</span>
        <span className="text-surface-400">·</span>
        <span>Mean:</span>
        <span className="font-bold text-surface-50">{fmtPrice(data.avg_price_usd)}</span>
      </div>
    </div>
  )
}

function positiveNumber(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

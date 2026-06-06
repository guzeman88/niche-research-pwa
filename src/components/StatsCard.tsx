interface Props {
  label: string
  value: string | number
  subtitle?: string
  color?: 'default' | 'green' | 'amber' | 'red' | 'blue'
}

const colorMap = {
  default: 'text-slate-200',
  green: 'text-emerald-400',
  amber: 'text-amber-400',
  red: 'text-red-400',
  blue: 'text-blue-400',
}

export default function StatsCard({ label, value, subtitle, color = 'default' }: Props) {
  return (
    <div className="card">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colorMap[color]}`}>{value}</div>
      {subtitle && <div className="text-xs text-slate-500 mt-1">{subtitle}</div>}
    </div>
  )
}

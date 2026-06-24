interface Props {
  label: string
  value: string | number
  subtitle?: string
  color?: 'default' | 'green' | 'amber' | 'red' | 'blue'
}

const colorMap = {
  default: 'text-surface-50',
  green: 'text-accent-green',
  amber: 'text-accent-amber',
  red: 'text-accent-red',
  blue: 'text-accent-blue',
}

export default function StatsCard({ label, value, subtitle, color = 'default' }: Props) {
  return (
    <div className="card">
      <div className="text-xs text-surface-300 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${colorMap[color]}`}>{value}</div>
      {subtitle && <div className="text-xs text-surface-300 mt-1">{subtitle}</div>}
    </div>
  )
}

import { scoreColor, scoreBg } from '../lib/utils'

interface Props {
  score: number
  label?: string
  size?: 'sm' | 'md' | 'lg'
}

export default function ScoreBadge({ score, label, size = 'md' }: Props) {
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-3 py-1',
    lg: 'text-lg px-4 py-2',
  }

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-sm text-slate-400">{label}</span>}
      <span
        className={`inline-flex items-center rounded-full font-semibold ${sizeClasses[size]} ${scoreColor(score)} ${scoreBg(score)}`}
      >
        {Math.round(score)}/100
      </span>
    </div>
  )
}

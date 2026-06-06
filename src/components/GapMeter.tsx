interface GapSignal {
  label: string
  score: number
  weight: number
}

interface Props {
  signals: GapSignal[]
  compositeScore: number
}

export default function GapMeter({ signals, compositeScore }: Props) {
  const maxBarWidth = 100

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Gap Analysis</h3>
        <span className={`text-lg font-bold ${compositeScore >= 60 ? 'text-emerald-400' : compositeScore >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
          {compositeScore.toFixed(0)}/100
        </span>
      </div>
      <div className="space-y-2">
        {signals.map((s) => (
          <div key={s.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-400">{s.label}</span>
              <span className="text-slate-500">wt: {s.weight.toFixed(2)}</span>
            </div>
            <div className="h-2 bg-surface-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(s.score, maxBarWidth)}%`,
                  backgroundColor: s.score >= 60 ? '#34d399' : s.score >= 40 ? '#fbbf24' : '#f87171',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

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
        <h3 className="text-sm font-semibold text-surface-100">Gap Analysis</h3>
        <span className={`text-lg font-bold ${compositeScore >= 60 ? 'text-accent-green' : compositeScore >= 40 ? 'text-accent-amber' : 'text-accent-red'}`}>
          {compositeScore.toFixed(0)}/100
        </span>
      </div>
      <div className="space-y-2">
        {signals.map((s) => (
          <div key={s.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-surface-200">{s.label}</span>
              <span className="text-surface-300">wt: {s.weight.toFixed(2)}</span>
            </div>
            <div className="progress-track h-2">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(s.score, maxBarWidth)}%`,
                  backgroundColor: s.score >= 60 ? '#a9c88f' : s.score >= 40 ? '#f0cf89' : '#c86f7a',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

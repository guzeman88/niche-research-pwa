import type { SchedulerStatus } from '../types/scheduler'

interface Props {
  status: SchedulerStatus
  onStart: (mode: string) => void
  onStop: () => void
  onPause: () => void
  onResume: () => void
  disabled?: boolean
}

const MODES = [
  { value: 'continuous', label: 'Continuous (~40/h)' },
  { value: 'burst', label: 'Burst (~180/h)' },
  { value: 'slow', label: 'Slow (~12/h)' },
]

export default function SchedulerControls({ status, onStart, onStop, onPause, onResume, disabled }: Props) {
  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3">
        {status.running ? (
          <>
            {status.paused ? (
              <button onClick={onResume} disabled={disabled} className="btn-primary">▶ Resume</button>
            ) : (
              <button onClick={onPause} disabled={disabled} className="btn-secondary">⏸ Pause</button>
            )}
            <button onClick={onStop} disabled={disabled} className="btn-danger">⏹ Stop</button>
          </>
        ) : (
          <>
            <select
              className="input w-auto"
              value={status.mode}
              onChange={(e) => onStart(e.target.value)}
              disabled={disabled}
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
            <button onClick={() => onStart(status.mode)} disabled={disabled} className="btn-primary">▶ Start</button>
          </>
        )}

        {/* Status indicators */}
        <div className="flex items-center gap-4 ml-auto text-xs">
          <div className="text-slate-500">
            Scanned: <span className="text-slate-300 font-medium">{status.keywords_scanned}</span>
          </div>
          <div className="text-slate-500">
            New seeds: <span className="text-slate-300 font-medium">{status.new_seeds_found}</span>
          </div>
          {status.current_keyword && (
            <div className="text-primary-400 truncate max-w-[120px]">
              Current: {status.current_keyword}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

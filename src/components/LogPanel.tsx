import { useEffect, useRef } from 'react'

interface LogEntry {
  level: string
  message: string
  timestamp: string
}

interface Props {
  entries: LogEntry[]
  maxHeight?: string
}

export default function LogPanel({ entries, maxHeight = 'h-64' }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries.length])

  return (
    <div className={`card overflow-hidden p-0 ${maxHeight}`}>
      <div className="flex items-center gap-2 px-4 py-2 border-b border-surface-700 bg-surface-800/50">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs font-medium text-slate-400">Live Log</span>
        <span className="text-xs text-slate-600 ml-auto">{entries.length} entries</span>
      </div>
      <div className="overflow-y-auto p-3 space-y-1 font-mono text-xs" style={{ maxHeight: 'calc(100% - 36px)' }}>
        {entries.length === 0 && (
          <p className="text-slate-600 italic">Waiting for events…</p>
        )}
        {entries.map((entry, i) => {
          const color = entry.level === 'error' ? 'text-red-400' : entry.level === 'warn' ? 'text-amber-400' : 'text-slate-400'
          const time = new Date(entry.timestamp).toLocaleTimeString()
          return (
            <div key={i} className={`${color} leading-relaxed`}>
              <span className="text-slate-600 mr-2">[{time}]</span>
              {entry.message}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

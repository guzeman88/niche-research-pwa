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
      <div className="flex items-center gap-2 px-4 py-2 border-b border-surface-500 bg-surface-800/50">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs font-medium text-surface-200">Live Log</span>
        <span className="text-xs text-surface-400 ml-auto">{entries.length} entries</span>
      </div>
      <div className="overflow-y-auto p-3 space-y-1 font-mono text-xs" style={{ maxHeight: 'calc(100% - 36px)' }}>
        {entries.length === 0 && (
          <p className="text-surface-400 italic">Waiting for events…</p>
        )}
        {entries.map((entry, i) => {
          const color = entry.level === 'error' ? 'text-accent-red' : entry.level === 'warn' ? 'text-accent-amber' : 'text-surface-200'
          const time = new Date(entry.timestamp).toLocaleTimeString()
          return (
            <div key={i} className={`${color} leading-relaxed`}>
              <span className="text-surface-400 mr-2">[{time}]</span>
              {entry.message}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

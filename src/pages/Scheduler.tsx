import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getSchedulerStatus, startScheduler, stopScheduler,
  pauseScheduler, resumeScheduler, getSchedulerHistory,
} from '../lib/api'
import SchedulerControls from '../components/SchedulerControls'
import LogPanel from '../components/LogPanel'
import { fmtDateTime } from '../lib/utils'
import type { SchedulerStatus, SchedulerHistoryItem } from '../types/scheduler'

interface LogEntry {
  level: string
  message: string
  timestamp: string
}

export default function Scheduler() {
  const queryClient = useQueryClient()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const esRef = useRef<EventSource | null>(null)

  const { data: status } = useQuery<SchedulerStatus>({
    queryKey: ['scheduler-status'],
    queryFn: getSchedulerStatus,
    refetchInterval: 3000,
  })

  const { data: history } = useQuery<SchedulerHistoryItem[]>({
    queryKey: ['scheduler-history'],
    queryFn: () => getSchedulerHistory(10),
    refetchInterval: 10_000,
  })

  // Connect SSE for live logs
  useEffect(() => {
    const es = new EventSource('/api/stream')
    esRef.current = es

    es.addEventListener('log', (e) => {
      try {
        const data = JSON.parse(e.data)
        setLogs((prev) => [...prev.slice(-300), data])
      } catch {}
    })

    es.addEventListener('error', () => {
      // Reconnect handled by browser
    })

    return () => es.close()
  }, [])

  const handleStart = useCallback(async (mode: string) => {
    await startScheduler(mode, 5)
    queryClient.invalidateQueries({ queryKey: ['scheduler-status'] })
  }, [queryClient])

  const handleStop = useCallback(async () => {
    await stopScheduler()
    queryClient.invalidateQueries({ queryKey: ['scheduler-status'] })
  }, [queryClient])

  const handlePause = useCallback(async () => {
    await pauseScheduler()
    queryClient.invalidateQueries({ queryKey: ['scheduler-status'] })
  }, [queryClient])

  const handleResume = useCallback(async () => {
    await resumeScheduler()
    queryClient.invalidateQueries({ queryKey: ['scheduler-status'] })
  }, [queryClient])

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Scheduler</h2>
        <p className="text-sm text-slate-500 mt-1">Autonomous keyword scanner</p>
      </div>

      {status && (
        <SchedulerControls
          status={status}
          onStart={handleStart}
          onStop={handleStop}
          onPause={handlePause}
          onResume={handleResume}
        />
      )}

      <LogPanel entries={logs} maxHeight="h-96" />

      {/* History */}
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Run History</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-700">
                <th className="text-left px-3 py-2 text-xs text-slate-400">Started</th>
                <th className="text-left px-3 py-2 text-xs text-slate-400">Status</th>
                <th className="text-left px-3 py-2 text-xs text-slate-400">Mode</th>
                <th className="text-right px-3 py-2 text-xs text-slate-400">Scanned</th>
                <th className="text-right px-3 py-2 text-xs text-slate-400">New Seeds</th>
              </tr>
            </thead>
            <tbody>
              {history?.map((h) => (
                <tr key={h.id} className="border-b border-surface-700/50">
                  <td className="px-3 py-2 text-slate-400">{fmtDateTime(h.started_at)}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs ${h.status === 'running' ? 'text-emerald-400' : h.status === 'stopped' ? 'text-amber-400' : 'text-slate-500'}`}>
                      {h.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-500">{h.mode}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{h.keywords_scanned}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{h.new_seeds_found}</td>
                </tr>
              ))}
              {(!history || history.length === 0) && (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-slate-500">No runs yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

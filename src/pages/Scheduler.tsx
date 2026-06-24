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
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Scheduler</h2>
          <p className="text-sm text-surface-300 mt-1">Autonomous keyword scanner</p>
        </div>
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
        <h3 className="text-sm font-semibold text-surface-100 mb-3">Run History</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-600">
                <th className="text-left px-3 py-2 text-xs text-surface-200">Started</th>
                <th className="text-left px-3 py-2 text-xs text-surface-200">Status</th>
                <th className="text-left px-3 py-2 text-xs text-surface-200">Mode</th>
                <th className="text-right px-3 py-2 text-xs text-surface-200">Scanned</th>
                <th className="text-right px-3 py-2 text-xs text-surface-200">New Seeds</th>
              </tr>
            </thead>
            <tbody>
              {history?.map((h) => (
                <tr key={h.id} className="border-b border-surface-600/45">
                  <td className="px-3 py-2 text-surface-200">{fmtDateTime(h.started_at)}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs ${h.status === 'running' ? 'text-accent-green' : h.status === 'stopped' ? 'text-accent-amber' : 'text-surface-300'}`}>
                      {h.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-surface-300">{h.mode}</td>
                  <td className="px-3 py-2 text-right text-surface-100">{h.keywords_scanned}</td>
                  <td className="px-3 py-2 text-right text-surface-100">{h.new_seeds_found}</td>
                </tr>
              ))}
              {(!history || history.length === 0) && (
                <tr><td colSpan={5} className="px-3 py-4 text-center text-surface-300">No runs yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

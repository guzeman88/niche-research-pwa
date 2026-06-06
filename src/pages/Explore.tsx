import { useState, useCallback, useRef } from 'react'
import { runResearch, getLatestReport } from '../lib/api'
import ScoreBadge from '../components/ScoreBadge'
import SeasonalityChart from '../components/SeasonalityChart'
import LogPanel from '../components/LogPanel'
import { fmt, fmtPrice, fmtDate, scoreColor } from '../lib/utils'
import type { NicheReport } from '../types/research'

interface LogEntry {
  level: string
  message: string
  timestamp: string
}

type Phase = 'idle' | 'running' | 'complete' | 'error'

export default function Explore() {
  const [keywords, setKeywords] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [report, setReport] = useState<NicheReport | null>(null)
  const [runId, setRunId] = useState('')
  const eventSourceRef = useRef<EventSource | null>(null)

  const handleSubmit = useCallback(async () => {
    const kw = keywords.split(',').map((k) => k.trim()).filter(Boolean)
    if (!kw.length) return

    setPhase('running')
    setLogs([])
    setReport(null)

    try {
      const { run_id } = await runResearch(kw, '__global__', false)
      setRunId(run_id)

      // Connect SSE stream
      const es = new EventSource(`/api/stream`)
      eventSourceRef.current = es

      es.addEventListener('log', (e) => {
        try {
          const data = JSON.parse(e.data)
          setLogs((prev) => [...prev.slice(-200), data])
        } catch {}
      })

      es.addEventListener('progress', (e) => {
        try {
          const data = JSON.parse(e.data)
          setLogs((prev) => [...prev.slice(-200), { level: 'info', message: `[${data.stage}] ${data.message}`, timestamp: new Date().toISOString() }])
        } catch {}
      })

      es.addEventListener('complete', async (e) => {
        es.close()
        setPhase('complete')
        // Fetch the full report
        try {
          const latest = await getLatestReport()
          setReport(latest as NicheReport)
        } catch {
          setLogs((prev) => [...prev, { level: 'warn', message: 'Report completed but could not fetch details', timestamp: new Date().toISOString() }])
        }
      })

      es.addEventListener('error', () => {
        es.close()
        if (phase === 'running') {
          setPhase('error')
          setLogs((prev) => [...prev, { level: 'error', message: 'SSE connection lost', timestamp: new Date().toISOString() }])
        }
      })
    } catch (err: any) {
      setPhase('error')
      setLogs((prev) => [...prev, { level: 'error', message: `Failed to start: ${err.message}`, timestamp: new Date().toISOString() }])
    }
  }, [keywords, phase])

  const handleCancel = () => {
    eventSourceRef.current?.close()
    setPhase('idle')
  }

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Explore</h2>
        <p className="text-sm text-slate-500 mt-1">Research Etsy niches with multi-source intelligence</p>
      </div>

      {/* Search bar */}
      <div className="flex gap-3">
        <input
          type="text"
          className="input flex-1"
          placeholder="Enter keywords (comma-separated), e.g. cottagecore art, botanical prints"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          disabled={phase === 'running'}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        />
        {phase === 'running' ? (
          <button onClick={handleCancel} className="btn-danger">Cancel</button>
        ) : (
          <button onClick={handleSubmit} disabled={!keywords.trim()} className="btn-primary">Research</button>
        )}
      </div>

      {/* Running state */}
      {phase === 'running' && (
        <LogPanel entries={logs} maxHeight="h-80" />
      )}

      {/* Error state */}
      {phase === 'error' && (
        <div className="card border-red-500/30 bg-red-500/5">
          <p className="text-red-400 text-sm">Research failed. Check the logs above for details.</p>
          <button onClick={() => setPhase('idle')} className="btn-secondary mt-3">Try Again</button>
        </div>
      )}

      {/* Results */}
      {report && (
        <div className="space-y-6 animate-in fade-in">
          {/* Score overview */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <ScoreCard label="Opportunity" score={report.opportunity_score} />
            <ScoreCard label="Demand" score={report.demand_score} />
            <ScoreCard label="Competition" score={report.competition_score} invert />
            <ScoreCard label="Margin" score={report.margin_score} />
            <ScoreCard label="Trend" score={report.trend_velocity_score} />
          </div>

          {/* Market metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="card">
              <div className="text-xs text-slate-500">Avg Price</div>
              <div className="text-lg font-bold text-slate-200">{fmtPrice(report.avg_price_usd)}</div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-500">Sweet Spot</div>
              <div className="text-lg font-bold text-slate-200">{report.price_sweet_spot || '—'}</div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-500">Est. Monthly Revenue</div>
              <div className="text-lg font-bold text-slate-200">{fmtPrice(report.estimated_market_monthly_revenue_usd)}</div>
            </div>
            <div className="card">
              <div className="text-xs text-slate-500">Comp. Quality</div>
              <div className="text-lg font-bold text-slate-200">{report.avg_competition_quality?.toFixed(0)}/100</div>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Seasonality */}
            <SeasonalityChart data={report.seasonality || []} peakMonths={report.peak_months || []} />

            {/* Signals summary */}
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Signal Sources ({report.sources_used?.length || 0})</h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {(report.keyword_signals || []).slice(0, 15).map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-surface-700 last:border-0">
                    <span className="text-slate-400 truncate max-w-[180px]">{s.keyword}</span>
                    <span className="text-slate-500">{s.source}</span>
                    <span className={scoreColor(s.monthly_searches > 1000 ? 70 : 40)}>{fmt(s.monthly_searches)} searches</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* LLM Synthesis */}
          {(report.keyword_clusters?.length > 0 || report.underserved_angles?.length > 0) && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">AI Synthesis</h3>

              {report.keyword_clusters?.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-slate-400 mb-2">Keyword Clusters</h4>
                  <div className="space-y-2">
                    {report.keyword_clusters.map((c, i) => (
                      <div key={i} className="p-3 rounded-lg bg-surface-700/50 border border-surface-600">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-slate-200">{c.cluster_name}</span>
                          <span className="text-xs text-slate-500">~{fmtPrice(c.estimated_monthly_revenue_potential_usd)}/mo</span>
                        </div>
                        <p className="text-xs text-slate-500">{c.rationale}</p>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {c.keywords?.map((k: string, j: number) => (
                            <span key={j} className="text-xs px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-300">{k}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {report.underserved_angles?.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-slate-400 mb-2">Underserved Angles</h4>
                  <ul className="list-disc list-inside text-sm text-slate-300 space-y-1">
                    {report.underserved_angles.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}

              {report.winning_styles?.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-slate-400 mb-2">Winning Styles</h4>
                  <div className="flex flex-wrap gap-2">
                    {report.winning_styles.map((s, i) => (
                      <span key={i} className="text-xs px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">{s}</span>
                    ))}
                  </div>
                </div>
              )}

              {report.pricing_insights && (
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-slate-400 mb-1">Pricing Insights</h4>
                  <p className="text-sm text-slate-300">{report.pricing_insights}</p>
                </div>
              )}

              {report.entry_strategy && (
                <div>
                  <h4 className="text-xs font-medium text-slate-400 mb-1">Entry Strategy</h4>
                  <p className="text-sm text-slate-300">{report.entry_strategy}</p>
                </div>
              )}
            </div>
          )}

          {/* Meta */}
          <div className="text-xs text-slate-600">
            Report ID: {report.report_id} · Generated: {fmtDate(report.generated_at)} · Sources: {report.sources_used?.join(', ')}
          </div>
        </div>
      )}

      {/* Idle state */}
      {phase === 'idle' && !report && (
        <div className="card text-center py-12">
          <div className="text-4xl mb-3">🔍</div>
          <h3 className="text-lg font-semibold text-slate-300 mb-2">Ready to research</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">
            Enter one or more seed keywords above to analyze Etsy niches.
            The pipeline will scrape real listing data, collect signals from multiple sources,
            and synthesize actionable insights.
          </p>
        </div>
      )}
    </div>
  )
}

function ScoreCard({ label, score, invert = false }: { label: string; score: number; invert?: boolean }) {
  const displayScore = invert ? 100 - score : score
  return (
    <div className="card text-center">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${scoreColor(invert ? displayScore : score)}`}>
        {Math.round(displayScore)}
      </div>
      <div className="text-xs text-slate-600">/100</div>
    </div>
  )
}

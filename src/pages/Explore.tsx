import { useState, useCallback, useRef } from 'react'
import { runResearch, getLatestReport } from '../lib/api'
import Icon from '../components/Icon'
import SeasonalityChart from '../components/SeasonalityChart'
import LogPanel from '../components/LogPanel'
import { fmt, fmtPrice, fmtDate, scoreColor } from '../lib/utils'
import type { NicheReport } from '../types/research'

interface LogEntry { level: string; message: string; timestamp: string }
type Phase = 'idle' | 'running' | 'complete' | 'error'

export default function Explore() {
  const [keywords, setKeywords] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [report, setReport] = useState<NicheReport | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const handleSubmit = useCallback(async () => {
    const kw = keywords.split(',').map(k => k.trim()).filter(Boolean)
    if (!kw.length) return
    setPhase('running'); setLogs([]); setReport(null)
    try {
      await runResearch(kw)
      const es = new EventSource('/api/stream')
      eventSourceRef.current = es
      es.addEventListener('log', e => { try { setLogs(p => [...p.slice(-200), JSON.parse(e.data)]) } catch {
        // Ignore malformed SSE log events.
      } })
      es.addEventListener('complete', async () => { es.close(); setPhase('complete'); try { setReport(await getLatestReport() as NicheReport) } catch {
        // Completion still matters even if the latest report fetch misses.
      } })
      es.addEventListener('error', () => { es.close(); if (phase === 'running') { setPhase('error'); setLogs(p => [...p, { level: 'error', message: 'Connection lost', timestamp: new Date().toISOString() }]) } })
    } catch (err: any) { setPhase('error'); setLogs(p => [...p, { level: 'error', message: `Failed: ${err.message}`, timestamp: new Date().toISOString() }]) }
  }, [keywords, phase])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="text-xl font-extrabold text-surface-50 tracking-tight">Explore</h2>
          <p className="text-[13px] text-surface-200 mt-0.5">Multi-source Etsy niche intelligence</p>
        </div>
        <span className="chip">Live research</span>
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Icon name="search" size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-300" />
          <input type="text" className="input pl-10 py-3 text-[14px] font-medium" placeholder="Enter keywords, e.g. cottagecore art, botanical prints" value={keywords} onChange={e => setKeywords(e.target.value)} disabled={phase === 'running'} onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
        </div>
        {phase === 'running'
          ? <button onClick={() => { eventSourceRef.current?.close(); setPhase('idle') }} className="btn-danger py-3 text-[13px]"><Icon name="square" size={14} />Cancel</button>
          : <button onClick={handleSubmit} disabled={!keywords.trim()} className="btn-primary px-5 py-3 text-[13px]"><Icon name="play" size={14} />Research</button>
        }
      </div>

      {phase === 'running' && <LogPanel entries={logs} maxHeight="h-72" />}
      {phase === 'error' && (
          <div className="panel-soft border-accent-red/25 bg-accent-red/5 p-4 text-[13px] text-accent-red">
          Research failed. Check the logs for details.
          <button onClick={() => setPhase('idle')} className="ml-3 underline font-semibold">Try Again</button>
        </div>
      )}

      {report && (
        <div className="space-y-5">
          {/* Score overview */}
          <div className="grid grid-cols-5 gap-2.5">
            <ScoreCard label="Opportunity" score={report.opportunity_score} />
            <ScoreCard label="Demand" score={report.demand_score} />
            <ScoreCard label="Competition" score={report.competition_score} invert />
            <ScoreCard label="Margin" score={report.margin_score} />
            <ScoreCard label="Trend" score={report.trend_velocity_score} />
          </div>

          {/* Market metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
            <div className="metric-panel p-3.5"><div className="text-[10px] text-surface-300 uppercase font-semibold tracking-wide">Avg Price</div><div className="text-lg font-extrabold text-surface-50 mt-0.5">{fmtPrice(report.avg_price_usd)}</div></div>
            <div className="metric-panel p-3.5"><div className="text-[10px] text-surface-300 uppercase font-semibold tracking-wide">Sweet Spot</div><div className="text-lg font-extrabold text-surface-50 mt-0.5">{report.price_sweet_spot || '—'}</div></div>
            <div className="metric-panel p-3.5"><div className="text-[10px] text-surface-300 uppercase font-semibold tracking-wide">Est. Revenue</div><div className="text-lg font-extrabold text-surface-50 mt-0.5">{fmtPrice(report.estimated_market_monthly_revenue_usd)}</div></div>
            <div className="metric-panel p-3.5"><div className="text-[10px] text-surface-300 uppercase font-semibold tracking-wide">Comp. Quality</div><div className="text-lg font-extrabold text-surface-50 mt-0.5">{report.avg_competition_quality?.toFixed(0) || '—'}/100</div></div>
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            <SeasonalityChart data={report.seasonality || []} peakMonths={report.peak_months || []} />
            <div className="panel p-4">
              <h3 className="text-[12px] font-bold text-surface-200 uppercase tracking-wider mb-3">Signal Sources ({report.sources_used?.length || 0})</h3>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {(report.keyword_signals || []).slice(0, 12).map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-[11px] py-1.5 border-b border-surface-600/30 last:border-0">
                    <span className="text-surface-200 truncate max-w-[140px]">{s.keyword}</span>
                    <span className="text-surface-400">{s.source}</span>
                    <span className={scoreColor(s.monthly_searches > 1000 ? 70 : 40)}>{fmt(s.monthly_searches)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* AI Synthesis */}
          {(report.keyword_clusters?.length > 0 || report.underserved_angles?.length > 0) && (
            <div className="panel p-5 space-y-4">
              <h3 className="text-[13px] font-bold text-surface-100 flex items-center gap-2"><Icon name="cpu" size={16} className="text-primary-200" />AI Synthesis</h3>
              {report.keyword_clusters?.length > 0 && report.keyword_clusters.map((c, i) => (
                <div key={i} className="rounded-lg border border-surface-600/45 bg-surface-900/45 p-4">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[13px] font-bold text-surface-50">{c.cluster_name}</span>
                    <span className="text-[11px] text-surface-300">~{fmtPrice(c.estimated_monthly_revenue_potential_usd)}/mo</span>
                  </div>
                  <p className="text-[11px] text-surface-300 mb-2">{c.rationale}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {c.keywords?.map((k: string, j: number) => <span key={j} className="text-[10px] px-2.5 py-0.5 rounded-full bg-primary-400/10 text-primary-200 font-medium border border-primary-400/15">{k}</span>)}
                  </div>
                </div>
              ))}
              {report.underserved_angles?.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-bold text-surface-200 uppercase tracking-wider mb-2">Underserved Angles</h4>
                  <ul className="list-disc list-inside text-[12px] text-surface-100 space-y-1">
                    {report.underserved_angles.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              {report.entry_strategy && (
                <div>
                  <h4 className="text-[11px] font-bold text-surface-200 uppercase tracking-wider mb-1.5">Entry Strategy</h4>
                  <p className="text-[12px] text-surface-100 leading-relaxed">{report.entry_strategy}</p>
                </div>
              )}
            </div>
          )}

          <div className="text-[11px] text-surface-400">
            Report {report.report_id} · {fmtDate(report.generated_at)} · Sources: {report.sources_used?.join(', ')}
          </div>
        </div>
      )}

      {phase === 'idle' && !report && (
        <div className="panel-soft p-12 text-center">
          <Icon name="compass" size={48} className="text-surface-400 mx-auto mb-4" />
          <h3 className="text-[15px] font-bold text-surface-200 mb-2">Ready to research</h3>
          <p className="text-[13px] text-surface-400 max-w-md mx-auto">Enter seed keywords above. The pipeline scrapes real Etsy listings, collects multi-source signals, and synthesizes insights.</p>
        </div>
      )}
    </div>
  )
}

function ScoreCard({ label, score, invert }: { label: string; score: number; invert?: boolean }) {
  const display = invert ? 100 - score : score
  return (
    <div className="metric-panel p-3 text-center">
      <div className="text-[9px] text-surface-300 uppercase font-semibold tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-extrabold tracking-tight ${scoreColor(invert ? display : score)}`}>{Math.round(display)}</div>
      <div className="text-[10px] text-surface-400">/100</div>
    </div>
  )
}

import {useState} from 'react'
import type {ReferenceReading} from '../../lib/salesIntelligence'
import {number, text} from '../../lib/sellingProducts'

export default function ReferenceHistory({readings}: {readings: ReferenceReading[]}) {
  const [selected, setSelected] = useState('')
  const key = (row: ReferenceReading) => JSON.stringify([row.basis, row.unit, row.period_start, row.period_end])
  const groups = [...new Map(readings.filter(row => row.status === 'observed' && row.precision === 'point' && row.value !== null).map(row => [key(row), row])).entries()]
  const active = groups.find(([id]) => id === selected) || groups[0]
  const rows = active ? readings.filter(row => key(row) === active[0] && row.status === 'observed' && row.precision === 'point' && row.value !== null).sort((a, b) => a.available_at.localeCompare(b.available_at)) : []
  const times = rows.map(row => new Date(row.available_at).getTime())
  const first = Math.min(...times), last = Math.max(...times)
  const maximum = Math.max(1, ...rows.map(row => row.value || 0))
  const x = (at: string) => 32 + (last === first ? .5 : (new Date(at).getTime() - first) / (last - first)) * 536
  const y = (value: number) => 120 - value / maximum * 104
  return <details>
    <summary className="cursor-pointer text-sm">Preserved reference history · {readings.length} recent readings</summary>
    {groups.length > 0 && <div className="mt-4 max-w-3xl space-y-3">
      <label className="block text-sm">Chart reporting cohort<select className="input mt-2 w-full" value={active?.[0]} onChange={event => setSelected(event.target.value)}>{groups.map(([id, row]) => <option key={id} value={id}>{text(row.basis)} · {row.unit}{row.period_end ? ` · ending ${new Date(row.period_end).toLocaleDateString()}` : ''}</option>)}</select></label>
      <p className="text-xs leading-relaxed text-surface-300">Provider readings for one reporting cohort, by when each became available. These are revisions or refreshes of estimates, not a chart of additional sales. The list below contains the plotted values and source references.</p>
      <svg viewBox="0 0 600 144" className="w-full text-surface-100" role="img" aria-label={`Reference estimates, zero to ${number(maximum)} ${active?.[1].unit}`}>
        <path d="M32 16V120H568" fill="none" stroke="currentColor" strokeWidth="1" />
        {rows.map(row => <circle key={row.id} cx={x(row.available_at)} cy={y(row.value || 0)} r="4" fill="currentColor"><title>{row.source_id}: {number(row.value)} {row.unit}, available {new Date(row.available_at).toLocaleString()}</title></circle>)}
      </svg>
      <div className="flex flex-wrap justify-between gap-2 text-xs tabular-nums text-surface-300"><span>{new Date(first).toLocaleString()}</span><span>Range 0–{number(maximum)} {active?.[1].unit}</span><span>{new Date(last).toLocaleString()}</span></div>
    </div>}
    <ul className="mt-3 divide-y divide-surface-700">{readings.map(row => <li key={row.id} className="py-3 text-sm"><p>{row.source_id} · {number(row.value)} {row.unit} · {text(row.basis)} · {text(row.precision)}</p><p className="mt-1 break-words text-xs text-surface-300">Captured {new Date(row.captured_at).toLocaleString()} · {row.source_ref}</p></li>)}</ul>
  </details>
}

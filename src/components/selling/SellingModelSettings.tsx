import { useState } from 'react'
import { sellingRequest, values, number, type Detail } from '../../lib/sellingProducts'

export default function SellingModelSettings({ item, refresh }: { item: Detail; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  const config = item.analysis.sales_model.config, trained = item.analysis.sales_model.trained_model
  const fields = [{name: 'review_rate', label: 'Review probability · 0–1', max: 1}, {name: 'view_conversion', label: 'Views to purchases · 0–1', max: 1}, {name: 'baseline_daily', label: 'Comparable baseline · purchases/day', max: 1000000}, {name: 'purchases_per_buyer', label: 'Purchases per displayed buyer · 1 or more', max: 100} ] as const
  return <div className="space-y-5">
    <details className="border-y border-surface-600 py-4"><summary className="cursor-pointer text-sm font-semibold">Model assumptions</summary>
      <form aria-label="Sales model assumptions" className="mt-4 max-w-3xl space-y-4" onSubmit={async event => {
        event.preventDefault(); const data = values(event.currentTarget); setBusy(true); setError(''); setMessage('')
        try {
          const next = {...config, ...Object.fromEntries(fields.map(({name}) => [name, data[name] === '' ? null : Number(data[name])])), review_delay_min: Number(data.review_delay_min), review_delay_max: Number(data.review_delay_max), seasonality: data.seasonality.split(',').map(Number), assumptions_note: data.assumptions_note}
          await sellingRequest(`/opportunities/${item.id}/model-config`, {config: next, expected_fingerprint: item.fingerprint}); await refresh(); setMessage('Assumptions saved. Estimates and brief freshness updated.')
        } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save model assumptions.') } finally { setBusy(false) }
      }}><p className="text-sm leading-relaxed text-surface-200">Leave unknown rates blank. With no explicit review probability, matching shop sales and shop-review readings can supply a lifetime proxy. Entering a rate is an assumption, not measured accuracy.</p>
        <div className="grid gap-4 sm:grid-cols-2">{fields.map(({name, label, max}) => <label key={name} className="text-sm">{label}<input name={name} className="input mt-2 w-full" type="number" min={name === 'purchases_per_buyer' ? 1 : 0} max={max} step="any" defaultValue={config[name] ?? ''} /></label>)}</div>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Minimum review delay · days<input className="input mt-2 w-full" name="review_delay_min" type="number" min={0} max={365} defaultValue={config.review_delay_min} required /></label><label className="text-sm">Maximum review delay · days<input className="input mt-2 w-full" name="review_delay_max" type="number" min={0} max={730} defaultValue={config.review_delay_max} required /></label></div>
        <label className="block text-sm">Seasonal multipliers · January to December<input className="input mt-2 w-full" name="seasonality" defaultValue={config.seasonality.join(', ')} required /></label>
        <label className="block text-sm">Basis for these assumptions<textarea className="input mt-2 w-full" rows={3} name="assumptions_note" defaultValue={config.assumptions_note} maxLength={1500} /></label>
        <button className="btn-secondary" disabled={busy}>{busy ? 'Saving…' : 'Save model assumptions'}</button>
      </form></details>
    <details className="border-b border-surface-600 pb-4"><summary className="cursor-pointer text-sm font-semibold">Calibration and held-out results</summary><div className="mt-4 max-w-prose space-y-4 text-sm leading-relaxed">
      <p>{item.evidence.calibration?.length || 0} recorded outcome cases. Add completed purchase counts under Evidence, or use the calibration CSV template. Cases need source references and identified shops; their authenticity remains operator-attested.</p>
      <p className="text-surface-200">Training requires 32 cases across eight shops, including 16 earlier training cases and eight later cases from at least two held-out shops. Windows for the same listing cannot overlap. These are initial validation rules, not a guarantee of accuracy.</p>
      {trained.present && <p className="font-semibold">{trained.stale ? 'Fitted model stale · recalibration required' : trained.active ? 'Fitted model active · passed baseline comparison' : 'Candidate inactive · did not beat baseline'}</p>}
      {trained.validation && <dl className="grid gap-3 sm:grid-cols-2">{[['Training cases', trained.validation.training_cases], ['Held-out cases', trained.validation.test_cases], ['Error · purchases/day', trained.validation.mae_daily], ['Baseline error · purchases/day', trained.validation.baseline_mae_daily]].map(([label, value]) => <div key={label}><dt className="text-surface-200">{label}</dt><dd className="font-semibold tabular-nums">{number(value as number)}</dd></div>)}</dl>}
      <button className="btn-secondary" disabled={busy} onClick={async () => { setBusy(true); setError(''); setMessage(''); try {
        await sellingRequest(`/opportunities/${item.id}/calibrate`, {expected_fingerprint: item.fingerprint}); await refresh(); setMessage('Calibration completed. Review held-out results before relying on the estimates.')
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Calibration failed; the saved model was preserved.') } finally { setBusy(false) } }}>Fit and evaluate model</button>
    </div></details>
    {error && <p role="alert" className="text-sm text-accent-amber">{error}</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </div>
}

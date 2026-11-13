import { useState } from 'react'
import { number, text, type Detail } from '../../lib/sellingProducts'
import SellingModelSettings from './SellingModelSettings'

export default function SellingModel({ item, refresh }: { item: Detail; refresh: () => Promise<void> }) {
  const [period, setPeriod] = useState('7')
  const model = item.analysis.sales_model
  if (!model) return <p role="status">Update the research server to use the sales model.</p>
  return <section aria-labelledby="sales-model-heading" className="space-y-6">
    <div><h3 id="sales-model-heading" className="text-lg font-semibold">EtGen sales model</h3>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-surface-200">Provisional estimates from dated evidence and explicit assumptions. Purchase messages keep their original units; a modeled range is not a verified order count.</p>
      <p className="mt-3 text-xs text-surface-300">Updated {new Date(model.as_of).toLocaleString()} · {model.version}</p></div>
    <div className="border-y border-surface-600 py-4"><h4 className="text-base font-semibold">Opportunity rating · {model.opportunity.score == null ? 'Incomplete' : `${number(model.opportunity.score)} / 100`}</h4>
      <p className="mt-2 text-sm text-surface-200">A comparison within your saved sample, not a forecast of success.</p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">{Object.entries(model.opportunity.components).map(([key, value]) => <div key={key} className="flex justify-between gap-4 text-sm"><dt>{text(key)}</dt><dd className="font-semibold tabular-nums">{value == null ? 'Needs evidence' : `${number(value * 100)} / 100`}</dd></div>)}</dl>
    </div>
    <div className="flex flex-wrap items-center gap-3"><span className="text-sm font-semibold">Estimated purchases</span>{['7', '30'].map(value => <button key={value} className={period === value ? 'btn-primary text-surface-950! hover:bg-primary-400!' : 'btn-secondary'} aria-pressed={period === value} onClick={() => setPeriod(value)}>Past {value} days</button>)}</div>
    {!model.listings.length && <div className="max-w-prose space-y-3"><h4 className="font-semibold">Add comparable products to start</h4><p className="text-sm leading-relaxed text-surface-200">Open Evidence to reuse saved listings, record purchase messages or import a permitted research file. The model updates when evidence changes.</p></div>}
    {model.listings.map(listing => {
      const window = listing.windows[period]
      return <article key={listing.listing_id} className="space-y-4 border-b border-surface-600 pb-6">
        <div><h4 className="break-words text-base font-semibold">{listing.title}</h4><p className="mt-1 break-words text-sm text-surface-200">{listing.shop || 'Shop unknown'} · {listing.listing_id}</p></div>
        <dl className="grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-surface-200">Past {period} days · provisional estimate</dt><dd className="mt-2 text-xl font-semibold tabular-nums">{window.estimate == null ? 'Insufficient evidence' : number(window.estimate)}</dd></div><div><dt className="text-sm text-surface-200">Scenario range</dt><dd className="mt-2 text-base font-semibold tabular-nums">{window.low == null ? 'Unknown' : `${number(window.low)}–${number(window.high)}`}</dd></div></dl>
        <p className="text-sm leading-relaxed text-surface-200">{number(window.coverage_days)} equivalent days supported by evidence or a fitted model. Assumptions may supply estimates for other days; {window.extrapolated_days} days have no daily estimate. {window.methods.length ? `Inputs: ${window.methods.map(text).join(', ')}.` : 'No usable conversion assumptions or model inputs yet.'}</p>
        {listing.purchase_evidence.length > 0 && <div><h5 className="text-sm font-semibold">Observed purchase messages</h5><ul className="mt-3 space-y-4">{listing.purchase_evidence.map((row, index) => <li key={index} className="break-words text-sm leading-relaxed"><blockquote>{row.raw_message}</blockquote><p className="mt-1 text-xs text-surface-200">{text(row.precision)} · {text(row.unit)} · captured {new Date(row.window_end).toLocaleString()}</p><p className="text-xs text-surface-300">{row.source_ref}</p></li>)}</ul></div>}
        {listing.shop_changes.length > 0 && <p className="text-sm text-surface-200">Latest observed shop counter change: +{number(listing.shop_changes[listing.shop_changes.length - 1]?.net_change)}. Shop totals do not identify this product’s purchases.</p>}
        {listing.issues.length > 0 && <details><summary className="cursor-pointer text-sm font-semibold">Evidence limits · {listing.issues.length}</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-surface-200">{listing.issues.map(issue => <li key={issue}>{text(issue)}</li>)}</ul></details>}
      </article>
    })}
    <SellingModelSettings item={item} refresh={refresh} />
    <details className="border-t border-surface-600 pt-4"><summary className="cursor-pointer text-sm font-semibold">How the model works</summary><div className="mt-3 max-w-prose space-y-3 text-sm leading-relaxed text-surface-200"><p>Comparable-product and seasonal assumptions provide a starting rate. Nonoverlapping purchase windows, review-counter changes and view conversion update the estimate. Reviews are spread backwards using the assumed review delay. Each evidence family contributes once, so repeated imports do not create extra votes.</p><p>Without enough daily inputs, the model leaves the total unknown. Available days may be extrapolated only after at least three supported days for a week or fourteen for a month. Scenario envelopes reflect missing coverage and disagreement; they are not confidence intervals.</p><p>Calibration fits a regularized model, testing on later periods from different shops. A candidate activates only if its held-out error beats a constant baseline. Evidence changes make the fitted model stale.</p><ul className="list-disc space-y-2 pl-5">{model.limits.map(limit => <li key={limit}>{limit}</li>)}</ul></div></details>
  </section>
}

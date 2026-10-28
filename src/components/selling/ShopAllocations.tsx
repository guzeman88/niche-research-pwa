import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {intelligenceRequest as request, type ShopAllocationOverview, type ShopAllocationReport} from '../../lib/salesIntelligence'
import {number, text} from '../../lib/sellingProducts'

const date = (value?: string) => value ? new Date(value).toLocaleString() : 'Unknown'
const assumptionText = (value?: string[] | string) => Array.isArray(value) ? value.join(' ') : value
const shopName = (shop: ShopAllocationReport) => shop.shop_label || shop.shop || `Shop ${shop.shop_id}`

export default function ShopAllocations({onSelect}: {onSelect: (id: string) => void}) {
  const [selected, setSelected] = useState('')
  const query = useQuery({queryKey: ['shop-anchored-estimates'], queryFn: () => request<ShopAllocationOverview>('/anchored'), retry: false, refetchInterval: 30000})
  const data = query.data
  const shops = [...(data?.shops || [])].sort((a, b) => Number(Boolean(b.window)) - Number(Boolean(a.window)) || shopName(a).localeCompare(shopName(b)))
  const shop = shops.find(item => item.shop_id === selected) || shops[0]
  return <section aria-label="Shop-anchored allocations" className="space-y-4">
    <div>
      <h4 className="text-base font-semibold">Shop-anchored allocations <span className="ml-2 text-sm font-normal text-surface-200">Experimental</span></h4>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-surface-200">An observed shop-counter increase anchors the total. EtGen estimates how much belongs to each tracked product and keeps an allowance for unobserved products. Counter increments have not been verified as purchases or units.</p>
    </div>
    {data && <p className="text-sm tabular-nums text-surface-200">{number(data.summary?.anchored_shops)} shops with usable counter windows · {number(data.summary?.allocated_products)} product allocations · calculated {date(data.summary?.at)}</p>}
    <p className="max-w-3xl text-sm leading-relaxed text-surface-200">Product accuracy is unvalidated. Ranges show sensitivity to assumptions about reviews, delays and missing products; they are not confidence intervals or a ±5% accuracy claim. Without independent product counts, any product could account for zero up to the observed shop increase.</p>
    {query.isPending && <p role="status" className="py-4 text-sm">Reading saved shop-counter evidence…</p>}
    {query.error && <div role="alert" className="text-sm text-accent-amber"><p>{query.error.message}</p><button className="btn-secondary mt-3" onClick={() => void query.refetch()}>Retry shop allocations</button></div>}
    {data && !shops.length && <p role="status" className="max-w-3xl border-y border-surface-700 py-5 text-sm leading-relaxed text-surface-200">No shop allocation is available yet. Track products and let the normal backend collect at least two compatible shop-counter readings spanning 24 hours. Recalculate estimates reads the saved evidence for both methods.</p>}
    {shops.length > 0 && <label className="block max-w-xl text-sm">Inspect a shop<select aria-label="Inspect a shop" className="input mt-2 block w-full" value={shop.shop_id} onChange={event => setSelected(event.target.value)}>{shops.map(item => <option key={item.shop_id} value={item.shop_id}>{shopName(item)} · {item.window ? `${number(item.window.days)} observed days` : text(item.status)}</option>)}</select></label>}
    {shop && <ShopReport shop={shop} onSelect={onSelect} />}
    {data && <details className="border-t border-surface-700 pt-4"><summary className="cursor-pointer text-sm font-semibold">Method and collection limits</summary>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">Each scenario reconciles product allocations plus the unobserved allowance with the same shop-counter change. Individual range endpoints need not add up. Review events may follow purchases by weeks; partial coverage and counter conflicts remain explicit.</p>
      {data.assumptions && <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">{assumptionText(data.assumptions)}</p>}
      {data.schedule && <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">{data.schedule}</p>}
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-surface-200">Saved allocations can be checked against independent seller records for matching products, periods and verified counter units. Reproducing a shop total is not independent validation of its product split.</p>
    </details>}
  </section>
}

function ShopReport({shop, onSelect}: {shop: ShopAllocationReport; onSelect: (id: string) => void}) {
  const products = [...shop.products].sort((a, b) => (b.value ?? -1) - (a.value ?? -1) || a.listing_id.localeCompare(b.listing_id))
  return <div className="min-w-0 border-y border-surface-600 py-5">
    <h5 className="break-words text-base font-semibold">{shopName(shop)}</h5>
    <p className="mt-2 text-sm text-surface-200">{text(shop.status)} · {shop.catalog_complete ? 'Catalog coverage declared complete' : 'Catalog coverage incomplete or unverified'}</p>
    {shop.window ? <>
      <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-4 text-sm tabular-nums">
        <div><dt className="text-surface-200">Observed shop-counter increase</dt><dd className="mt-1 text-lg font-semibold">{number(shop.window.counter_delta)}</dd></div>
        <div><dt className="text-surface-200">Observed interval</dt><dd className="mt-1 font-semibold">{number(shop.window.days)} days</dd></div>
        <div><dt className="text-surface-200">Unobserved-product allowance</dt><dd className="mt-1 font-semibold">{number(shop.unobserved?.value)} <span className="font-normal text-surface-200">({number(shop.unobserved?.low)}–{number(shop.unobserved?.high)})</span></dd></div>
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-surface-300">{date(shop.window.start)} to {date(shop.window.end)}. These allocations apply only to this observed interval.</p>
    </> : <p role="status" className="mt-4 max-w-3xl text-sm leading-relaxed text-surface-200">Product allocations are unknown for this shop. The evidence needs compatible, recent counter readings spanning at least 24 hours. Stale readings, conflicting values and decreases cannot establish a usable increase.</p>}
    <ul aria-label="Product counter allocations" className="mt-5 divide-y divide-surface-700">{products.map(product => <li key={product.listing_id} className="py-4">
      <div className="flex min-w-0 flex-col items-start justify-between gap-2 sm:flex-row sm:items-baseline sm:gap-3">
        <button className="min-w-0 break-words text-left text-sm font-semibold underline-offset-4 hover:underline sm:flex-1" onClick={() => onSelect(product.listing_id)}>{product.title || `Listing ${product.listing_id}`}</button>
        <span className="text-sm tabular-nums">{product.value == null ? 'Allocation unknown' : `${number(product.value)} allocated counter increments`}</span>
      </div>
      <p className="mt-2 text-sm text-surface-200">{product.value == null ? text(product.status) : `${number(product.low)}–${number(product.high)} sensitivity range · ${text(product.status)}`}</p>
      {product.value != null && <p className="mt-2 text-sm text-surface-200">Unresolved feasible range: {number(product.feasible_low ?? 0)}–{number(product.feasible_high ?? shop.window?.counter_delta)} counter increments.</p>}
    </li>)}</ul>
    {shop.issues && shop.issues.length > 0 && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Evidence limits · {shop.issues.length}</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-surface-200">{shop.issues.map(issue => <li key={issue}>{text(issue)}</li>)}</ul></details>}
    {shop.priority && shop.priority.length > 0 && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Evidence to improve next</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-surface-200">{shop.priority.slice(0, 5).map((item, index) => <li key={`${item.listing_id}:${index}`}>Listing {item.listing_id} · {text(item.reason)}</li>)}</ul><p className="mt-3 max-w-3xl text-sm text-surface-200">The backend uses the existing collection allowance. More observations may still leave product-level sales ambiguous.</p></details>}
  </div>
}

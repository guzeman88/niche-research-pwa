import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { productionRequest, productionIntakes, intakeSpec, type ProductionOverview, type ProductionSpec } from '../lib/production'
import ProductionSpecForm from './ProductionSpecForm'
import ProductionJobReview from './ProductionJobReview'
import ProductionTools from './ProductionTools'
import { sellingRequest } from '../lib/sellingProducts'

export default function ProductionQueue() {
  const [editor, setEditor] = useState<{spec?: ProductionSpec; productId?: string} | null>(null)
  const [selected, setSelected] = useState('')
  const opportunity = new URLSearchParams(location.search).get('opportunity')
  const intake = useQuery({queryKey: ['selling-production-intake', opportunity],
    queryFn: () => sellingRequest<ProductionSpec>(`/opportunities/${encodeURIComponent(opportunity || '')}/production-intake`), enabled: Boolean(opportunity), retry: false})
  const client = useQueryClient()
  const query = useQuery({queryKey: ['production'], queryFn: () => productionRequest<ProductionOverview>(), refetchInterval: 5000})
  const refresh = () => {void query.refetch(); void client.invalidateQueries({queryKey: ['product-validation']})}
  const pause = useMutation({mutationFn: (paused: boolean) => productionRequest('/pause', {paused}), onSuccess: refresh})
  const job = query.data?.jobs.find(item => item.id === selected) || query.data?.jobs[0]
  return <section aria-labelledby="production-heading" className="my-8 border-y border-surface-600 py-6">
    <div className="flex flex-wrap items-baseline justify-between gap-4"><h2 id="production-heading" className="text-xl font-semibold">Production queue</h2><button className="btn-primary" onClick={() => setEditor({})}>Create product specification</button></div>
    <p className="mt-3 max-w-prose text-sm text-surface-200">Generate customer files, inspect quality, and prepare a reviewed listing package. Production runs inside the app. Drafts require explicit approval; products are never activated automatically.</p>
    {intake.data && <div className="mt-4 space-y-3 border-b border-surface-600 pb-4"><p className="text-sm">Selling-product brief: {intake.data.name}. Original customer contents and actual product facts are still required.</p><button className="btn-secondary" onClick={() => setEditor({spec: intake.data})}>Review selling-product specification</button></div>}
    {intake.error && <p role="alert" className="mt-4 text-sm text-accent-amber">{intake.error.message}</p>}
    {productionIntakes().map(product => <button key={`${product.storeSlug}:${product.id}`} className="btn-secondary mt-4 mr-3" onClick={() => setEditor({spec: intakeSpec(product)})}>Review imported concept: {product.title}</button>)}
    {query.isPending && <p className="mt-4 text-sm" role="status">Loading private production records…</p>}
    {query.error && <p className="mt-4 text-sm" role="alert">{(query.error as Error).message}</p>}
    {query.data && <>
      <div className="mt-4 flex flex-wrap items-center gap-4"><span className="text-sm">{query.data.jobs.length} saved revisions · {query.data.paused ? 'Paused' : 'Enabled'}</span><button className="btn-secondary" disabled={pause.isPending} onClick={() => pause.mutate(!query.data.paused)}>{query.data.paused ? 'Resume production' : 'Pause new production jobs'}</button></div>
      <ProductionTools overview={query.data} refresh={refresh} productId={job?.product_id} />
      {!query.data.jobs.length && <p className="mt-5 max-w-prose text-sm">No production jobs yet. Start with your original content and actual product facts. Incomplete costs, provider access, or research remain visible.</p>}
      {query.data.jobs.length > 0 && <label className="mt-5 block max-w-xl text-sm">Product revision<select className="input mt-2 w-full" value={job?.id || ''} onChange={event => setSelected(event.target.value)}>{query.data.jobs.map(item => <option key={item.id} value={item.id}>{item.spec.name} · {item.status.replace(/_/g, ' ')} · {item.revision.slice(0, 8)}</option>)}</select></label>}
      {job && <ProductionJobReview key={job.id} job={job} refresh={refresh} revise={spec => setEditor({spec, productId: job.product_id})} />}
    </>}
    {pause.error && <p role="alert" className="mt-3 text-sm">{(pause.error as Error).message}</p>}
    {editor && <ProductionSpecForm key={editor.productId || 'new'} initial={editor.spec} productId={editor.productId} refresh={refresh} close={() => setEditor(null)} />}
  </section>
}

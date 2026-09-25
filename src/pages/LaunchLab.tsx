import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Icon from '../components/Icon'
import type { IconName } from '../components/Icon'
import {
  createStore,
  getOpportunityDecision,
  getStores,
  recordProductEconomics,
  searchKeywords,
  type OpportunityDecision,
  type StoreItem,
} from '../lib/api'
import { useAuth } from '../lib/auth'
import {
  createLaunchWorkflow,
  downloadLaunchPackage,
  listLaunchWorkflows,
  saveLaunchWorkflow,
  stageStatuses,
  type LaunchStageId,
  type LaunchWorkflow,
} from '../lib/launchWorkflow'
import {
  createSpecificProductIdeas,
  readStoreWorkspace,
  saveProductIdea,
  scoreListingDraft,
  type StoreKeywordCandidate,
  type StoreProductIdea,
} from '../lib/storeWorkspace'

const PRODUCT_TYPES = [
  ['digital_download', 'Digital download'],
  ['printable', 'Printable'],
  ['template', 'Editable template'],
  ['wall_art', 'Wall art'],
  ['mug', 'Mug'],
  ['tshirt', 'T-shirt'],
  ['sticker', 'Sticker'],
] as const

const STAGE_ICONS: Record<LaunchStageId, IconName> = {
  keyword: 'search',
  evidence: 'database',
  economics: 'dollar-sign',
  decision: 'target',
  product: 'package',
  package: 'file-text',
}

export default function LaunchLab() {
  const auth = useAuth()
  const queryClient = useQueryClient()
  const [workflows, setWorkflows] = useState<LaunchWorkflow[]>(() => listLaunchWorkflows())
  const [activeId, setActiveId] = useState(() => workflows[0]?.id || '')
  const active = workflows.find((workflow) => workflow.id === activeId) || null
  const [activeStage, setActiveStage] = useState<LaunchStageId>('keyword')
  const [keywordDraft, setKeywordDraft] = useState('')
  const [productTypeDraft, setProductTypeDraft] = useState('digital_download')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [approvalNote, setApprovalNote] = useState('')
  const [approvalChecked, setApprovalChecked] = useState(false)
  const [storeName, setStoreName] = useState('')
  const [targetBuyer, setTargetBuyer] = useState('')
  const [aesthetic, setAesthetic] = useState('clear, useful, evidence-led')

  const storesQuery = useQuery({ queryKey: ['stores'], queryFn: getStores })
  const store = storesQuery.data?.find((item) => item.slug === active?.storeSlug)
  const stages = active ? stageStatuses(active, store) : []
  const suggestions = useQuery({
    queryKey: ['launch-keyword-search', keywordDraft],
    queryFn: () => searchKeywords(keywordDraft.trim(), 8),
    enabled: auth.profile?.role === 'admin' && keywordDraft.trim().length >= 3,
    staleTime: 30_000,
  })

  const previewStore = active?.decision && active.approval
    ? previewStoreFromWorkflow(active, storeName, targetBuyer, aesthetic)
    : null
  const productCandidates = previewStore && active?.decision
    ? createSpecificProductIdeas(
      previewStore,
      keywordCandidate(active.decision),
      active.productType,
      3,
    )
    : []

  const persist = (workflow: LaunchWorkflow) => {
    const saved = saveLaunchWorkflow(workflow)
    const next = [saved, ...workflows.filter((item) => item.id !== saved.id)]
    setWorkflows(next)
    setActiveId(saved.id)
    return saved
  }

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await action()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'This step could not be completed. Your saved work was preserved.')
    } finally {
      setBusy(false)
    }
  }

  const refreshDecision = async (workflow: LaunchWorkflow) => {
    const decision = await getOpportunityDecision(workflow.keyword, workflow.productType)
    const fingerprintChanged = workflow.decision?.input_fingerprint !== decision.input_fingerprint
    return persist({
      ...workflow,
      decision,
      approval: fingerprintChanged ? null : workflow.approval,
    })
  }

  const beginWorkflow = async (event: FormEvent) => {
    event.preventDefault()
    const keyword = keywordDraft.trim().toLowerCase()
    if (!keyword) return
    await run(async () => {
      const workflow = createLaunchWorkflow(keyword, productTypeDraft)
      setWorkflows([workflow, ...workflows])
      setActiveId(workflow.id)
      const loaded = await refreshDecision(workflow)
      setStoreName(`${titleCase(loaded.keyword)} Studio`)
      setTargetBuyer(`Etsy shoppers searching for ${loaded.keyword}`)
      setActiveStage('evidence')
      setMessage('Evidence loaded. Missing requirements are named before any score is allowed.')
    })
  }

  if (auth.profile?.role !== 'admin') {
    return (
      <div className="page max-w-3xl">
        <div className="page-header"><h1 className="text-xl font-extrabold">Launch Lab</h1></div>
        <div className="panel mt-5 p-6">
          <h2 className="text-[15px] font-bold text-surface-50">Administrator access is required</h2>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-surface-200">
            This workflow reads private evidence and records exact costs. Ask an administrator to prepare and approve the launch decision.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page max-w-[92rem]">
      <header className="page-header flex-col items-stretch sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold tracking-tight text-surface-50">Launch Lab</h1>
          <p className="mt-0.5 max-w-3xl text-[13px] text-surface-200">
            Move one exact keyword through evidence, economics, approval, product development, and a reviewable listing package.
          </p>
        </div>
        <button
          type="button"
          className="btn-secondary w-fit shrink-0"
          onClick={() => {
            setActiveId('')
            setActiveStage('keyword')
            setKeywordDraft('')
            setMessage('')
            setError('')
          }}
        >
          <Icon name="plus-circle" size={15} /> New launch
        </button>
      </header>

      {workflows.length > 0 && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <label className="flex min-w-0 flex-col items-start gap-2 text-[12px] font-semibold text-surface-200 sm:flex-row sm:items-center">
            <span className="shrink-0">Saved launch</span>
            <select
              className="input min-w-0 max-w-md py-2"
              value={activeId}
              onChange={(event) => {
                const workflow = workflows.find((item) => item.id === event.target.value)
                setActiveId(event.target.value)
                setActiveStage(workflow ? firstOpenStage(workflow, storesQuery.data || []) : 'keyword')
                setMessage('')
                setError('')
              }}
            >
              <option value="">Start a new launch</option>
              {workflows.map((workflow) => (
                <option key={workflow.id} value={workflow.id}>
                  {workflow.keyword} · {labelProductType(workflow.productType)} · {new Date(workflow.updatedAt).toLocaleDateString()}
                </option>
              ))}
            </select>
          </label>
          {active?.decision && (
            <span className="text-[11px] font-semibold text-surface-300">
              Model {active.decision.model_version} · fingerprint {active.decision.input_fingerprint.slice(0, 10)}
            </span>
          )}
        </div>
      )}

      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[17rem_minmax(0,1fr)_19rem]">
        <aside className="panel h-fit overflow-x-auto xl:overflow-hidden" aria-label="Launch stages">
          <div className="border-b border-surface-600/55 px-4 py-3">
            <div className="text-[12px] font-bold text-surface-100">Quality gates</div>
            <div className="mt-0.5 text-[11px] text-surface-300">Each handoff keeps its source evidence.</div>
          </div>
          <ol className="flex min-w-max divide-x divide-surface-600/35 xl:block xl:min-w-0 xl:divide-x-0 xl:divide-y">
            {(active ? stages : emptyStages()).map((stage, index) => (
              <li key={stage.id} className="min-w-[8.5rem] xl:min-w-0">
                <button
                  type="button"
                  onClick={() => setActiveStage(stage.id)}
                  disabled={!active && stage.id !== 'keyword'}
                  aria-current={activeStage === stage.id ? 'step' : undefined}
                  className={`flex w-full items-start gap-2.5 px-3 py-3 text-left transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45 xl:gap-3 xl:px-4 ${
                    activeStage === stage.id ? 'bg-primary-400/12' : 'hover:bg-surface-700/35'
                  }`}
                >
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${stageTone(stage.state)}`}>
                    {stage.state === 'complete'
                      ? <Icon name="check-circle" size={15} />
                      : <span className="text-[11px] font-extrabold tabular-nums">{index + 1}</span>}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12px] font-bold text-surface-50">{stage.label}</span>
                    <span className="mt-0.5 hidden text-[10px] leading-relaxed text-surface-300 xl:block">{stage.detail}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </aside>

        <main className="min-w-0">
          <section className="panel min-h-[32rem] overflow-hidden">
            <StageHeader stage={activeStage} />
            <div className="p-4 sm:p-5">
              {activeStage === 'keyword' && (
                <KeywordStage
                  keyword={keywordDraft}
                  productType={productTypeDraft}
                  suggestions={suggestions.data || []}
                  busy={busy}
                  onKeywordChange={setKeywordDraft}
                  onProductTypeChange={setProductTypeDraft}
                  onSubmit={beginWorkflow}
                />
              )}
              {activeStage === 'evidence' && (
                <EvidenceStage workflow={active} busy={busy} onRefresh={() => active && run(async () => {
                  await refreshDecision(active)
                  setMessage('Evidence refreshed from the private source record.')
                })} />
              )}
              {activeStage === 'economics' && (
                <EconomicsStage workflow={active} busy={busy} onSubmit={(payload) => active && run(async () => {
                  await recordProductEconomics({ keyword: active.keyword, product_type: active.productType, ...payload })
                  const updated = await refreshDecision(active)
                  setActiveStage('decision')
                  setMessage(`Economics recorded. Contribution profit: ${formatMoney(updated.decision?.economics.contribution_profit_usd)}`)
                })} />
              )}
              {activeStage === 'decision' && (
                <DecisionStage
                  workflow={active}
                  note={approvalNote}
                  checked={approvalChecked}
                  onNoteChange={setApprovalNote}
                  onCheckedChange={setApprovalChecked}
                  onApprove={() => active?.decision && run(async () => {
                    const updated = persist({
                      ...active,
                      approval: {
                        acceptedAt: new Date().toISOString(),
                        operatorNote: approvalNote.trim(),
                        decisionFingerprint: active.decision!.input_fingerprint,
                      },
                    })
                    setStoreName((value) => value || `${titleCase(updated.keyword)} Studio`)
                    setTargetBuyer((value) => value || `Etsy shoppers searching for ${updated.keyword}`)
                    setActiveStage('product')
                    setMessage('Decision approved. The product brief will retain this exact evidence fingerprint.')
                  })}
                />
              )}
              {activeStage === 'product' && (
                <ProductStage
                  workflow={active}
                  candidates={productCandidates}
                  storeName={storeName}
                  targetBuyer={targetBuyer}
                  aesthetic={aesthetic}
                  busy={busy}
                  onStoreNameChange={setStoreName}
                  onTargetBuyerChange={setTargetBuyer}
                  onAestheticChange={setAesthetic}
                  onChoose={(candidate) => active && run(async () => {
                    const storeItem = await createStore(storePayload(active, storeName, targetBuyer, aesthetic))
                    const savedWorkspace = saveProductIdea(storeItem.slug, { ...candidate, storeSlug: storeItem.slug })
                    const savedProduct = savedWorkspace.products[0]
                    persist({ ...active, storeSlug: storeItem.slug, productId: savedProduct.id })
                    await queryClient.invalidateQueries({ queryKey: ['stores'] })
                    setActiveStage('package')
                    setMessage('Product brief saved. Continue through design and listing review in My Stores.')
                  })}
                />
              )}
              {activeStage === 'package' && <PackageStage workflow={active} store={store} />}
            </div>
          </section>

          {message && <p role="status" className="mt-3 rounded-md bg-accent-green/10 px-3 py-2 text-[12px] font-semibold text-accent-green">{message}</p>}
          {error && <p role="alert" className="mt-3 rounded-md bg-accent-red/10 px-3 py-2 text-[12px] font-semibold text-accent-red">{error}</p>}
        </main>

        <aside className="panel h-fit overflow-hidden">
          <div className="border-b border-surface-600/55 px-4 py-3">
            <div className="text-[12px] font-bold text-surface-100">Decision record</div>
            <div className="mt-0.5 text-[11px] text-surface-300">Facts carried into the product brief.</div>
          </div>
          {active?.decision ? <DecisionRecord decision={active.decision} approved={Boolean(active.approval)} /> : (
            <div className="p-4 text-[12px] leading-relaxed text-surface-300">
              Start with one exact keyword. A score remains unavailable until its required evidence is present.
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function KeywordStage({ keyword, productType, suggestions, busy, onKeywordChange, onProductTypeChange, onSubmit }: {
  keyword: string
  productType: string
  suggestions: Array<{ keyword: string; evidence_status?: string; sampled_listing_count?: number | null }>
  busy: boolean
  onKeywordChange: (value: string) => void
  onProductTypeChange: (value: string) => void
  onSubmit: (event: FormEvent) => void
}) {
  return (
    <form className="max-w-3xl" onSubmit={onSubmit}>
      <p className="max-w-2xl text-[13px] leading-relaxed text-surface-200">
        Choose one precise buyer phrase and the exact product format you intend to make. Product economics are evaluated per format, never borrowed from another product.
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_15rem]">
        <Field label="Exact keyword">
          <input className="input" value={keyword} onChange={(event) => onKeywordChange(event.target.value)} placeholder="teacher appreciation printable" autoComplete="off" required />
        </Field>
        <Field label="Product format">
          <select className="input" value={productType} onChange={(event) => onProductTypeChange(event.target.value)}>
            {PRODUCT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
      </div>
      {suggestions.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-md border border-surface-600/55">
          {suggestions.map((item) => (
            <button key={item.keyword} type="button" onClick={() => onKeywordChange(item.keyword)} className="flex w-full items-center justify-between gap-3 border-b border-surface-600/35 px-3 py-2 text-left last:border-b-0 hover:bg-surface-700/35">
              <span className="text-[12px] font-bold text-surface-50">{item.keyword}</span>
              <span className="text-[10px] font-semibold text-surface-300">{item.evidence_status || 'unverified'} · {item.sampled_listing_count || 0} samples</span>
            </button>
          ))}
        </div>
      )}
      <button className="btn-primary mt-5" type="submit" disabled={busy || !keyword.trim()}>
        <Icon name={busy ? 'loader' : 'arrow-right'} size={15} className={busy ? 'animate-spin' : ''} />
        {busy ? 'Loading evidence…' : 'Open evidence record'}
      </button>
    </form>
  )
}

function EvidenceStage({ workflow, busy, onRefresh }: { workflow: LaunchWorkflow | null; busy: boolean; onRefresh: () => void }) {
  if (!workflow?.decision) return <StageUnavailable text="Start a launch and load its evidence record first." />
  const decision = workflow.decision
  const pair = decision.evidence.market_pair
  const sampleReady = decision.evidence.listing_sample_count >= 10
  return (
    <div>
      <p className="max-w-3xl text-[13px] leading-relaxed text-surface-200">
        Market demand and supply are accepted only when they share a provider, geography, and reporting period. Listing samples validate that the market view has enough depth for product work.
      </p>
      <div className="mt-5 divide-y divide-surface-600/40 border-y border-surface-600/50">
        <GateRow label="Matched demand and supply" complete={Boolean(pair)} detail={pair ? `${formatNumber(pair.demand)} ${humanize(pair.demand_metric)} / ${formatNumber(pair.supply)} ${humanize(pair.supply_metric)}` : 'No matching observation pair'} />
        <GateRow label="Evidence source" complete={Boolean(pair?.source)} detail={pair ? `${humanize(pair.source)} · ${pair.geography || 'geography not supplied'} · ${pair.period_end || pair.observed_at}` : 'Import one source with both measurements'} />
        <GateRow label="Marketplace sample" complete={sampleReady} detail={`${decision.evidence.listing_sample_count} listing snapshots recorded · minimum 10`} />
        <GateRow label="Freshness" complete={decision.evidence.evidence_age_days != null && decision.evidence.evidence_age_days <= 180} detail={decision.evidence.evidence_age_days == null ? 'No valid observation date' : `${decision.evidence.evidence_age_days} days old · maximum 180`} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" disabled={busy} onClick={onRefresh}><Icon name="refresh-cw" size={14} />Refresh evidence</button>
        <Link className="btn-secondary" to={`/evidence?keyword=${encodeURIComponent(workflow.keyword)}`}><Icon name="database" size={14} />Add source evidence</Link>
      </div>
    </div>
  )
}

function EconomicsStage({ workflow, busy, onSubmit }: {
  workflow: LaunchWorkflow | null
  busy: boolean
  onSubmit: (payload: {
    source: string
    sale_price_usd: number
    production_cost_usd: number
    shipping_cost_usd: number
    marketplace_fees_usd: number
    advertising_cost_usd: number
    refund_allowance_usd: number
  }) => void
}) {
  const [values, setValues] = useState({ sale: '', production: '0', shipping: '0', fees: '', ads: '0', refunds: '0', source: 'launch cost worksheet' })
  if (!workflow) return <StageUnavailable text="Choose a keyword before entering economics." />
  const contribution = number(values.sale) - number(values.production) - number(values.shipping) - number(values.fees) - number(values.ads) - number(values.refunds)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit({
      source: values.source.trim(),
      sale_price_usd: number(values.sale),
      production_cost_usd: number(values.production),
      shipping_cost_usd: number(values.shipping),
      marketplace_fees_usd: number(values.fees),
      advertising_cost_usd: number(values.ads),
      refund_allowance_usd: number(values.refunds),
    })
  }
  return (
    <form onSubmit={submit}>
      <p className="max-w-3xl text-[13px] leading-relaxed text-surface-200">
        Enter the expected transaction economics for one {labelProductType(workflow.productType).toLowerCase()}. Use a worksheet, provider quote, or actual invoice as the source—never a hidden default.
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <MoneyField label="Sale price" value={values.sale} onChange={(value) => setValues({ ...values, sale: value })} />
        <MoneyField label="Production cost" value={values.production} onChange={(value) => setValues({ ...values, production: value })} />
        <MoneyField label="Shipping cost" value={values.shipping} onChange={(value) => setValues({ ...values, shipping: value })} />
        <MoneyField label="Marketplace fees" value={values.fees} onChange={(value) => setValues({ ...values, fees: value })} />
        <MoneyField label="Advertising allowance" value={values.ads} onChange={(value) => setValues({ ...values, ads: value })} />
        <MoneyField label="Refund allowance" value={values.refunds} onChange={(value) => setValues({ ...values, refunds: value })} />
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,1fr)_14rem] sm:items-end">
        <Field label="Evidence source">
          <input className="input" value={values.source} onChange={(event) => setValues({ ...values, source: event.target.value })} required />
        </Field>
        <div className={`rounded-md px-3 py-2.5 ${contribution > 0 ? 'bg-accent-green/10 text-accent-green' : 'bg-accent-amber/10 text-accent-amber'}`}>
          <div className="text-[10px] font-bold">Contribution per sale</div>
          <div className="mt-0.5 text-base font-extrabold tabular-nums">{formatMoney(contribution)}</div>
        </div>
      </div>
      <button className="btn-primary mt-5" type="submit" disabled={busy || !values.sale || !values.fees || !values.source.trim()}>
        <Icon name={busy ? 'loader' : 'check-circle'} size={15} className={busy ? 'animate-spin' : ''} />
        {busy ? 'Recording…' : 'Record economics and evaluate'}
      </button>
    </form>
  )
}

function DecisionStage({ workflow, note, checked, onNoteChange, onCheckedChange, onApprove }: {
  workflow: LaunchWorkflow | null
  note: string
  checked: boolean
  onNoteChange: (value: string) => void
  onCheckedChange: (value: boolean) => void
  onApprove: () => void
}) {
  if (!workflow?.decision) return <StageUnavailable text="Load the evidence record before reviewing a decision." />
  const decision = workflow.decision
  return (
    <div>
      <div className="flex flex-col gap-4 border-b border-surface-600/45 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[12px] font-semibold text-surface-300">Pre-launch opportunity score</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold tabular-nums text-surface-50">{decision.score == null ? 'TBD' : decision.score.toFixed(1)}</span>
            <span className="text-[12px] font-bold text-surface-300">/ 100</span>
          </div>
        </div>
        <DecisionBadge status={decision.status} />
      </div>
      <div className="grid border-b border-surface-600/45 sm:grid-cols-2 xl:grid-cols-4">
        <ComponentValue label="Demand" value={decision.components.demand} weight="35%" />
        <ComponentValue label="Market balance" value={decision.components.market_balance} weight="25%" />
        <ComponentValue label="Contribution" value={decision.components.contribution_margin} weight="30%" />
        <ComponentValue label="Sample depth" value={decision.components.sample_depth} weight="10%" />
      </div>
      {decision.blockers.length > 0 && (
        <div className="mt-5 rounded-md bg-accent-amber/10 p-4">
          <div className="text-[12px] font-bold text-accent-amber">Cannot advance yet</div>
          <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-surface-100">
            {decision.blockers.map((blocker) => <li key={blocker}>• {blocker}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-5 max-w-3xl">
        <Field label="Operator decision note">
          <textarea className="input min-h-24 resize-y" value={note} onChange={(event) => onNoteChange(event.target.value)} placeholder="Why this product should advance, what remains uncertain, and what would stop the launch." />
        </Field>
        <label className="mt-3 flex items-start gap-2.5 text-[12px] leading-relaxed text-surface-200">
          <input className="mt-0.5 h-4 w-4" type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />
          <span>I reviewed the source period, unit economics, model limitations, and evidence fingerprint. I understand this is not a revenue prediction.</span>
        </label>
        <button className="btn-primary mt-4" type="button" disabled={!decision.ready_to_advance || !checked || !note.trim()} onClick={onApprove}>
          <Icon name="check-circle" size={15} /> Approve product development
        </button>
      </div>
    </div>
  )
}

function ProductStage({ workflow, candidates, storeName, targetBuyer, aesthetic, busy, onStoreNameChange, onTargetBuyerChange, onAestheticChange, onChoose }: {
  workflow: LaunchWorkflow | null
  candidates: StoreProductIdea[]
  storeName: string
  targetBuyer: string
  aesthetic: string
  busy: boolean
  onStoreNameChange: (value: string) => void
  onTargetBuyerChange: (value: string) => void
  onAestheticChange: (value: string) => void
  onChoose: (candidate: StoreProductIdea) => void
}) {
  if (!workflow?.approval) return <StageUnavailable text="Approve the versioned decision before creating product concepts." />
  if (workflow.productId) return <StageUnavailable text="A product brief is already linked to this launch. Continue to the package stage." />
  return (
    <div>
      <p className="max-w-3xl text-[13px] leading-relaxed text-surface-200">
        The concepts below are constrained by the approved keyword, product format, buyer, and evidence snapshot. Choosing one creates a private store workspace and a traceable product brief.
      </p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Working store name"><input className="input" value={storeName} onChange={(event) => onStoreNameChange(event.target.value)} /></Field>
        <Field label="Target buyer"><input className="input" value={targetBuyer} onChange={(event) => onTargetBuyerChange(event.target.value)} /></Field>
        <div className="sm:col-span-2"><Field label="Aesthetic direction"><input className="input" value={aesthetic} onChange={(event) => onAestheticChange(event.target.value)} /></Field></div>
      </div>
      <div className="mt-6 divide-y divide-surface-600/40 border-y border-surface-600/50">
        {candidates.map((candidate, index) => (
          <div key={candidate.id} className="grid gap-4 py-4 lg:grid-cols-[2.5rem_minmax(0,1fr)_auto] lg:items-start">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-700/65 text-[12px] font-extrabold text-surface-200">{index + 1}</div>
            <div className="min-w-0">
              <h3 className="text-[14px] font-extrabold leading-snug text-surface-50">{candidate.title}</h3>
              <p className="mt-1 text-[12px] leading-relaxed text-surface-200">{candidate.creativeBrief?.listingAngle}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(candidate.supportingKeywords || []).slice(0, 5).map((keyword) => <span key={keyword} className="tag">{keyword}</span>)}
              </div>
            </div>
            <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" disabled={busy || !storeName.trim() || !targetBuyer.trim()} onClick={() => onChoose(candidate)}>
              <Icon name="arrow-right" size={14} /> Use this concept
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function PackageStage({ workflow, store }: { workflow: LaunchWorkflow | null; store?: StoreItem }) {
  if (!workflow?.storeSlug || !workflow.productId || !store) return <StageUnavailable text="Save a product brief before preparing the listing package." />
  const workspace = readStoreWorkspace(store.slug)
  const product = workspace.products.find((item) => item.id === workflow.productId)
  const listing = workspace.listings.find((item) => item.productId === workflow.productId)
  const listingQuality = listing ? scoreListingDraft(store, listing, product) : null
  const designReady = Boolean(product?.designQuality?.passed)
  const listingReady = Boolean(listing && Number(listingQuality?.score) >= 80)
  const packageReady = designReady && listingReady
  const href = `/stores?store=${encodeURIComponent(store.slug)}&tab=${listing ? 'listings' : 'products'}&product=${encodeURIComponent(workflow.productId)}`
  return (
    <div>
      <p className="max-w-3xl text-[13px] leading-relaxed text-surface-200">
        Finish the visual and listing gates in My Stores. Returning here reads the same account workspace, so the launch record advances without copying data between screens.
      </p>
      <div className="mt-5 divide-y divide-surface-600/40 border-y border-surface-600/50">
        <GateRow label="Product brief" complete={Boolean(product)} detail={product?.title || 'Product not found'} />
        <GateRow label="Design review" complete={designReady} detail={designReady ? `Passed at ${product?.designQuality?.score}%` : 'Generate or attach a design, then complete all design checks'} />
        <GateRow label="Listing draft" complete={Boolean(listing)} detail={listing ? listing.title : 'Send the approved product to Listing Manager'} />
        <GateRow label="Listing quality" complete={listingReady} detail={listingQuality ? `${listingQuality.score}% · ${listingQuality.grade}` : 'No listing score yet'} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link className="btn-primary" to={href}><Icon name="arrow-right" size={15} />{listing ? 'Continue listing review' : 'Continue design work'}</Link>
        <button type="button" className="btn-secondary" disabled={!packageReady} onClick={() => downloadLaunchPackage(workflow, store)}><Icon name="download" size={15} />Download launch package</button>
      </div>
      {!packageReady && <p className="mt-3 text-[11px] leading-relaxed text-surface-300">Export unlocks only after the design passes every visual check and the listing quality score reaches 80.</p>}
    </div>
  )
}

function DecisionRecord({ decision, approved }: { decision: OpportunityDecision; approved: boolean }) {
  const pair = decision.evidence.market_pair
  return (
    <div className="divide-y divide-surface-600/35 text-[11px]">
      <RecordRow label="Keyword" value={decision.keyword} />
      <RecordRow label="Product" value={labelProductType(decision.product_type)} />
      <RecordRow label="Score" value={decision.score == null ? 'TBD' : `${decision.score.toFixed(1)} · ${decision.status}`} />
      <RecordRow label="Confidence" value={`${decision.confidence.toFixed(1)} evidence completeness`} />
      <RecordRow label="Demand" value={pair ? `${formatNumber(pair.demand)} ${humanize(pair.demand_metric)}` : 'Missing'} />
      <RecordRow label="Supply" value={pair ? `${formatNumber(pair.supply)} ${humanize(pair.supply_metric)}` : 'Missing'} />
      <RecordRow label="Contribution" value={formatMoney(decision.economics.contribution_profit_usd)} />
      <RecordRow label="Samples" value={formatNumber(decision.evidence.listing_sample_count)} />
      <RecordRow label="Approval" value={approved ? 'Operator approved' : 'Not approved'} />
      <RecordRow label="Fingerprint" value={decision.input_fingerprint.slice(0, 16)} mono />
      <div className="p-4">
        <div className="font-bold text-surface-200">Model boundaries</div>
        <ul className="mt-2 space-y-1.5 leading-relaxed text-surface-300">
          {decision.model_notes.map((note) => <li key={note}>• {note}</li>)}
        </ul>
      </div>
    </div>
  )
}

function StageHeader({ stage }: { stage: LaunchStageId }) {
  const copy: Record<LaunchStageId, [string, string]> = {
    keyword: ['Choose the launch target', 'One keyword and one product format'],
    evidence: ['Verify market evidence', 'Matched measurements, fresh dates, sufficient sample'],
    economics: ['Record unit economics', 'Every cost is explicit and source-labeled'],
    decision: ['Review the decision', 'Transparent components and an operator sign-off'],
    product: ['Shape the product', 'Focused concepts tied to the approved record'],
    package: ['Complete the package', 'Design, listing quality, and export gates'],
  }
  return (
    <div className="flex items-start gap-3 border-b border-surface-600/55 px-4 py-4 sm:px-5">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary-400/14 text-primary-100"><Icon name={STAGE_ICONS[stage]} size={17} /></span>
      <div><h2 className="text-[15px] font-extrabold text-surface-50">{copy[stage][0]}</h2><p className="mt-0.5 text-[11px] text-surface-300">{copy[stage][1]}</p></div>
    </div>
  )
}

function GateRow({ label, complete, detail }: { label: string; complete: boolean; detail: string }) {
  return <div className="grid gap-2 py-3 sm:grid-cols-[1.1rem_12rem_minmax(0,1fr)] sm:items-start"><Icon name={complete ? 'check-circle' : 'alert-triangle'} size={15} className={complete ? 'text-accent-green' : 'text-accent-amber'} /><span className="text-[12px] font-bold text-surface-100">{label}</span><span className="text-[12px] leading-relaxed text-surface-300">{detail}</span></div>
}

function ComponentValue({ label, value, weight }: { label: string; value: number | null; weight: string }) {
  return <div className="border-b border-surface-600/35 px-3 py-3 sm:border-b-0 sm:border-r last:border-r-0"><div className="text-[10px] font-semibold text-surface-300">{label} · {weight}</div><div className="mt-1 text-base font-extrabold tabular-nums text-surface-50">{value == null ? 'TBD' : value.toFixed(1)}</div></div>
}

function DecisionBadge({ status }: { status: OpportunityDecision['status'] }) {
  const labels = { blocked: 'Blocked', hold: 'Hold', review: 'Review candidate', advance: 'Advance candidate' }
  const tone = status === 'advance' ? 'bg-accent-green/12 text-accent-green' : status === 'review' ? 'bg-primary-400/15 text-primary-100' : 'bg-accent-amber/12 text-accent-amber'
  return <span className={`inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold ${tone}`}><Icon name={status === 'advance' ? 'check-circle' : 'alert-triangle'} size={13} />{labels[status]}</span>
}

function RecordRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="grid gap-1 px-4 py-3"><span className="font-semibold text-surface-400">{label}</span><span className={`break-words font-bold text-surface-100 ${mono ? 'font-mono' : ''}`}>{value}</span></div>
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-[11px] font-bold text-surface-200">{label}</span>{children}</label>
}

function MoneyField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <Field label={`${label} (USD)`}><input className="input tabular-nums" type="number" min="0" step="0.01" value={value} onChange={(event) => onChange(event.target.value)} required /></Field>
}

function StageUnavailable({ text }: { text: string }) {
  return <div className="grid min-h-64 place-items-center text-center"><div><Icon name="clock" size={34} className="mx-auto text-surface-400" /><p className="mt-3 max-w-sm text-[13px] leading-relaxed text-surface-300">{text}</p></div></div>
}

function emptyStages() {
  return (['keyword', 'evidence', 'economics', 'decision', 'product', 'package'] as LaunchStageId[]).map((id, index) => ({
    id,
    label: titleCase(id),
    state: index === 0 ? 'current' as const : 'upcoming' as const,
    detail: index === 0 ? 'Choose an exact phrase' : 'Complete the prior gate first',
  }))
}

function stageTone(state: 'complete' | 'current' | 'blocked' | 'upcoming') {
  if (state === 'complete') return 'bg-accent-green/12 text-accent-green'
  if (state === 'current') return 'bg-primary-400/18 text-primary-100'
  if (state === 'blocked') return 'bg-accent-amber/12 text-accent-amber'
  return 'bg-surface-700/55 text-surface-400'
}

function firstOpenStage(workflow: LaunchWorkflow, stores: StoreItem[]): LaunchStageId {
  const store = stores.find((item) => item.slug === workflow.storeSlug)
  return stageStatuses(workflow, store).find((stage) => stage.state !== 'complete')?.id || 'package'
}

function previewStoreFromWorkflow(workflow: LaunchWorkflow, storeName: string, targetBuyer: string, aesthetic: string): StoreItem {
  return {
    slug: 'launch-preview',
    name: storeName || `${titleCase(workflow.keyword)} Studio`,
    niche: workflow.keyword,
    niche_secondary: [],
    target_audience: targetBuyer || `Etsy shoppers searching for ${workflow.keyword}`,
    product_types: [workflow.productType],
    active: true,
    created_at: workflow.createdAt,
    listing_target: 1,
    brand_voice: 'focused, useful, trustworthy',
    aesthetic,
    pricing_strategy: null,
    research_snapshot: storeResearchSnapshot(workflow),
  }
}

function keywordCandidate(decision: OpportunityDecision): StoreKeywordCandidate {
  const economics = decision.evidence.unit_economics || {}
  return {
    keyword: decision.keyword,
    product: labelProductType(decision.product_type),
    opportunity: decision.score,
    demand: decision.components.demand,
    margin: decision.components.contribution_margin,
    avgPrice: typeof economics.sale_price_usd === 'number' ? economics.sale_price_usd : null,
    competitionEase: decision.components.market_balance,
    marketEvidenceScore: decision.confidence,
    profitabilityIndex: null,
    strength: decision.score,
    source: decision.model_version,
    sources: decision.evidence.market_pair ? [decision.evidence.market_pair.source] : [],
    scoreVersion: decision.model_version,
    evidenceStatus: 'verified',
  }
}

function storePayload(workflow: LaunchWorkflow, name: string, buyer: string, aesthetic: string) {
  return {
    name: name.trim(),
    niche: workflow.keyword,
    niche_secondary: [labelProductType(workflow.productType)],
    target_audience: buyer.trim(),
    product_types: [workflow.productType],
    brand_voice: 'focused, useful, trustworthy',
    aesthetic: aesthetic.trim(),
    listing_target: 1,
    research_snapshot: storeResearchSnapshot(workflow),
  }
}

function storeResearchSnapshot(workflow: LaunchWorkflow): Record<string, unknown> {
  const decision = workflow.decision
  if (!decision) return {}
  const keyword = keywordCandidate(decision)
  return {
    source: 'launch_lab',
    decision_model: decision.model_version,
    decision_fingerprint: decision.input_fingerprint,
    decision_approved_at: workflow.approval?.acceptedAt || null,
    decision_operator_note: workflow.approval?.operatorNote || '',
    opportunity_score: decision.score,
    confidence_score: decision.confidence,
    keywords: [keyword],
    keyword_clusters: [{ id: 'launch-keyword', label: workflow.keyword, keywords: [keyword] }],
    listing_blueprints: [{
      id: 'launch-blueprint',
      title: titleCase(workflow.keyword),
      primaryKeyword: workflow.keyword,
      supportingKeywords: [],
      productType: workflow.productType,
      tags: [workflow.keyword],
      evidenceLevel: `verified by ${decision.model_version}`,
      profitRationale: `Exact contribution profit ${formatMoney(decision.economics.contribution_profit_usd)}; no revenue forecast.`,
    }],
    evidence: decision.evidence,
    risks: decision.cautions,
    validation_checklist: decision.blockers,
  }
}

function labelProductType(value: string) {
  return PRODUCT_TYPES.find(([key]) => key === value)?.[1] || titleCase(value.replace(/_/g, ' '))
}

function titleCase(value: string) {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function humanize(value: string) {
  return value.replace(/_/g, ' ')
}

function formatMoney(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? 'TBD' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)
}

function number(value: string) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

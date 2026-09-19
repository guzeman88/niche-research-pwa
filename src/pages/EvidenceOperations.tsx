import { useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import Icon from '../components/Icon'
import {
  clearConnection,
  operatorRequest,
  readConnection,
  saveConnection,
} from '../lib/operatorConnection'

interface ProviderStatus {
  available: boolean
  configured?: boolean
  healthy?: boolean
  requires_credentials?: boolean
  evidence?: string[]
  error?: string
}

interface EvidenceBundle {
  keyword: string
  latest_attempt: Record<string, unknown> | null
  latest_verified_evidence: Record<string, unknown> | null
  sources: Array<Record<string, unknown>>
  observations: Array<Record<string, unknown>>
  product_economics: Array<Record<string, unknown>>
  outcomes: Array<Record<string, unknown>>
}

const MARKET_ADAPTERS = [
  'google_suggest',
  'etsy_autocomplete',
  'etsy_open_api',
  'erank',
  'marmalead',
  'google_trends',
  'pinterest_trends',
  'reddit_etsy',
]

const MONEY_FIELDS = [
  ['sale_price_usd', 'Sale price'],
  ['production_cost_usd', 'Production cost'],
  ['shipping_cost_usd', 'Shipping cost'],
  ['marketplace_fees_usd', 'Marketplace fees'],
  ['advertising_cost_usd', 'Advertising cost'],
  ['refund_allowance_usd', 'Refund allowance'],
] as const

const OUTCOME_MONEY_FIELDS = [
  ['revenue_usd', 'Revenue'],
  ['marketplace_fees_usd', 'Marketplace fees'],
  ['advertising_cost_usd', 'Advertising cost'],
  ['production_cost_usd', 'Production cost'],
  ['shipping_cost_usd', 'Shipping cost'],
  ['refunds_usd', 'Refunds'],
] as const

export default function EvidenceOperations() {
  const initialConnection = readConnection()
  const [url, setUrl] = useState(initialConnection.url)
  const [token, setToken] = useState(initialConnection.token)
  const [connectionVersion, setConnectionVersion] = useState(0)
  const connected = Boolean(readConnection().url)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [lookup, setLookup] = useState('')
  const [selectedKeyword, setSelectedKeyword] = useState('')
  const [researchKeywords, setResearchKeywords] = useState('')
  const [selectedAdapters, setSelectedAdapters] = useState<string[]>([])
  const [mode, setMode] = useState('')
  const [batchSize, setBatchSize] = useState('')

  const providers = useQuery<Record<string, ProviderStatus>>({
    queryKey: ['provider-readiness', connectionVersion],
    queryFn: () => operatorRequest('/api/settings/adapters'),
    enabled: connected,
    retry: false,
  })
  const scheduler = useQuery<Record<string, unknown>>({
    queryKey: ['scheduler-operations', connectionVersion],
    queryFn: () => operatorRequest('/api/scheduler/status'),
    enabled: connected,
    retry: false,
  })
  const evidence = useQuery<EvidenceBundle>({
    queryKey: ['keyword-evidence', selectedKeyword, connectionVersion],
    queryFn: () => operatorRequest(`/api/evidence/${encodeURIComponent(selectedKeyword)}`),
    enabled: connected && Boolean(selectedKeyword),
    retry: false,
  })

  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body: Record<string, unknown> }) => operatorRequest<Record<string, unknown>>(path, body),
    onSuccess: async (result) => {
      setError('')
      setMessage(String(result.message || result.status || 'Recorded.'))
      await Promise.all([scheduler.refetch(), evidence.refetch()])
    },
    onError: failure => setError(failure instanceof Error ? failure.message : 'The operation failed.'),
  })

  const configuredMarketProviders = useMemo(
    () => MARKET_ADAPTERS.filter(name => providers.data?.[name]?.configured),
    [providers.data],
  )

  const connect = (event: FormEvent) => {
    event.preventDefault()
    setError('')
    try {
      saveConnection({ url, token })
      setConnectionVersion(value => value + 1)
      setMessage('Backend connection saved for this tab.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Unable to save the connection.')
    }
  }

  const disconnect = () => {
    clearConnection()
    setConnectionVersion(value => value + 1)
    setMessage('Backend disconnected. No credentials were persisted.')
  }

  const submitResearch = () => {
    const keywords = researchKeywords.split(/[,\n]/).map(value => value.trim()).filter(Boolean)
    if (!keywords.length || !selectedAdapters.length) {
      setError('Enter at least one exact keyword and choose at least one source.')
      return
    }
    action.mutate({
      path: '/api/research/run',
      body: { keywords, store_slug: '__global__', skip_scraper: false, adapter_names: selectedAdapters },
    })
  }

  return (
    <div className="page max-w-6xl">
      <div className="page-header">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight">Evidence operations</h1>
          <p className="mt-1 max-w-2xl text-[13px] text-surface-200">Collect exact observations, inspect provenance, and record real unit economics and outcomes. Blank inputs stay blank; this page never estimates them.</p>
        </div>
        <span className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] font-bold ${connected ? 'bg-accent-green/10 text-accent-green' : 'bg-surface-700/70 text-surface-200'}`}>
          <Icon name={connected ? 'wifi' : 'wifi-off'} size={15} />
          {connected ? 'Connected' : 'Not connected'}
        </span>
      </div>

      <section className="panel p-4" aria-labelledby="connection-heading">
        <h2 id="connection-heading" className="text-sm font-bold">Private backend connection</h2>
        <p className="mt-1 text-[12px] text-surface-300">The operator token stays in this browser tab and is excluded from account backups.</p>
        <form onSubmit={connect} className="mt-4 grid gap-3 lg:grid-cols-[minmax(15rem,1fr)_minmax(15rem,1fr)_auto] lg:items-end">
          <Field label="Backend origin"><input className="input" type="url" required value={url} onChange={event => setUrl(event.target.value)} placeholder="https://your-backend.example" /></Field>
          <Field label="Operator token"><input className="input" type="password" required value={token} onChange={event => setToken(event.target.value)} autoComplete="off" /></Field>
          <div className="flex gap-2"><button className="btn-primary" type="submit">Connect</button><button className="btn-secondary" type="button" onClick={disconnect}>Disconnect</button></div>
        </form>
      </section>

      {connected && (
        <>
          <section className="panel overflow-hidden" aria-labelledby="providers-heading">
            <div className="border-b border-surface-600/55 px-4 py-3">
              <h2 id="providers-heading" className="text-sm font-bold">Provider readiness</h2>
              <p className="mt-1 text-[12px] text-surface-300">Configured means the provider can be called. It does not imply that a keyword has evidence.</p>
            </div>
            {providers.isError ? <InlineError text={errorText(providers.error)} /> : (
              <div className="divide-y divide-surface-600/35">
                {MARKET_ADAPTERS.map(name => {
                  const provider = providers.data?.[name]
                  const ready = provider?.available && provider?.configured
                  return <div key={name} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div><div className="text-[13px] font-bold text-surface-50">{name.split('_').join(' ')}</div><div className="mt-0.5 text-[11px] text-surface-300">{provider?.evidence?.join(' · ') || 'Readiness not checked'}</div></div>
                    <span className={`text-[11px] font-bold ${ready ? 'text-accent-green' : 'text-accent-amber'}`}>{ready ? 'Configured' : provider?.requires_credentials ? 'Credentials required' : 'Unavailable'}</span>
                  </div>
                })}
              </div>
            )}
          </section>

          <section className="panel p-4" aria-labelledby="collection-heading">
            <h2 id="collection-heading" className="text-sm font-bold">Controlled collection</h2>
            <p className="mt-1 text-[12px] text-surface-300">Run named keywords against sources you explicitly select, or start the queue with an explicit operating mode and batch size.</p>
            <div className="mt-4 grid gap-5 lg:grid-cols-2">
              <div>
                <Field label="Exact keywords"><textarea className="input min-h-28 resize-y" value={researchKeywords} onChange={event => setResearchKeywords(event.target.value)} placeholder="One keyword per line" /></Field>
                <div className="mt-3 flex flex-wrap gap-2">
                  {configuredMarketProviders.map(name => <label key={name} className="inline-flex items-center gap-2 rounded-md bg-surface-900/55 px-3 py-2 text-[11px] font-semibold"><input type="checkbox" checked={selectedAdapters.includes(name)} onChange={event => setSelectedAdapters(current => event.target.checked ? [...current, name] : current.filter(value => value !== name))} />{name.split('_').join(' ')}</label>)}
                  {!configuredMarketProviders.length && <span className="text-[12px] text-accent-amber">No collection providers are currently configured.</span>}
                </div>
                <button className="btn-primary mt-3" type="button" disabled={action.isPending} onClick={submitResearch}><Icon name="play" size={15} />Run exact keywords</button>
              </div>
              <div className="border-t border-surface-600/45 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                <div className="flex items-center justify-between gap-3"><span className="text-[12px] font-bold">Queue status</span><span className="text-[11px] text-surface-300">{scheduler.data ? String(scheduler.data.health || 'unknown') : 'Unavailable'}</span></div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <Field label="Mode"><select className="input" value={mode} onChange={event => setMode(event.target.value)}><option value="">Choose mode</option><option value="performance">Performance</option><option value="continuous">Continuous</option><option value="burst">Burst</option><option value="slow">Slow</option></select></Field>
                  <Field label="Batch size"><input className="input" type="number" min="1" max="50" value={batchSize} onChange={event => setBatchSize(event.target.value)} placeholder="Required" /></Field>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="btn-primary" type="button" disabled={!mode || !batchSize || action.isPending} onClick={() => action.mutate({ path: '/api/scheduler/start', body: { mode, batch_size: Number(batchSize) } })}><Icon name="play" size={14} />Start</button>
                  <button className="btn-secondary" type="button" disabled={action.isPending} onClick={() => action.mutate({ path: '/api/scheduler/pause', body: {} })}><Icon name="pause" size={14} />Pause</button>
                  <button className="btn-danger" type="button" disabled={action.isPending} onClick={() => action.mutate({ path: '/api/scheduler/stop', body: {} })}><Icon name="square" size={14} />Stop</button>
                </div>
              </div>
            </div>
          </section>

          <section className="panel p-4" aria-labelledby="audit-heading">
            <h2 id="audit-heading" className="text-sm font-bold">Keyword evidence record</h2>
            <div className="mt-3 flex gap-2"><input className="input" value={lookup} onChange={event => setLookup(event.target.value)} placeholder="Exact keyword" /><button className="btn-secondary" type="button" onClick={() => setSelectedKeyword(lookup.trim().toLowerCase())}><Icon name="search" size={14} />Inspect</button></div>
            {evidence.isError && <InlineError text={errorText(evidence.error)} />}
            {evidence.data && <EvidenceSummary data={evidence.data} />}
          </section>

          <div className="grid gap-5 xl:grid-cols-2">
            <ExactDataForm title="Record unit economics" fields={MONEY_FIELDS} extraFields={[['keyword', 'Keyword'], ['product_type', 'Product type'], ['source', 'Source']]} submitLabel="Record economics" onSubmit={payload => action.mutate({ path: '/api/evidence/economics', body: payload })} />
            <ExactDataForm title="Record listing outcome" fields={OUTCOME_MONEY_FIELDS} extraFields={[['keyword', 'Keyword'], ['listing_id', 'Listing ID'], ['product_type', 'Product type'], ['period_start', 'Period start'], ['period_end', 'Period end'], ['impressions', 'Impressions'], ['clicks', 'Clicks'], ['orders', 'Orders'], ['source', 'Source']]} submitLabel="Record outcome" onSubmit={payload => action.mutate({ path: '/api/evidence/outcomes', body: payload })} />
          </div>
        </>
      )}

      {message && <p role="status" className="text-[13px] font-semibold text-accent-green">{message}</p>}
      {error && <p role="alert" className="text-[13px] font-semibold text-accent-red">{error}</p>}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="mb-1 block text-[11px] font-bold text-surface-200">{label}</span>{children}</label>
}

function InlineError({ text }: { text: string }) {
  return <p role="alert" className="m-4 rounded-md bg-accent-red/10 px-3 py-2 text-[12px] font-semibold text-accent-red">{text}</p>
}

function EvidenceSummary({ data }: { data: EvidenceBundle }) {
  const verified = data.latest_verified_evidence
  return <div className="mt-4 divide-y divide-surface-600/35 border-y border-surface-600/45 text-[12px]">
    <EvidenceRow label="Verified ranking" value={verified ? `${String(verified.score_version || 'version missing')} · ${String(verified.scanned_at || '')}` : 'TBD — no verified, versioned score'} />
    <EvidenceRow label="Latest attempt" value={data.latest_attempt ? `${String(data.latest_attempt.evidence_status || 'unknown')} · ${String(data.latest_attempt.scanned_at || '')}` : 'No attempt recorded'} />
    <EvidenceRow label="Sources" value={data.sources.length ? data.sources.map(source => String(source.source)).join(', ') : 'None recorded'} />
    <EvidenceRow label="Raw observations" value={`${data.observations.length} recorded`} />
    <EvidenceRow label="Economics" value={`${data.product_economics.length} exact records`} />
    <EvidenceRow label="Outcomes" value={`${data.outcomes.length} observed periods`} />
  </div>
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return <div className="grid gap-1 py-2.5 sm:grid-cols-[10rem_1fr]"><span className="font-bold text-surface-200">{label}</span><span className="break-words text-surface-50">{value}</span></div>
}

function ExactDataForm({ title, fields, extraFields, submitLabel, onSubmit }: {
  title: string
  fields: ReadonlyArray<readonly [string, string]>
  extraFields: ReadonlyArray<readonly [string, string]>
  submitLabel: string
  onSubmit: (payload: Record<string, unknown>) => void
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const payload: Record<string, unknown> = {}
    for (const [key] of extraFields) {
      const raw = String(form.get(key) || '').trim()
      payload[key] = ['impressions', 'clicks', 'orders'].includes(key) ? Number(raw) : raw
    }
    for (const [key] of fields) payload[key] = Number(String(form.get(key) || ''))
    onSubmit(payload)
  }
  return <form className="panel p-4" onSubmit={submit}>
    <h2 className="text-sm font-bold">{title}</h2>
    <p className="mt-1 text-[12px] text-surface-300">Every field is required and stored exactly as entered.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      {extraFields.map(([key, label]) => <Field key={key} label={label}><input className="input" name={key} required type={['impressions', 'clicks', 'orders'].includes(key) ? 'number' : key.startsWith('period_') ? 'date' : 'text'} min={['impressions', 'clicks', 'orders'].includes(key) ? '0' : undefined} /></Field>)}
      {fields.map(([key, label]) => <Field key={key} label={`${label} (USD)`}><input className="input" name={key} required type="number" min="0" step="0.01" /></Field>)}
    </div>
    <button className="btn-primary mt-4" type="submit">{submitLabel}</button>
  </form>
}

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : 'The backend request failed.'
}

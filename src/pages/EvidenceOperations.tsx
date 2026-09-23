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
  approval_required?: boolean
  integration_mode?: 'automatic' | 'approved_api' | 'import_or_private_api'
  status_reason?: string
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
  suggestions: Array<Record<string, unknown>>
  trend_points: Array<Record<string, unknown>>
  listing_snapshots: Array<Record<string, unknown>>
  collection_runs: Array<Record<string, unknown>>
}

interface EvidenceCoverage {
  coverage: Record<string, number>
  metrics: Record<string, number>
  observation_sources: Array<Record<string, unknown>>
  suggestion_sources: Array<Record<string, unknown>>
  recent_runs: Array<Record<string, unknown>>
  durability: {
    cloud_sync_configured: boolean
    run_statuses: Record<string, number>
  }
}

interface CollectionQuality {
  generated_at: string
  window_hours: number
  target_min_pct: number
  target_max_pct: number
  sources: Array<{
    source: string
    metric: string
    purpose: string
    configured: boolean | null
    status: string | null
    collection_rate_pct: number | null
    quality_yield_pct: number | null
    collected: number | null
    eligible_or_available: number | null
    new_rows: number | null
    target_status: 'on_target' | 'below_target' | 'tbd' | 'not_configured'
  }>
}

type ImportSource = 'etsy_marketplace_insights' | 'erank' | 'marmalead' | 'etsy_shop_stats' | 'google_keyword_planner' | 'google_trends' | 'pinterest_trends'

const MARKET_ADAPTERS = [
  'google_suggest',
  'etsy_autocomplete',
  'etsy_open_api',
  'erank',
  'marmalead',
  'google_trends',
  'google_daily_trends',
  'pinterest_trends',
  'reddit_etsy',
]

const IMPORT_SOURCES: Array<{ value: ImportSource; label: string; help: string }> = [
  { value: 'etsy_marketplace_insights', label: 'Etsy Marketplace Insights', help: 'Keyword searches and competing listings from Etsy\'s seller tool.' },
  { value: 'erank', label: 'eRank free export', help: 'Searches, clicks, click rate, and competition exactly as exported.' },
  { value: 'marmalead', label: 'Marmalead export', help: 'Search, engagement, and competition values exactly as supplied by Marmalead.' },
  { value: 'etsy_shop_stats', label: 'Etsy Shop Stats', help: 'Search terms tied to your own visits, views, orders, and revenue.' },
  { value: 'google_keyword_planner', label: 'Google Keyword Planner', help: 'Google monthly searches, competition, and optional bid ranges with an explicit geography and reporting period.' },
  { value: 'google_trends', label: 'Google Trends CSV', help: 'The complete dated relative-interest series, not a single average.' },
  { value: 'pinterest_trends', label: 'Pinterest Trends CSV', help: 'Official ranked, growth, normalized-volume, and dated trend data. Capped values stay explicit bounds.' },
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
  const [importSource, setImportSource] = useState<ImportSource>('etsy_marketplace_insights')
  const [importName, setImportName] = useState('')
  const [importText, setImportText] = useState('')
  const [importGeography, setImportGeography] = useState('')
  const [importPeriodStart, setImportPeriodStart] = useState('')
  const [importPeriodEnd, setImportPeriodEnd] = useState('')
  const [importCurrency, setImportCurrency] = useState('')

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
  const coverage = useQuery<EvidenceCoverage>({
    queryKey: ['evidence-coverage', connectionVersion],
    queryFn: () => operatorRequest('/api/evidence/coverage'),
    enabled: connected,
    retry: false,
  })
  const quality = useQuery<CollectionQuality>({
    queryKey: ['collection-quality', connectionVersion],
    queryFn: () => operatorRequest('/api/evidence/quality'),
    enabled: connected,
    retry: false,
  })

  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body: Record<string, unknown> }) => operatorRequest<Record<string, unknown>>(path, body),
    onSuccess: async (result) => {
      setError('')
      setMessage(String(result.message || result.status || 'Recorded.'))
      await Promise.all([scheduler.refetch(), evidence.refetch(), coverage.refetch(), quality.refetch()])
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
      body: { keywords, store_slug: '__global__', skip_scraper: !selectedAdapters.includes('etsy_open_api'), adapter_names: selectedAdapters },
    })
  }

  const submitImport = () => {
    if (!importText.trim()) {
      setError('Paste the source export before importing.')
      return
    }
    if (importSource === 'etsy_marketplace_insights' && (!importPeriodStart || !importPeriodEnd)) {
      setError('Marketplace Insights needs the exact start and end dates shown by the export.')
      return
    }
    if (importSource === 'google_trends' && !importGeography.trim()) {
      setError('Google Trends needs the geography used for the export.')
      return
    }
    if (importSource === 'etsy_shop_stats' && (!importPeriodStart || !importPeriodEnd)) {
      setError('Etsy Shop Stats needs the exact reporting period.')
      return
    }
    if (importSource === 'google_keyword_planner' && (!importPeriodStart || !importPeriodEnd || !importGeography.trim())) {
      setError('Google Keyword Planner needs the exact reporting period and geography.')
      return
    }
    action.mutate({
      path: '/api/evidence/import',
      body: {
        source: importSource,
        name: importName.trim() || null,
        text: importText,
        geography: importGeography.trim() || null,
        period_start: importPeriodStart || null,
        period_end: importPeriodEnd || null,
        currency_code: importCurrency.trim().toUpperCase() || null,
      },
    })
  }

  return (
    <div className="page max-w-6xl">
      <div className="page-header flex-col items-start gap-3 sm:flex-row sm:items-center">
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
                  const importOnly = provider?.integration_mode === 'import_or_private_api' && !provider?.configured
                  const status = ready ? 'Configured' : importOnly ? 'Import available' : provider?.approval_required ? 'Approval required' : provider?.requires_credentials ? 'Credentials required' : 'Unavailable'
                  return <div key={name} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div><div className="text-[13px] font-bold text-surface-50">{name.split('_').join(' ')}</div><div className="mt-0.5 text-[11px] text-surface-300">{provider?.evidence?.join(' · ') || 'Readiness not checked'}</div>{provider?.status_reason && <div className="mt-1 max-w-3xl text-[11px] leading-relaxed text-surface-300">{provider.status_reason}</div>}</div>
                    <span className={`shrink-0 text-[11px] font-bold ${ready ? 'text-accent-green' : 'text-accent-amber'}`}>{status}</span>
                  </div>
                })}
              </div>
            )}
          </section>

          <section className="panel overflow-hidden" aria-labelledby="coverage-heading">
            <div className="border-b border-surface-600/55 px-4 py-3">
              <h2 id="coverage-heading" className="text-sm font-bold">Evidence coverage</h2>
              <p className="mt-1 text-[12px] text-surface-300">Counts show what is actually stored. No coverage percentage or opportunity score is inferred.</p>
            </div>
            {coverage.isError ? <InlineError text={errorText(coverage.error)} /> : (
              <>
                <div className="grid sm:grid-cols-2 xl:grid-cols-4">
                  <CoverageValue label="Candidate phrases" value={coverage.data?.coverage.candidate_keywords} />
                  <CoverageValue label="Buyer demand" value={coverage.data?.coverage.keywords_with_demand} />
                  <CoverageValue label="Marketplace supply" value={coverage.data?.coverage.keywords_with_supply} />
                  <CoverageValue label="Trend series" value={coverage.data?.coverage.keywords_with_trend_series} />
                  <CoverageValue label="Listing samples" value={coverage.data?.coverage.keywords_with_listing_samples} />
                  <CoverageValue label="Own-shop outcomes" value={coverage.data?.coverage.keywords_with_shop_outcomes} />
                  <CoverageValue label="Unit economics" value={coverage.data?.coverage.keywords_with_unit_economics} />
                  <CoverageValue label="Any observation" value={coverage.data?.coverage.keywords_with_any_observation} />
                </div>
                <div className="flex flex-col gap-1 border-t border-surface-600/45 px-4 py-3 text-[11px] sm:flex-row sm:items-center sm:justify-between">
                  <span className="font-bold text-surface-200">Durable cloud copy</span>
                  <span className={coverage.data?.durability.cloud_sync_configured ? 'text-accent-green' : 'text-accent-amber'}>{coverage.data?.durability.cloud_sync_configured ? 'Configured — completed runs sync to Supabase' : 'Not configured — evidence remains on this backend filesystem'}</span>
                </div>
              </>
            )}
          </section>

          <section className="panel overflow-hidden" aria-labelledby="quality-heading">
            <div className="border-b border-surface-600/55 px-4 py-3">
              <h2 id="quality-heading" className="text-sm font-bold">Collection quality</h2>
              <p className="mt-1 text-[12px] text-surface-300">Measured work completed in the last {quality.data?.window_hours ?? 24} hours. Target: 80–100%. Missing denominators stay TBD.</p>
            </div>
            {quality.isError ? <InlineError text={errorText(quality.error)} /> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[48rem] text-left text-[12px]">
                  <thead className="bg-surface-900/45 text-[10px] uppercase tracking-wide text-surface-300">
                    <tr><th className="px-4 py-2">Source</th><th className="px-4 py-2">Rate</th><th className="px-4 py-2">Measured</th><th className="px-4 py-2">Useful yield</th><th className="px-4 py-2">Used for</th></tr>
                  </thead>
                  <tbody className="divide-y divide-surface-600/35">
                    {(quality.data?.sources || []).map(row => {
                      const onTarget = row.target_status === 'on_target'
                      const measured = row.collected != null && row.eligible_or_available != null ? `${row.collected.toLocaleString()} / ${row.eligible_or_available.toLocaleString()}` : 'TBD'
                      return <tr key={row.source}>
                        <td className="px-4 py-3 font-bold text-surface-50">{row.source.split('_').join(' ')}</td>
                        <td className={`px-4 py-3 font-bold ${onTarget ? 'text-accent-green' : row.collection_rate_pct == null ? 'text-surface-300' : 'text-accent-amber'}`}>{row.collection_rate_pct == null ? 'TBD' : `${row.collection_rate_pct}%`}</td>
                        <td className="px-4 py-3 tabular-nums text-surface-200">{measured}</td>
                        <td className="px-4 py-3 tabular-nums text-surface-200">{row.quality_yield_pct == null ? 'TBD' : `${row.quality_yield_pct}%`}</td>
                        <td className="max-w-sm px-4 py-3 text-surface-300">{row.purpose}</td>
                      </tr>
                    })}
                  </tbody>
                </table>
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
                {configuredMarketProviders.length > 0 && <button className="mt-2 text-[11px] font-bold text-primary-200 hover:text-primary-100" type="button" onClick={() => setSelectedAdapters(configuredMarketProviders)}>Select every ready source</button>}
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

          <section className="panel p-4" aria-labelledby="imports-heading">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-primary-200"><Icon name="database" size={18} /></span>
              <div>
                <h2 id="imports-heading" className="text-sm font-bold">Import free first-party and seller-tool evidence</h2>
                <p className="mt-1 max-w-3xl text-[12px] text-surface-300">Paste CSV or tab-separated exports. The importer stores source values, dates, geography, and units exactly; missing cells remain missing.</p>
              </div>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(14rem,0.7fr)_minmax(20rem,1.3fr)]">
              <div className="grid content-start gap-3">
                <Field label="Source"><select className="input" value={importSource} onChange={event => setImportSource(event.target.value as ImportSource)}>{IMPORT_SOURCES.map(source => <option key={source.value} value={source.value}>{source.label}</option>)}</select></Field>
                <p className="text-[11px] leading-relaxed text-surface-300">{IMPORT_SOURCES.find(source => source.value === importSource)?.help}</p>
                <Field label="Import name (optional)"><input className="input" value={importName} onChange={event => setImportName(event.target.value)} placeholder="Export filename or note" /></Field>
                {(importSource === 'etsy_marketplace_insights' || importSource === 'etsy_shop_stats' || importSource === 'google_keyword_planner') && <div className="grid grid-cols-2 gap-3"><Field label="Period start"><input className="input" type="date" value={importPeriodStart} onChange={event => setImportPeriodStart(event.target.value)} /></Field><Field label="Period end"><input className="input" type="date" value={importPeriodEnd} onChange={event => setImportPeriodEnd(event.target.value)} /></Field></div>}
                {(importSource === 'google_trends' || importSource === 'pinterest_trends' || importSource === 'google_keyword_planner' || importSource === 'etsy_marketplace_insights' || importSource === 'erank' || importSource === 'marmalead') && <Field label="Geography (when shown)"><input className="input" value={importGeography} onChange={event => setImportGeography(event.target.value)} placeholder="US, worldwide, or export value" /></Field>}
                {(importSource === 'etsy_shop_stats' || importSource === 'google_keyword_planner') && <Field label="Currency (when money columns are included)"><input className="input uppercase" maxLength={3} value={importCurrency} onChange={event => setImportCurrency(event.target.value)} placeholder="USD" /></Field>}
              </div>
              <div>
                <Field label="Export data"><textarea className="input min-h-56 resize-y font-mono text-[11px] leading-relaxed" value={importText} onChange={event => setImportText(event.target.value)} placeholder="Paste the unedited CSV or TSV export here" /></Field>
                <button className="btn-primary mt-3" type="button" disabled={action.isPending} onClick={submitImport}><Icon name="database" size={15} />{action.isPending ? 'Recording…' : 'Record source evidence'}</button>
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
    <EvidenceRow label="Autocomplete" value={`${data.suggestions.length} dated suggestions`} />
    <EvidenceRow label="Trend history" value={`${data.trend_points.length} dated points`} />
    <EvidenceRow label="Listing sample" value={`${data.listing_snapshots.length} listing snapshots`} />
    <EvidenceRow label="Collection runs" value={`${data.collection_runs.length} linked attempts`} />
    <EvidenceRow label="Economics" value={`${data.product_economics.length} exact records`} />
    <EvidenceRow label="Outcomes" value={`${data.outcomes.length} observed periods`} />
  </div>
}

function CoverageValue({ label, value }: { label: string; value: number | undefined }) {
  return <div className="border-b border-surface-600/35 px-4 py-3 sm:border-r">
    <div className="text-[11px] font-semibold text-surface-300">{label}</div>
    <div className="mt-1 text-base font-extrabold tabular-nums text-surface-50">{value == null ? 'TBD' : value.toLocaleString()}</div>
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

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { generateDesignAsset, getDesignProviders, getStores } from '../lib/api'
import type { DesignProviderInfo, GeneratedDesignAsset, StoreItem } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { StoresSkeleton } from '../components/Skeleton'
import {
  createListingFromProduct,
  createSpecificProductIdeas,
  designQualityChecklist,
  emptyWorkspace,
  evaluateDesignQuality,
  extractKeywordClusters,
  extractStoreKeywords,
  readStoreWorkspace,
  saveListingDraft,
  saveProductIdea,
  scoreListingDraft,
  scoreProductTypeFit,
  updateListingDraft,
  updateProductIdea,
  validationItems,
  workspaceExport,
  type ListingStatus,
  type ProductStatus,
  type ProductTypeFit,
  type StoreProductDesignAsset,
  type StoreKeywordCandidate,
  type StoreListingDraft,
  type StoreListingPerformance,
  type StoreProductIdea,
  type StoreWorkspace,
} from '../lib/storeWorkspace'
import { fmtPrice, scoreColor } from '../lib/utils'
import { useAppMode, type AppMode } from '../lib/appMode'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']
const TABS = [
  { id: 'dashboard', label: 'Store Dashboard', shortLabel: 'Store', icon: 'dashboard' },
  { id: 'products', label: 'Product Creator', shortLabel: 'Products', icon: 'package' },
  { id: 'listings', label: 'Listing Manager', shortLabel: 'Listings', icon: 'file-text' },
] as const
const DESIGN_PROVIDERS = [
  { id: 'ideogram', label: 'Ideogram', fit: 'Text' },
  { id: 'recraft', label: 'Recraft', fit: 'Vector' },
  { id: 'krea', label: 'Krea', fit: 'Style' },
  { id: 'openai', label: 'OpenAI', fit: 'General' },
  { id: 'firefly', label: 'Firefly', fit: 'Safe' },
  { id: 'stability', label: 'Stability', fit: 'Art' },
  { id: 'fal', label: 'fal', fit: 'Fast' },
  { id: 'replicate', label: 'Replicate', fit: 'Models' },
  { id: 'bfl', label: 'BFL', fit: 'Flux' },
  { id: 'gemini', label: 'Gemini', fit: 'Smart' },
  { id: 'luma', label: 'Luma', fit: 'Photo' },
  { id: 'magnific', label: 'Magnific', fit: 'Detail' },
  { id: 'leonardo', label: 'Leonardo', fit: 'Styles' },
  { id: 'midjourney', label: 'Midjourney', fit: 'Manual' },
  { id: 'local_svg', label: 'Built-in', fit: 'Test' },
] as const
const PROMPT_LAUNCHERS = [
  { id: 'ideogram_web', label: 'Ideogram', fit: 'Text', url: 'https://ideogram.ai/', promptProvider: 'ideogram' },
  { id: 'recraft_web', label: 'Recraft', fit: 'Vector', url: 'https://www.recraft.ai/', promptProvider: 'recraft' },
  { id: 'krea_web', label: 'Krea', fit: 'Style', url: 'https://www.krea.ai/', promptProvider: 'krea' },
  { id: 'leonardo_web', label: 'Leonardo', fit: 'Art', url: 'https://leonardo.ai/', promptProvider: 'leonardo' },
  { id: 'firefly_web', label: 'Firefly', fit: 'Safe', url: 'https://firefly.adobe.com/', promptProvider: 'firefly' },
  { id: 'designer_web', label: 'Designer', fit: 'Free', url: 'https://designer.microsoft.com/', promptProvider: 'gemini' },
] as const

type WorkspaceTab = typeof TABS[number]['id']
type DesignProviderId = typeof DESIGN_PROVIDERS[number]['id']
type PromptLauncherId = typeof PROMPT_LAUNCHERS[number]['id']
type ProviderStatus = 'ready' | 'needs_key' | 'manual' | 'unsupported' | 'billing_locked'

interface ManualDesignAsset {
  asset_url: string
  title: string
  prompt: string
  content_type: string
  provider: string
}

export default function Stores() {
  const qc = useQueryClient()
  const { mode } = useAppMode()
  const { data: rawStores, isLoading, isError } = useQuery<StoreItem[]>({ queryKey: ['stores'], queryFn: getStores })
  const { data: designProviders } = useQuery<DesignProviderInfo[]>({ queryKey: ['design-providers'], queryFn: getDesignProviders })
  const stores = useMemo(() => (rawStores || []).filter((store) => storeMatchesMode(store, mode)), [rawStores, mode])
  const [selected, setSelected] = useState<string>('')
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('dashboard')
  const [workspaceVersion, setWorkspaceVersion] = useState(0)
  const current = stores.find((store) => store.slug === selected)
  const workspace = useMemo(
    () => current ? readStoreWorkspace(current.slug) : emptyWorkspace(),
    [current, workspaceVersion],
  )
  const showDetail = !!current
  const refresh = () => {
    setWorkspaceVersion((value) => value + 1)
    return qc.refetchQueries({ type: 'active' })
  }

  const colorFor = (slug: string) => COLORS[Math.max(0, stores.findIndex((store) => store.slug === slug)) % COLORS.length]

  const saveProduct = (store: StoreItem, product: StoreProductIdea) => {
    saveProductIdea(store.slug, product)
    setWorkspaceVersion((value) => value + 1)
  }

  const updateProduct = (store: StoreItem, productId: string, patch: Partial<StoreProductIdea>) => {
    updateProductIdea(store.slug, productId, patch)
    setWorkspaceVersion((value) => value + 1)
  }

  const saveListing = (store: StoreItem, listing: StoreListingDraft) => {
    saveListingDraft(store.slug, listing)
    setWorkspaceVersion((value) => value + 1)
  }

  const updateListing = (store: StoreItem, listingId: string, patch: Partial<StoreListingDraft>) => {
    updateListingDraft(store.slug, listingId, patch)
    setWorkspaceVersion((value) => value + 1)
  }

  const sendProductToListings = (store: StoreItem, product: StoreProductIdea) => {
    const alreadyExists = workspace.listings.some((listing) => listing.productId === product.id)
    if (!alreadyExists) {
      saveListingDraft(store.slug, createListingFromProduct(store, product))
      updateProductIdea(store.slug, product.id, { status: 'sent_to_listing' })
      setWorkspaceVersion((value) => value + 1)
    }
    setActiveTab('listings')
  }

  if (!rawStores && isLoading) return <StoresSkeleton />

  const masterList = (
    <div className="flex h-full flex-col">
      <div className="border-b border-surface-600/60 bg-surface-900/45 px-4 pb-3 pt-4">
        <h2 className="text-xl font-extrabold tracking-tight text-surface-50">My Stores</h2>
        <p className="mt-0.5 text-[12px] text-surface-300">{stores.length} stores / {stores.filter((store) => store.active).length} active</p>
      </div>
      <div className="flex-1 space-y-1.5 overflow-y-auto px-3 py-2">
        {isLoading && <p className="py-12 text-center text-xs text-surface-300">Loading...</p>}
        {stores.map((store) => {
          const color = colorFor(store.slug)
          return (
            <button
              key={store.slug}
              onClick={() => {
                setSelected(store.slug)
                setActiveTab('dashboard')
              }}
              className="flex w-full items-center gap-3.5 rounded-lg p-3.5 text-left transition-all duration-150 active:scale-[0.98]"
              style={{ backgroundColor: selected === store.slug ? color + '12' : '#303948', border: `1px solid ${selected === store.slug ? color + '38' : '#465365'}` }}
            >
              <span
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-[15px] font-extrabold"
                style={{ backgroundColor: color + '15', color, border: `1px solid ${color}30` }}
              >
                {store.name[0]}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold text-surface-50">{store.name}</span>
                <span className="mt-0.5 block truncate text-[11px] text-surface-300">{store.niche}</span>
              </span>
              <Icon name="chevron-right" size={16} className="flex-shrink-0 text-surface-400" />
            </button>
          )
        })}
        {stores.length === 0 && !isLoading && (
          <div className="py-12 text-center">
            <Icon name="package" size={40} className="mx-auto mb-3 text-surface-400" />
            <p className="text-[13px] text-surface-300">No stores yet</p>
            <p className="mt-1 text-[11px] text-surface-400">
              {isError ? 'Stores saved on this device will still appear here.' : 'Saved stores will appear here.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )

  const detailView = current && (
    <StoreWorkspaceView
      store={current}
      workspace={workspace}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      onBack={() => setSelected('')}
      onSaveProduct={(product) => saveProduct(current, product)}
      onUpdateProduct={(productId, patch) => updateProduct(current, productId, patch)}
      onSaveListing={(listing) => saveListing(current, listing)}
      onUpdateListing={(listingId, patch) => updateListing(current, listingId, patch)}
      onSendProductToListings={(product) => sendProductToListings(current, product)}
      designProviders={designProviders || []}
    />
  )

  return (
    <PullToRefresh onRefresh={refresh}>
      <>
        <div className="hidden h-full lg:flex">
          <div className="w-80 flex-shrink-0 border-r border-surface-600/60 bg-surface-900/45">
            {masterList}
          </div>
          <div className="flex-1">
            {detailView || (
              <div className="flex h-full items-center justify-center px-8 text-center">
                <div className="space-y-3">
                  <Icon name="package" size={48} className="mx-auto text-surface-400" />
                  <h3 className="text-[15px] font-bold text-surface-200">Select a store</h3>
                  <p className="text-[13px] text-surface-400">Choose a store from the sidebar to build products and listings.</p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="h-full lg:hidden">
          {showDetail ? <div className="h-full">{detailView}</div> : <div className="h-full">{masterList}</div>}
        </div>
      </>
    </PullToRefresh>
  )
}

function StoreWorkspaceView({
  store,
  workspace,
  activeTab,
  onTabChange,
  onBack,
  onSaveProduct,
  onUpdateProduct,
  onSaveListing,
  onUpdateListing,
  onSendProductToListings,
  designProviders,
}: {
  store: StoreItem
  workspace: StoreWorkspace
  activeTab: WorkspaceTab
  onTabChange: (tab: WorkspaceTab) => void
  onBack: () => void
  onSaveProduct: (product: StoreProductIdea) => void
  onUpdateProduct: (productId: string, patch: Partial<StoreProductIdea>) => void
  onSaveListing: (listing: StoreListingDraft) => void
  onUpdateListing: (listingId: string, patch: Partial<StoreListingDraft>) => void
  onSendProductToListings: (product: StoreProductIdea) => void
  designProviders: DesignProviderInfo[]
}) {
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 })
  }, [activeTab, store.slug])

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-surface-600/60 bg-surface-900/55 px-4 pb-3 pt-4">
        <button onClick={onBack} className="mb-3 flex items-center gap-1.5 text-[13px] font-medium text-surface-200 lg:hidden">
          <Icon name="chevron-left" size={16} /> Back
        </button>
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-extrabold tracking-tight text-surface-50">{store.name}</h2>
            <p className="mt-0.5 line-clamp-2 text-[12px] text-surface-200">{store.niche}</p>
          </div>
          <div className="hidden flex-shrink-0 text-right text-[11px] font-semibold text-surface-300 sm:block">
            {workspace.products.length} products / {workspace.listings.length} listings
          </div>
        </div>
        <div className="mt-4">
          <div className="grid grid-cols-3 gap-1 rounded-lg border border-surface-600/65 bg-surface-950/30 p-1">
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onTabChange(tab.id)}
                  className={`inline-flex min-h-9 min-w-0 items-center justify-center gap-1.5 rounded-md px-2 text-[11px] font-bold transition-all duration-150 sm:gap-2 sm:px-3 sm:text-[12px] ${
                    isActive
                      ? 'bg-primary-400/18 text-primary-100 ring-1 ring-primary-300/25'
                      : 'text-surface-300 hover:bg-surface-800/80 hover:text-surface-100'
                  }`}
                >
                  <Icon name={tab.icon} size={14} />
                  <span className="truncate sm:hidden">{tab.shortLabel}</span>
                  <span className="hidden truncate sm:inline">{tab.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div ref={contentRef} className="flex-1 overflow-y-auto px-4 py-4">
        {activeTab === 'dashboard' && <StoreDashboard store={store} workspace={workspace} onTabChange={onTabChange} />}
        {activeTab === 'products' && (
          <ProductCreator
            store={store}
            workspace={workspace}
            onSaveProduct={onSaveProduct}
            onUpdateProduct={onUpdateProduct}
            onSendProductToListings={onSendProductToListings}
            designProviders={designProviders}
          />
        )}
        {activeTab === 'listings' && (
          <ListingManager
            store={store}
            workspace={workspace}
            onSaveListing={onSaveListing}
            onUpdateListing={onUpdateListing}
          />
        )}
        <button onClick={onBack} className="mt-5 hidden items-center gap-1.5 text-[13px] font-medium text-surface-200 lg:flex">
          <Icon name="chevron-left" size={16} /> Back to stores
        </button>
      </div>
    </div>
  )
}

function StoreDashboard({ store, workspace, onTabChange }: { store: StoreItem; workspace: StoreWorkspace; onTabChange: (tab: WorkspaceTab) => void }) {
  const keywords = extractStoreKeywords(store)
  const clusters = extractKeywordClusters(store)
  const validation = validationItems(store, workspace)
  const completeCount = validation.filter((item) => item.complete).length
  const performance = workspacePerformance(workspace)

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricBlock icon="search" label="Keyword base" value={`${keywords.length}`} detail={keywords.length ? `${clusters.length} clusters` : 'No keyword snapshot'} />
        <MetricBlock icon="package" label="Products" value={`${workspace.products.length}`} detail="Saved product ideas" />
        <MetricBlock icon="file-text" label="Listings" value={`${workspace.listings.length}`} detail="Draft listings" />
        <MetricBlock icon="check-circle" label="Validation" value={`${completeCount}/${validation.length}`} detail="Workflow checks" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="panel p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="section-label">Product pipeline</div>
              <p className="mt-0.5 text-[12px] text-surface-300">Products created from this store's real keyword snapshot.</p>
            </div>
            <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => onTabChange('products')}>
              <Icon name="plus-circle" size={14} /> Add products
            </button>
          </div>
          {workspace.products.length ? (
            <div className="space-y-2">
              {workspace.products.slice(0, 6).map((product) => (
                <div key={product.id} className="grid min-w-0 gap-2 rounded-md border border-surface-600/45 bg-surface-900/30 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_7rem]">
                  <div className="min-w-0">
                    <div className="break-words text-[12px] font-extrabold text-surface-50">{product.title}</div>
                    <div className="mt-0.5 break-words text-[11px] text-surface-300">{product.keyword} / {formatProductType(product.productType)}</div>
                  </div>
                  <StatusPill status={product.status} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon="package" title="No product ideas yet" text="Use Product Creator to generate product ideas from the store's strongest keywords." />
          )}
        </div>

        <div className="space-y-4">
          {performance.hasData ? (
            <PerformanceSummaryPanel performance={performance} />
          ) : (
            <>
              <NoDataPanel icon="dollar-sign" title="Sales" text="No Etsy sales data connected for this store yet." />
              <NoDataPanel icon="activity" title="Traffic" text="No Etsy traffic data connected for this store yet." />
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="panel p-4">
          <div className="section-label mb-3">Validation checklist</div>
          <div className="space-y-2">
            {validation.map((item) => (
              <div key={item.label} className="flex min-w-0 gap-2 rounded-md border border-surface-600/35 bg-surface-900/20 p-3">
                <Icon name={item.complete ? 'check-circle' : 'clock'} size={15} className={item.complete ? 'mt-0.5 flex-shrink-0 text-accent-green' : 'mt-0.5 flex-shrink-0 text-accent-amber'} />
                <div className="min-w-0">
                  <div className="break-words text-[12px] font-bold text-surface-100">{item.label}</div>
                  <div className="mt-0.5 break-words text-[11px] text-surface-300">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel p-4">
          <div className="section-label mb-3">Top keywords</div>
          {keywords.length ? (
            <div className="space-y-2">
              {keywords.slice(0, 8).map((keyword, index) => (
                <KeywordRow key={keyword.keyword} keyword={keyword} rank={index + 1} />
              ))}
            </div>
          ) : (
            <EmptyState icon="search" title="No keyword evidence" text="This store does not have a keyword snapshot saved yet." />
          )}
        </div>
      </div>

      <div className="panel p-4">
        <div className="section-label mb-3">Store setup</div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <DetailRow label="Target audience" value={store.target_audience || 'Not specified'} />
          <DetailRow label="Brand voice" value={store.brand_voice || 'Not specified'} />
          <DetailRow label="Aesthetic" value={store.aesthetic || 'Not specified'} />
          <DetailRow label="Pricing strategy" value={titleCase(store.pricing_strategy || 'competitive')} />
          <DetailRow label="Listing target" value={`${store.listing_target || 0} listings`} />
          <DetailRow label="Created" value={store.created_at ? new Date(store.created_at).toLocaleDateString() : 'Unknown'} />
        </div>
      </div>
    </div>
  )
}

function ProductCreator({
  store,
  workspace,
  onSaveProduct,
  onUpdateProduct,
  onSendProductToListings,
  designProviders,
}: {
  store: StoreItem
  workspace: StoreWorkspace
  onSaveProduct: (product: StoreProductIdea) => void
  onUpdateProduct: (productId: string, patch: Partial<StoreProductIdea>) => void
  onSendProductToListings: (product: StoreProductIdea) => void
  designProviders: DesignProviderInfo[]
}) {
  const keywords = extractStoreKeywords(store)
  const [activeKeywordName, setActiveKeywordName] = useState('')
  const activeKeyword = keywords.find((keyword) => keyword.keyword === activeKeywordName) || null

  if (!keywords.length) {
    return (
      <div className="space-y-4">
        <EmptyState icon="search" title="No keywords saved" text="Add a store idea with keyword evidence before creating products." />
      </div>
    )
  }

  if (!activeKeyword) {
    return (
      <ProductKeywordPicker
        keywords={keywords}
        onSelectKeyword={(keyword) => setActiveKeywordName(keyword.keyword)}
      />
    )
  }

  return (
    <KeywordProductCreationPage
      store={store}
      keyword={activeKeyword}
      workspace={workspace}
      onBack={() => setActiveKeywordName('')}
      onSaveProduct={onSaveProduct}
      onUpdateProduct={onUpdateProduct}
      onSendProductToListings={onSendProductToListings}
      designProviders={designProviders}
    />
  )
}

function ProductKeywordPicker({
  keywords,
  onSelectKeyword,
}: {
  keywords: StoreKeywordCandidate[]
  onSelectKeyword: (keyword: StoreKeywordCandidate) => void
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(17rem,0.65fr)_minmax(0,1.35fr)]">
      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-surface-600/45 px-3 py-2.5">
          <div className="section-label">Keywords</div>
          <div className="text-[11px] font-bold text-surface-400">strength</div>
        </div>
        <div className="divide-y divide-surface-600/35">
          {keywords.map((keyword, index) => (
            <button
              key={keyword.keyword}
              type="button"
              onClick={() => onSelectKeyword(keyword)}
              className="grid min-h-12 w-full min-w-0 grid-cols-[2rem_minmax(0,1fr)_3rem] items-center gap-2 px-3 text-left transition-colors duration-150 hover:bg-primary-400/10"
            >
              <span className="text-[12px] font-extrabold tabular-nums text-surface-500">{index + 1}</span>
              <span className="min-w-0 truncate text-[13px] font-extrabold text-surface-50">{keyword.keyword}</span>
              <span className={`text-right text-[12px] font-extrabold tabular-nums ${scoreClass(keyword.strength)}`}>{formatMetric(keyword.strength)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="hidden min-h-80 place-items-center rounded-lg border border-dashed border-surface-600/55 bg-surface-900/20 text-[13px] font-extrabold text-surface-500 xl:grid">
        Select keyword
      </div>
    </div>
  )
}

function KeywordProductCreationPage({
  store,
  keyword,
  workspace,
  onBack,
  onSaveProduct,
  onUpdateProduct,
  onSendProductToListings,
  designProviders,
}: {
  store: StoreItem
  keyword: StoreKeywordCandidate
  workspace: StoreWorkspace
  onBack: () => void
  onSaveProduct: (product: StoreProductIdea) => void
  onUpdateProduct: (productId: string, patch: Partial<StoreProductIdea>) => void
  onSendProductToListings: (product: StoreProductIdea) => void
  designProviders: DesignProviderInfo[]
}) {
  const productTypes = productTypeOptionsFor(store, keyword)
  const [selectedType, setSelectedType] = useState(productTypes[0]?.value || '')
  const [selectedIdeaId, setSelectedIdeaId] = useState('')
  const [showDesign, setShowDesign] = useState(false)
  const [designVariant, setDesignVariant] = useState(0)
  const [selectedProvider, setSelectedProvider] = useState<DesignProviderId>('local_svg')
  const [manualSource, setManualSource] = useState<PromptLauncherId>('ideogram_web')
  const [manualDesign, setManualDesign] = useState<ManualDesignAsset | null>(null)
  const [generatedDesign, setGeneratedDesign] = useState<GeneratedDesignAsset | null>(null)
  const [qualityChecks, setQualityChecks] = useState<Record<string, boolean>>({})
  const designPanelRef = useRef<HTMLDivElement>(null)
  const generateMutation = useMutation({
    mutationFn: (payload: { provider: DesignProviderId; prompt: string; productType: string }) => generateDesignAsset({
      provider: payload.provider,
      prompt: payload.prompt,
      product_type: payload.productType,
      aspect_ratio: '1:1',
    }),
    onSuccess: (asset) => setGeneratedDesign(asset),
  })
  const activeType = productTypes.find((type) => type.value === selectedType) || productTypes[0]
  const ideas = activeType ? productIdeasForType(store, keyword, activeType.value) : []
  const selectedIdea = ideas.find((idea) => idea.id === selectedIdeaId) || null
  const savedProduct = selectedIdea
    ? workspace.products.find((product) => productKey(product) === productKey(selectedIdea))
    : null
  const activeProduct = savedProduct || selectedIdea
  const designSpec = activeProduct ? createDesignSpec(store, activeProduct, designVariant) : null
  const qualityReview = activeProduct ? evaluateDesignQuality(activeProduct, qualityChecks) : null
  const approvedDesign = savedProduct?.approvedDesign
  const mockupReady = savedProduct?.status === 'mockup_selected' || savedProduct?.status === 'sent_to_listing'
  const listingExists = savedProduct
    ? workspace.listings.some((listing) => listing.productId === savedProduct.id)
    : false

  const selectType = (value: string) => {
    setSelectedType(value)
    setSelectedIdeaId('')
    setShowDesign(false)
    setDesignVariant(0)
    setManualDesign(null)
    setGeneratedDesign(null)
    setQualityChecks({})
  }

  const startDesign = (idea: StoreProductIdea) => {
    const existingProduct = workspace.products.find((product) => productKey(product) === productKey(idea))
    setSelectedIdeaId(idea.id)
    setShowDesign(true)
    setDesignVariant(0)
    setManualDesign(null)
    setGeneratedDesign(null)
    setQualityChecks(existingProduct?.designQuality?.checks || {})
    if (!existingProduct) onSaveProduct(idea)
    window.requestAnimationFrame(() => designPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }))
  }

  useEffect(() => {
    if (!productTypes.some((type) => type.value === selectedType)) {
      setSelectedType(productTypes[0]?.value || '')
      setSelectedIdeaId('')
      setShowDesign(false)
    }
  }, [keyword.keyword, productTypes, selectedType])

  const generateDesign = () => {
    if (!activeProduct || !designSpec) return
    if (selectedProvider === 'local_svg') {
      setDesignVariant((value) => value + 1)
      setManualDesign(null)
      setGeneratedDesign(null)
      return
    }
    setManualDesign(null)
    generateMutation.mutate({
      provider: selectedProvider,
      prompt: createDesignPrompt(activeProduct, selectedProvider),
      productType: activeProduct.productType,
    })
  }

  const attachManualDesign = (file: File) => {
    if (!activeProduct) return
    const launcher = promptLauncherInfo(manualSource)
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result !== 'string') return
      setManualDesign({
        asset_url: reader.result,
        title: file.name.replace(/\.[^.]+$/, '') || activeProduct.title,
        prompt: createDesignPrompt(activeProduct, launcher.promptProvider),
        content_type: file.type || 'image/png',
        provider: launcher.label,
      })
      setGeneratedDesign(null)
    }
    reader.readAsDataURL(file)
  }

  const approveDesign = () => {
    if (!savedProduct || !designSpec || !qualityReview?.passed) return
    const asset = manualDesign
      ? createManualDesignAsset(savedProduct, manualDesign, manualSource)
      : generatedDesign
      ? createProviderDesignAsset(savedProduct, generatedDesign, selectedProvider)
      : createDesignAsset(savedProduct, designSpec, selectedProvider)
    onUpdateProduct(savedProduct.id, {
      approvedDesign: asset,
      designProvider: manualDesign ? `web:${manualSource}` : selectedProvider,
      designPrompt: asset.prompt,
      mockupPrompt: createMockupPrompt(savedProduct, asset),
      designQuality: qualityReview,
      status: 'design_approved',
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <button type="button" className="btn-secondary mb-3 min-h-9 px-3 py-2 text-[12px]" onClick={onBack}>
            <Icon name="arrow-left" size={14} /> Keywords
          </button>
          <div className="section-label">Product Creator</div>
          <h3 className="mt-1 break-words text-2xl font-extrabold tracking-tight text-surface-50">{keyword.keyword}</h3>
        </div>
        <div className="pt-12 text-[11px] font-extrabold text-surface-500">real</div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="panel overflow-hidden">
          <div className="border-b border-surface-600/45 p-3">
            <div className="section-label mb-3">Brainstorm</div>
            <div className="flex flex-wrap gap-2">
              {productTypes.map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => selectType(type.value)}
                  className={`min-h-9 rounded-md border px-3 text-[13px] font-extrabold transition-colors duration-150 ${
                    activeType?.value === type.value
                      ? 'border-primary-300/45 bg-primary-400/15 text-surface-50'
                      : 'border-surface-600/60 bg-surface-900/25 text-surface-100 hover:bg-surface-700/35'
                  }`}
                >
                  <span>{type.label}</span>
                  <span className={`ml-2 tabular-nums ${scoreClass(type.fit.score)}`}>{formatMetric(type.fit.score)}</span>
                </button>
              ))}
            </div>
            {activeType && (
              <div className="mt-2 line-clamp-2 break-words text-[11px] font-semibold text-surface-400">
                {activeType.fit.reasons.slice(0, 3).join(' / ')}
              </div>
            )}
          </div>

          <div className="p-3">
            <div className="section-label mb-3">Ideas</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {ideas.map((idea) => {
                const isSelected = selectedIdea?.id === idea.id
                const isSaved = workspace.products.some((product) => productKey(product) === productKey(idea))
                return (
                  <div
                    key={idea.id}
                    className={`grid min-h-14 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md border px-3 py-2 transition-colors duration-150 ${
                      isSelected
                        ? 'border-accent-green/45 bg-accent-green/10 text-surface-50'
                        : 'border-surface-600/55 bg-surface-900/20 text-surface-100 hover:bg-surface-700/35'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => startDesign(idea)}
                      className="min-w-0 text-left"
                    >
                      <span className="block break-words text-[13px] font-extrabold leading-snug">{idea.title}</span>
                      {idea.creativeBrief?.exactPhrase && (
                        <span className="mt-0.5 block truncate text-[11px] font-semibold text-surface-400">"{idea.creativeBrief.exactPhrase}"</span>
                      )}
                      <span className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] font-bold uppercase tracking-wider text-surface-500">
                        <span>Fit {formatMetric(idea.productTypeFit?.score)}</span>
                        <span>Gap {formatMetric(idea.gapEvidence?.score)}</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => startDesign(idea)}
                      className={`inline-flex min-h-8 flex-shrink-0 items-center justify-center gap-1.5 rounded-md border px-2.5 text-[11px] font-extrabold transition-colors duration-150 ${
                        isSaved
                          ? 'border-accent-green/30 bg-accent-green/10 text-accent-green'
                          : 'border-primary-300/35 bg-primary-400/15 text-primary-100 hover:bg-primary-400/25'
                      }`}
                    >
                      <Icon name={isSaved ? 'layers' : 'plus-circle'} size={13} />
                      {isSaved ? 'Design' : 'Start'}
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div ref={designPanelRef} className="space-y-3">
          <div className="panel p-3">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="section-label">Design</div>
                <div className="mt-1 min-h-6 truncate text-[14px] font-extrabold text-surface-50">{selectedIdea?.title || 'Add idea'}</div>
              </div>
              {savedProduct && (
                <button
                  type="button"
                  disabled={listingExists || !mockupReady}
                  onClick={() => onSendProductToListings(savedProduct)}
                  className="btn-secondary min-h-9 flex-shrink-0 px-3 py-2 text-[12px] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icon name={listingExists ? 'check-circle' : 'arrow-right'} size={14} />
                  {listingExists ? 'Listed' : 'Listing'}
                </button>
              )}
            </div>
            <button
              type="button"
              disabled={!selectedIdea}
              onClick={() => setShowDesign((value) => !value)}
              className="btn-secondary mt-3 min-h-10 w-full px-3 py-2 text-[13px]"
            >
              <Icon name="layers" size={14} /> {showDesign ? 'Hide' : 'Open'}
            </button>
            {showDesign && selectedIdea && (
              <div className="mt-3 space-y-3 border-t border-surface-600/45 pt-3">
                {activeProduct && designSpec && (
                  <GeneratedDesignPanel
                    spec={designSpec}
                    product={activeProduct}
                    provider={selectedProvider}
                    providerStatuses={designProviders}
                    manualSource={manualSource}
                    manualDesign={manualDesign}
                    generatedDesign={generatedDesign}
                    isGenerating={generateMutation.isPending}
                    generationError={generateMutation.error instanceof Error ? generateMutation.error.message : ''}
                    approvedDesign={approvedDesign}
                    qualityChecks={qualityChecks}
                    qualityReview={qualityReview}
                    onQualityCheckChange={(id, checked) => setQualityChecks((current) => ({ ...current, [id]: checked }))}
                    onProviderChange={(provider) => {
                      setSelectedProvider(provider)
                      setManualDesign(null)
                      setGeneratedDesign(null)
                      generateMutation.reset()
                    }}
                    onManualSourceChange={(source) => {
                      setManualSource(source)
                      setManualDesign(null)
                    }}
                    onAttachManualDesign={attachManualDesign}
                    onGenerate={generateDesign}
                    onApprove={approveDesign}
                  />
                )}
                {savedProduct && approvedDesign && (
                  <MockupGate
                    product={savedProduct}
                    design={approvedDesign}
                    isReady={mockupReady}
                    onUseMockup={() => onUpdateProduct(savedProduct.id, { status: 'mockup_selected' })}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

interface DesignSpec {
  title: string
  subtitle: string
  motif: 'pet' | 'camp' | 'botanical' | 'gift' | 'minimal'
  bg: string
  paper: string
  ink: string
  accent: string
  secondary: string
  variant: number
}

function GeneratedDesignPanel({
  spec,
  product,
  provider,
  providerStatuses,
  manualSource,
  manualDesign,
  generatedDesign,
  isGenerating,
  generationError,
  approvedDesign,
  qualityChecks,
  qualityReview,
  onQualityCheckChange,
  onProviderChange,
  onManualSourceChange,
  onAttachManualDesign,
  onGenerate,
  onApprove,
}: {
  spec: DesignSpec
  product: StoreProductIdea
  provider: DesignProviderId
  providerStatuses: DesignProviderInfo[]
  manualSource: PromptLauncherId
  manualDesign: ManualDesignAsset | null
  generatedDesign: GeneratedDesignAsset | null
  isGenerating: boolean
  generationError: string
  approvedDesign?: StoreProductDesignAsset
  qualityChecks: Record<string, boolean>
  qualityReview: ReturnType<typeof evaluateDesignQuality> | null
  onQualityCheckChange: (id: string, checked: boolean) => void
  onProviderChange: (provider: DesignProviderId) => void
  onManualSourceChange: (source: PromptLauncherId) => void
  onAttachManualDesign: (file: File) => void
  onGenerate: () => void
  onApprove: () => void
}) {
  const [copyState, setCopyState] = useState<'idle' | 'copied'>('idle')
  const svg = designSvgMarkup(spec)
  const providerInfo = designProviderInfo(provider, providerStatuses)
  const launcher = promptLauncherInfo(manualSource)
  const canGenerate = providerInfo.status === 'ready'
  const prompt = createDesignPrompt(product, provider)
  const launcherPrompt = createDesignPrompt(product, launcher.promptProvider)
  const activeAssetUrl = manualDesign?.asset_url || generatedDesign?.asset_url
  const hasApiAsset = !!generatedDesign?.asset_url
  const canApprove = provider === 'local_svg' || hasApiAsset || !!manualDesign
  const isApproved = approvedDesign?.prompt === prompt || approvedDesign?.prompt === launcherPrompt
  const qualityPassed = !!qualityReview?.passed
  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(launcherPrompt)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 1200)
    } catch {
      setCopyState('idle')
    }
  }
  return (
    <div className="overflow-hidden rounded-md border border-surface-600/45 bg-surface-950/25">
      <div className="border-b border-surface-600/35 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="section-label">Generator</div>
          <span className={`rounded-md border px-2 py-1 text-[10px] font-extrabold uppercase tracking-wider ${providerStatusClass(providerInfo.status)}`}>
            {providerStatusLabel(providerInfo.status)}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4 xl:grid-cols-2">
          {DESIGN_PROVIDERS.map((option) => {
            const selected = option.id === provider
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => onProviderChange(option.id)}
                className={`min-w-0 rounded-md border px-2.5 py-2 text-left transition-colors duration-150 ${
                  selected
                    ? 'border-primary-300/45 bg-primary-400/15 text-surface-50'
                    : 'border-surface-600/45 bg-surface-900/25 text-surface-200 hover:bg-surface-700/35'
                }`}
              >
                <span className="block truncate text-[11px] font-extrabold">{option.label}</span>
                <span className="mt-0.5 block truncate text-[9px] font-bold uppercase tracking-wider text-surface-400">{option.fit}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="space-y-3 bg-surface-950/30 p-3">
        {canGenerate || activeAssetUrl || provider === 'local_svg' ? (
          <div className="mx-auto aspect-square max-h-64 overflow-hidden rounded-md border border-surface-600/35 bg-surface-50">
            {activeAssetUrl ? (
              <img src={activeAssetUrl} alt={`${product.title} generated design`} className="h-full w-full object-cover" />
            ) : (
              <GeneratedDesignSvg spec={spec} />
            )}
          </div>
        ) : (
          <div className="rounded-md border border-surface-600/45 bg-surface-900/30 p-3">
            <div className="text-[12px] font-extrabold text-surface-100">{providerInfo.title}</div>
            <div className="mt-1 text-[11px] leading-relaxed text-surface-300">{providerInfo.detail}</div>
          </div>
        )}

        {generationError && (
          <div className="rounded-md border border-accent-amber/30 bg-accent-amber/10 p-2.5 text-[11px] font-semibold leading-relaxed text-accent-amber">
            {generationError}
          </div>
        )}

        <CreativeBriefPanel product={product} />

        <div className="rounded-md border border-surface-600/35 bg-surface-900/25 p-2.5">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-surface-400">Prompt</div>
          <div className="line-clamp-3 break-words text-[11px] leading-relaxed text-surface-200">{prompt}</div>
        </div>

        <div className="rounded-md border border-surface-600/35 bg-surface-900/25 p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-surface-400">Quality gate</div>
            <span className={`text-[10px] font-extrabold tabular-nums ${qualityPassed ? 'text-accent-green' : 'text-accent-amber'}`}>
              {qualityReview ? `${qualityReview.score}%` : 'n/a'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {designQualityChecklist(product).map((item) => (
              <label key={item.id} className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md border border-surface-600/35 bg-surface-950/25 px-2 py-1.5 text-[11px] font-bold text-surface-200">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 flex-shrink-0 accent-sky-400"
                  checked={!!qualityChecks[item.id]}
                  onChange={(event) => onQualityCheckChange(item.id, event.target.checked)}
                />
                <span className="min-w-0 truncate">{item.label}</span>
              </label>
            ))}
          </div>
          {qualityReview?.failureReason && (
            <div className="mt-2 break-words text-[11px] font-semibold text-accent-amber">{qualityReview.failureReason}</div>
          )}
        </div>

        <div className="rounded-md border border-surface-600/35 bg-surface-900/25 p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-surface-400">Free web</div>
            <span className="truncate text-[10px] font-extrabold text-surface-300">{manualDesign ? 'Attached' : launcher.label}</span>
          </div>
          <div className="line-clamp-3 break-words text-[11px] leading-relaxed text-surface-200">{launcherPrompt}</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3 xl:grid-cols-2">
            {PROMPT_LAUNCHERS.map((option) => {
              const selected = option.id === manualSource
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => onManualSourceChange(option.id)}
                  className={`min-w-0 rounded-md border px-2.5 py-2 text-left transition-colors duration-150 ${
                    selected
                      ? 'border-accent-green/40 bg-accent-green/10 text-surface-50'
                      : 'border-surface-600/45 bg-surface-950/30 text-surface-200 hover:bg-surface-700/35'
                  }`}
                >
                  <span className="block truncate text-[11px] font-extrabold">{option.label}</span>
                  <span className="mt-0.5 block truncate text-[9px] font-bold uppercase tracking-wider text-surface-400">{option.fit}</span>
                </button>
              )
            })}
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <button type="button" className="btn-secondary min-h-9 px-2.5 py-2 text-[11px]" onClick={copyPrompt}>
              <Icon name={copyState === 'copied' ? 'check-circle' : 'file-text'} size={13} /> {copyState === 'copied' ? 'Copied' : 'Copy'}
            </button>
            <a className="btn-secondary min-h-9 px-2.5 py-2 text-[11px]" href={launcher.url} target="_blank" rel="noreferrer">
              <Icon name="external-link" size={13} /> Open
            </a>
            <label className="btn-secondary min-h-9 cursor-pointer px-2.5 py-2 text-[11px]">
              <Icon name={manualDesign ? 'check-circle' : 'plus-circle'} size={13} /> {manualDesign ? 'Attached' : 'Attach'}
              <input
                type="file"
                accept="image/*"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) onAttachManualDesign(file)
                  event.currentTarget.value = ''
                }}
              />
            </label>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            className="btn-secondary min-h-9 px-2.5 py-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={onGenerate}
            disabled={!canGenerate || isGenerating}
          >
            <Icon name={isGenerating ? 'loader' : 'refresh-cw'} size={13} className={isGenerating ? 'animate-spin' : ''} /> {isGenerating ? 'Working' : 'Generate'}
          </button>
          {!activeAssetUrl ? (
            <a
              className="btn-secondary min-h-9 px-2.5 py-2 text-[11px]"
              href={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`}
              download={`${slugifyLocal(product.title)}-design.svg`}
            >
              <Icon name="download" size={13} /> SVG
            </a>
          ) : (
            <a
              className="btn-secondary min-h-9 px-2.5 py-2 text-[11px]"
              href={activeAssetUrl}
              download={`${slugifyLocal(product.title)}-${manualDesign ? manualSource : provider}-design.png`}
            >
              <Icon name="download" size={13} /> Image
            </a>
          )}
        </div>

        <button
          type="button"
          className={`min-h-10 w-full rounded-md border px-3 py-2 text-[12px] font-extrabold transition-colors duration-150 ${
            isApproved
              ? 'border-accent-green/35 bg-accent-green/10 text-accent-green'
              : 'border-primary-300/35 bg-primary-400/15 text-primary-100 hover:bg-primary-400/25 disabled:cursor-not-allowed disabled:opacity-50'
          }`}
          disabled={isGenerating || !canApprove || !qualityPassed}
          onClick={onApprove}
        >
          <Icon name={isApproved ? 'check-circle' : 'plus-circle'} size={14} />
          {isApproved ? 'Approved' : 'Approve'}
        </button>
      </div>
    </div>
  )
}

function CreativeBriefPanel({ product }: { product: StoreProductIdea }) {
  const brief = product.creativeBrief
  if (!brief) return null
  const rows = [
    ['Fit', `${formatMetric(product.productTypeFit?.score)} ${product.productTypeFit?.reasons.slice(0, 2).join(' / ') || ''}`.trim()],
    ['Gap', `${formatMetric(product.gapEvidence?.score)} ${product.gapEvidence?.reasons.slice(0, 2).join(' / ') || product.gapEvidence?.level || ''}`.trim()],
    ['Words', brief.exactPhrase || 'No text'],
    ['Artwork', brief.visualSubject],
    ['Style', `${brief.styleDirection}. ${brief.palette}.`],
    ['Avoid', brief.avoid.slice(0, 4).join(', ')],
    ['SEO', [brief.seoSource.primaryKeyword, ...brief.seoSource.supportingKeywords.slice(0, 3)].join(', ')],
  ]
  return (
    <details className="rounded-md border border-surface-600/35 bg-surface-900/25 p-2.5" open>
      <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-wider text-surface-400">Brief</summary>
      <div className="mt-2 space-y-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[3.75rem_minmax(0,1fr)] gap-2 text-[11px] leading-relaxed">
            <span className="font-bold text-surface-500">{label}</span>
            <span className="break-words font-semibold text-surface-200">{value}</span>
          </div>
        ))}
      </div>
    </details>
  )
}

function MockupGate({
  product,
  design,
  isReady,
  onUseMockup,
}: {
  product: StoreProductIdea
  design: StoreProductDesignAsset
  isReady: boolean
  onUseMockup: () => void
}) {
  return (
    <div className="overflow-hidden rounded-md border border-surface-600/45 bg-surface-950/25">
      <div className="flex items-center justify-between gap-2 border-b border-surface-600/35 px-3 py-2">
        <div className="section-label">Mockups</div>
        <span className="truncate text-[10px] font-bold uppercase tracking-wider text-surface-400">{design.provider}</span>
      </div>
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-[4.75rem_minmax(0,1fr)] gap-3">
          <div className="aspect-square overflow-hidden rounded-md border border-surface-600/35 bg-surface-50">
            {design.type === 'svg' && design.svgMarkup ? (
              <div className="h-full w-full" dangerouslySetInnerHTML={{ __html: design.svgMarkup }} />
            ) : (
              <img src={design.assetUrl} alt={`${product.title} approved design`} className="h-full w-full object-cover" />
            )}
          </div>
          <div className="min-w-0">
            <div className="truncate text-[12px] font-extrabold text-surface-50">{product.title}</div>
            <div className="mt-1 line-clamp-3 break-words text-[11px] leading-relaxed text-surface-300">{product.mockupPrompt}</div>
          </div>
        </div>
        <button
          type="button"
          className={`min-h-9 w-full rounded-md border px-3 py-2 text-[12px] font-extrabold transition-colors duration-150 ${
            isReady
              ? 'border-accent-green/35 bg-accent-green/10 text-accent-green'
              : 'border-primary-300/35 bg-primary-400/15 text-primary-100 hover:bg-primary-400/25'
          }`}
          onClick={onUseMockup}
        >
          <Icon name={isReady ? 'check-circle' : 'layers'} size={14} />
          {isReady ? 'Mockup ready' : 'Add to mockups'}
        </button>
      </div>
    </div>
  )
}

function GeneratedDesignSvg({ spec }: { spec: DesignSpec }) {
  return (
    <svg viewBox="0 0 600 600" role="img" aria-label={`${spec.title} generated design`} className="h-full w-full">
      <rect width="600" height="600" fill={spec.bg} />
      <rect x="54" y="54" width="492" height="492" rx={spec.variant % 2 ? 32 : 6} fill={spec.paper} />
      <path d={designWavePath(spec.variant)} fill={spec.accent} opacity="0.16" />
      <path d={designWavePath(spec.variant + 2)} fill={spec.secondary} opacity="0.13" transform="rotate(180 300 300)" />
      <DesignMotif spec={spec} />
      <text x="300" y="324" textAnchor="middle" fill={spec.ink} fontFamily="Georgia, serif" fontWeight="800" fontSize={fitDesignFont(spec.title)} letterSpacing="0">
        {spec.title}
      </text>
      <text x="300" y="362" textAnchor="middle" fill={spec.ink} fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="18" letterSpacing="0">
        {spec.subtitle}
      </text>
      <line x1="196" y1="394" x2="404" y2="394" stroke={spec.accent} strokeWidth="5" strokeLinecap="round" />
    </svg>
  )
}

function DesignMotif({ spec }: { spec: DesignSpec }) {
  if (spec.motif === 'pet') {
    return (
      <g transform="translate(300 202)">
        <circle cx="-38" cy="-28" r="22" fill={spec.accent} />
        <circle cx="38" cy="-28" r="22" fill={spec.accent} />
        <circle cx="-16" cy="-58" r="18" fill={spec.secondary} />
        <circle cx="16" cy="-58" r="18" fill={spec.secondary} />
        <ellipse cx="0" cy="6" rx="62" ry="50" fill={spec.ink} opacity="0.92" />
      </g>
    )
  }
  if (spec.motif === 'camp') {
    return (
      <g transform="translate(300 210)" fill="none" stroke={spec.ink} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round">
        <path d="M-84 40 L0 -76 L84 40 Z" fill={spec.accent} stroke="none" opacity="0.9" />
        <path d="M0 -76 L0 40" />
        <path d="M-118 58 H118" stroke={spec.secondary} />
      </g>
    )
  }
  if (spec.motif === 'botanical') {
    return (
      <g transform="translate(300 210)" fill="none" stroke={spec.ink} strokeWidth="7" strokeLinecap="round">
        <path d="M0 62 C-8 10 8 -36 0 -82" />
        <ellipse cx="-36" cy="-22" rx="26" ry="46" fill={spec.accent} stroke="none" transform="rotate(-35 -36 -22)" />
        <ellipse cx="38" cy="-2" rx="24" ry="42" fill={spec.secondary} stroke="none" transform="rotate(36 38 -2)" />
      </g>
    )
  }
  if (spec.motif === 'gift') {
    return (
      <g transform="translate(300 204)">
        <rect x="-78" y="-12" width="156" height="102" rx="10" fill={spec.accent} />
        <rect x="-12" y="-12" width="24" height="102" fill={spec.ink} opacity="0.86" />
        <rect x="-88" y="-42" width="176" height="34" rx="8" fill={spec.secondary} />
        <path d="M-10 -42 C-68 -84 -92 -22 -14 -16 M10 -42 C68 -84 92 -22 14 -16" fill="none" stroke={spec.ink} strokeWidth="8" strokeLinecap="round" />
      </g>
    )
  }
  return (
    <g transform="translate(300 204)" fill="none" stroke={spec.ink} strokeWidth="8">
      <circle r="68" stroke={spec.accent} />
      <path d="M-82 0 H82 M0 -82 V82" stroke={spec.secondary} />
      <circle r="18" fill={spec.ink} stroke="none" />
    </g>
  )
}

function designProviderInfo(provider: DesignProviderId, providerStatuses: DesignProviderInfo[]): { status: ProviderStatus; title: string; detail: string } {
  const option = DESIGN_PROVIDERS.find((item) => item.id === provider) || DESIGN_PROVIDERS[0]
  if (provider === 'local_svg') {
    return {
      status: 'ready',
      title: `${option.label} is ready`,
      detail: 'Built-in generation is available now for testing the approval workflow.',
    }
  }
  const backendStatus = providerStatuses.find((item) => item.id === provider)
  if (backendStatus?.status === 'ready') {
    return {
      status: 'ready',
      title: `${option.label} is connected`,
      detail: backendStatus.detail,
    }
  }
  if (backendStatus?.status === 'manual' || provider === 'midjourney') {
    return {
      status: 'manual',
      title: `${option.label} is manual`,
      detail: 'Use this as a benchmark provider. Save the prompt, generate manually, then connect a supported API path when available.',
    }
  }
  if (backendStatus?.status === 'unsupported') {
    return {
      status: 'unsupported',
      title: `${option.label} needs more setup`,
      detail: backendStatus.detail,
    }
  }
  if (backendStatus?.status === 'billing_locked') {
    return {
      status: 'billing_locked',
      title: `${option.label} is cost locked`,
      detail: backendStatus.detail,
    }
  }
  const envVars = backendStatus?.env_vars?.join(', ') || providerEnvVars(provider).join(', ')
  return {
    status: 'needs_key',
    title: `${option.label} needs an API key`,
    detail: `Set ${envVars} on the backend before this generator can create real design assets.`,
  }
}

function providerStatusClass(status: ProviderStatus): string {
  if (status === 'ready') return 'border-accent-green/25 bg-accent-green/10 text-accent-green'
  if (status === 'manual') return 'border-accent-amber/25 bg-accent-amber/10 text-accent-amber'
  if (status === 'unsupported') return 'border-accent-amber/25 bg-accent-amber/10 text-accent-amber'
  if (status === 'billing_locked') return 'border-accent-amber/25 bg-accent-amber/10 text-accent-amber'
  return 'border-surface-500/45 bg-surface-800/45 text-surface-300'
}

function providerStatusLabel(status: ProviderStatus): string {
  if (status === 'ready') return 'Ready'
  if (status === 'manual') return 'Manual'
  if (status === 'unsupported') return 'Setup'
  if (status === 'billing_locked') return 'Locked'
  return 'Needs key'
}

function createDesignAsset(product: StoreProductIdea, spec: DesignSpec, provider: DesignProviderId): StoreProductDesignAsset {
  const svgMarkup = designSvgMarkup(spec)
  return {
    id: `design-${product.id}-${provider}-${spec.variant}`,
    provider,
    type: 'svg',
    title: spec.title,
    prompt: createDesignPrompt(product, provider),
    assetUrl: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgMarkup)}`,
    svgMarkup,
    approvedAt: new Date().toISOString(),
  }
}

function createProviderDesignAsset(product: StoreProductIdea, generated: GeneratedDesignAsset, provider: DesignProviderId): StoreProductDesignAsset {
  return {
    id: `design-${product.id}-${provider}-${Date.now()}`,
    provider,
    type: 'image',
    title: generated.title,
    prompt: generated.prompt,
    assetUrl: generated.asset_url,
    approvedAt: new Date().toISOString(),
  }
}

function createManualDesignAsset(product: StoreProductIdea, manual: ManualDesignAsset, source: PromptLauncherId): StoreProductDesignAsset {
  const launcher = promptLauncherInfo(source)
  return {
    id: `design-${product.id}-${source}-${Date.now()}`,
    provider: `web:${launcher.label}`,
    type: 'external',
    title: manual.title || product.title,
    prompt: manual.prompt,
    assetUrl: manual.asset_url,
    approvedAt: new Date().toISOString(),
  }
}

function promptLauncherInfo(source: PromptLauncherId) {
  return PROMPT_LAUNCHERS.find((launcher) => launcher.id === source) || PROMPT_LAUNCHERS[0]
}

function providerEnvVars(provider: DesignProviderId): string[] {
  if (provider === 'ideogram') return ['IDEOGRAM_API_KEY']
  if (provider === 'recraft') return ['RECRAFT_API_TOKEN']
  if (provider === 'krea') return ['KREA_API_KEY']
  if (provider === 'openai') return ['OPENAI_API_KEY']
  if (provider === 'stability') return ['STABILITY_API_KEY']
  if (provider === 'firefly') return ['FIREFLY_SERVICES_CLIENT_ID', 'FIREFLY_SERVICES_CLIENT_SECRET']
  if (provider === 'fal') return ['FAL_KEY']
  if (provider === 'replicate') return ['REPLICATE_API_TOKEN']
  if (provider === 'bfl') return ['BFL_API_KEY']
  if (provider === 'gemini') return ['GEMINI_API_KEY']
  if (provider === 'luma') return ['LUMA_API_KEY']
  if (provider === 'magnific') return ['MAGNIFIC_API_KEY']
  if (provider === 'leonardo') return ['LEONARDO_API_KEY']
  return []
}

function createDesignPrompt(product: StoreProductIdea, provider: DesignProviderId): string {
  const providerHint = {
    ideogram: 'typography-first merch design with accurate readable text',
    recraft: 'clean print-ready vector-style design asset',
    krea: 'premium style exploration with polished visual taste',
    openai: 'balanced commercial product design concept',
    firefly: 'commercially safe graphic design asset',
    stability: 'illustrative high-impact product graphic',
    fal: 'fast model test for production-quality concepts',
    replicate: 'model marketplace benchmark with practical output',
    bfl: 'premium Flux prompt-following design asset',
    gemini: 'reasoned product graphic with strong composition',
    luma: 'polished campaign-ready visual direction',
    magnific: 'high-detail creative product artwork',
    leonardo: 'commercial design style with print-ready polish',
    midjourney: 'high-taste artistic benchmark concept',
    local_svg: 'simple deterministic approval-test design',
  } satisfies Record<DesignProviderId, string>
  const brief = product.creativeBrief
  if (brief) {
    return [
      `Create a flat printable design asset for ${formatProductType(product.productType)}.`,
      `Exact words to render: "${brief.exactPhrase || 'no text'}".`,
      `Artwork: ${brief.visualSubject}`,
      `Composition: ${brief.composition}`,
      `Palette: ${brief.palette}.`,
      `Typography: ${brief.typography}`,
      `Style: ${brief.styleDirection}.`,
      `Primary Etsy keyword: ${brief.seoSource.primaryKeyword}.`,
      `Supporting keywords: ${brief.seoSource.supportingKeywords.slice(0, 5).join(', ') || 'none'}.`,
      `Avoid: ${brief.avoid.join(', ')}.`,
      `Provider target: ${providerHint[provider]}.`,
      'Do not make a product mockup; output only the design artwork.',
    ].join(' ')
  }
  return [
    `${product.title} for ${formatProductType(product.productType)}.`,
    `Primary keyword: ${product.keyword}.`,
    `Create a flat printable design asset, not a product mockup.`,
    `Style target: ${providerHint[provider]}.`,
    `Use only intentional text that supports the keyword.`,
    `Transparent or clean background preferred.`,
  ].join(' ')
}

function createMockupPrompt(product: StoreProductIdea, design: StoreProductDesignAsset): string {
  if (product.creativeBrief) {
    return [
      product.creativeBrief.mockupDirection,
      `Product: ${product.title}.`,
      `Use the approved ${design.provider} design asset as the only artwork source.`,
      `Keep the first Etsy image realistic, clean, and focused on ${formatProductType(product.productType)}.`,
    ].join(' ')
  }
  return [
    `Mock up "${product.title}" as a ${formatProductType(product.productType)}.`,
    `Use the approved ${design.provider} design asset as the only artwork source.`,
    `Keep the Etsy thumbnail clean, realistic, and product-focused.`,
  ].join(' ')
}

function createDesignSpec(store: StoreItem, product: StoreProductIdea, variant: number): DesignSpec {
  const context = `${store.niche} ${store.aesthetic} ${product.keyword} ${product.title} ${product.productType}`.toLowerCase()
  const palettes = [
    { bg: '#dfe8e5', paper: '#f8f4eb', ink: '#263238', accent: '#7fa37a', secondary: '#d69a64' },
    { bg: '#e8e2d5', paper: '#fbf7ef', ink: '#2c2a25', accent: '#b07b57', secondary: '#6f96c8' },
    { bg: '#e6e8ef', paper: '#f7f4ef', ink: '#243043', accent: '#6f96c8', secondary: '#c86f7a' },
    { bg: '#eee3e0', paper: '#fff8f2', ink: '#342a2f', accent: '#c86f7a', secondary: '#a9c88f' },
  ]
  const palette = palettes[(hashString(product.keyword + product.title) + variant) % palettes.length]
  const displayTitle = product.creativeBrief?.exactPhrase || product.title
  return {
    ...palette,
    title: titleCase(displayTitle).slice(0, 28),
    subtitle: titleCase(product.keyword).slice(0, 32),
    motif: designMotifFor(context),
    variant,
  }
}

function designMotifFor(context: string): DesignSpec['motif'] {
  if (/\b(pet|dog|cat|puppy|kitten|rescue|breed)\b/.test(context)) return 'pet'
  if (/\b(camp|travel|summer|outdoor|hike|trail|vacation)\b/.test(context)) return 'camp'
  if (/\b(botanical|flower|garden|plant|floral|wildflower)\b/.test(context)) return 'botanical'
  if (/\b(gift|birthday|wedding|holiday|christmas|mom|dad)\b/.test(context)) return 'gift'
  return 'minimal'
}

function designSvgMarkup(spec: DesignSpec): string {
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img">',
    `<rect width="600" height="600" fill="${spec.bg}"/>`,
    `<rect x="54" y="54" width="492" height="492" rx="${spec.variant % 2 ? 32 : 6}" fill="${spec.paper}"/>`,
    `<path d="${designWavePath(spec.variant)}" fill="${spec.accent}" opacity="0.16"/>`,
    `<path d="${designWavePath(spec.variant + 2)}" fill="${spec.secondary}" opacity="0.13" transform="rotate(180 300 300)"/>`,
    designMotifMarkup(spec),
    `<text x="300" y="324" text-anchor="middle" fill="${spec.ink}" font-family="Georgia, serif" font-weight="800" font-size="${fitDesignFont(spec.title)}" letter-spacing="0">${escapeXml(spec.title)}</text>`,
    `<text x="300" y="362" text-anchor="middle" fill="${spec.ink}" font-family="system-ui, sans-serif" font-weight="800" font-size="18" letter-spacing="0">${escapeXml(spec.subtitle)}</text>`,
    `<line x1="196" y1="394" x2="404" y2="394" stroke="${spec.accent}" stroke-width="5" stroke-linecap="round"/>`,
    '</svg>',
  ].join('')
}

function designMotifMarkup(spec: DesignSpec): string {
  if (spec.motif === 'pet') {
    return `<g transform="translate(300 202)"><circle cx="-38" cy="-28" r="22" fill="${spec.accent}"/><circle cx="38" cy="-28" r="22" fill="${spec.accent}"/><circle cx="-16" cy="-58" r="18" fill="${spec.secondary}"/><circle cx="16" cy="-58" r="18" fill="${spec.secondary}"/><ellipse cx="0" cy="6" rx="62" ry="50" fill="${spec.ink}" opacity="0.92"/></g>`
  }
  if (spec.motif === 'camp') {
    return `<g transform="translate(300 210)" fill="none" stroke="${spec.ink}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"><path d="M-84 40 L0 -76 L84 40 Z" fill="${spec.accent}" stroke="none" opacity="0.9"/><path d="M0 -76 L0 40"/><path d="M-118 58 H118" stroke="${spec.secondary}"/></g>`
  }
  if (spec.motif === 'botanical') {
    return `<g transform="translate(300 210)" fill="none" stroke="${spec.ink}" stroke-width="7" stroke-linecap="round"><path d="M0 62 C-8 10 8 -36 0 -82"/><ellipse cx="-36" cy="-22" rx="26" ry="46" fill="${spec.accent}" stroke="none" transform="rotate(-35 -36 -22)"/><ellipse cx="38" cy="-2" rx="24" ry="42" fill="${spec.secondary}" stroke="none" transform="rotate(36 38 -2)"/></g>`
  }
  if (spec.motif === 'gift') {
    return `<g transform="translate(300 204)"><rect x="-78" y="-12" width="156" height="102" rx="10" fill="${spec.accent}"/><rect x="-12" y="-12" width="24" height="102" fill="${spec.ink}" opacity="0.86"/><rect x="-88" y="-42" width="176" height="34" rx="8" fill="${spec.secondary}"/><path d="M-10 -42 C-68 -84 -92 -22 -14 -16 M10 -42 C68 -84 92 -22 14 -16" fill="none" stroke="${spec.ink}" stroke-width="8" stroke-linecap="round"/></g>`
  }
  return `<g transform="translate(300 204)" fill="none" stroke="${spec.ink}" stroke-width="8"><circle r="68" stroke="${spec.accent}"/><path d="M-82 0 H82 M0 -82 V82" stroke="${spec.secondary}"/><circle r="18" fill="${spec.ink}" stroke="none"/></g>`
}

function designWavePath(variant: number): string {
  return variant % 2
    ? 'M54 154 C170 92 244 196 348 134 C446 76 510 122 546 94 L546 54 L54 54 Z'
    : 'M54 506 C146 428 240 510 342 452 C438 398 506 436 546 400 L546 546 L54 546 Z'
}

function fitDesignFont(value: string): number {
  if (value.length > 22) return 28
  if (value.length > 16) return 34
  return 42
}

function hashString(value: string): number {
  return value.split('').reduce((hash, char) => ((hash << 5) - hash + char.charCodeAt(0)) >>> 0, 0)
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

function ListingManager({
  store,
  workspace,
  onSaveListing,
  onUpdateListing,
}: {
  store: StoreItem
  workspace: StoreWorkspace
  onSaveListing: (listing: StoreListingDraft) => void
  onUpdateListing: (listingId: string, patch: Partial<StoreListingDraft>) => void
}) {
  const productsWithoutListings = workspace.products.filter((product) => !workspace.listings.some((listing) => listing.productId === product.id))
  return (
    <div className="space-y-4">
      <div className="panel p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="section-label">Listing drafts</div>
            <p className="mt-0.5 text-[12px] text-surface-300">Create and manage listing details before anything goes to Etsy.</p>
          </div>
          <div className="flex flex-shrink-0 gap-2">
            <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => downloadWorkspaceExport(store, workspace, 'json')}>
              <Icon name="download" size={14} /> JSON
            </button>
            <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => downloadWorkspaceExport(store, workspace, 'csv')}>
              <Icon name="download" size={14} /> CSV
            </button>
          </div>
        </div>

        {workspace.listings.length ? (
          <div className="space-y-4">
            {workspace.listings.map((listing) => {
              const product = workspace.products.find((item) => item.id === listing.productId)
              return (
                <ListingDraftEditor
                  key={listing.id}
                  store={store}
                  product={product}
                  listing={listing}
                  onUpdate={(patch) => onUpdateListing(listing.id, patch)}
                />
              )
            })}
          </div>
        ) : (
          <EmptyState icon="file-text" title="No listing drafts yet" text="Send a selected product idea here from Product Creator." />
        )}
      </div>

      {productsWithoutListings.length > 0 && (
        <div className="panel p-4">
          <div className="section-label mb-3">Products ready for listing drafts</div>
          <div className="grid gap-2 md:grid-cols-2">
            {productsWithoutListings.map((product) => (
              <div key={product.id} className="rounded-md border border-surface-600/45 bg-surface-900/20 p-3">
                <div className="break-words text-[12px] font-bold text-surface-100">{product.title}</div>
                <div className="mt-0.5 break-words text-[11px] text-surface-300">{product.keyword}</div>
                <button type="button" className="btn-secondary mt-3 min-h-9 px-3 py-2 text-[12px]" onClick={() => onSaveListing(createListingFromProduct(store, product))}>
                  <Icon name="plus-circle" size={14} /> Create draft
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <NoDataPanel icon="external-link" title="Etsy publishing" text="Publishing is not connected yet. Drafts stay inside this app until real Etsy credentials and publish flow exist." />
        <NoDataPanel icon="bar-chart" title="Listing performance" text="No live Etsy listing performance data connected yet." />
      </div>
    </div>
  )
}

function ListingDraftEditor({
  store,
  product,
  listing,
  onUpdate,
}: {
  store: StoreItem
  product?: StoreProductIdea
  listing: StoreListingDraft
  onUpdate: (patch: Partial<StoreListingDraft>) => void
}) {
  const quality = scoreListingDraft(store, listing, product)
  return (
    <div className="rounded-md border border-surface-600/50 bg-surface-900/25 p-3">
      <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-[13px] font-extrabold text-surface-50">{listing.title}</div>
          <div className="mt-0.5 break-words text-[11px] text-surface-300">{listing.primaryKeyword} / {formatProductType(listing.productType)}</div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <span className={`rounded-md border px-2 py-1 text-[10px] font-extrabold uppercase tracking-wider ${quality.score !== null && quality.score >= 80 ? 'border-accent-green/25 bg-accent-green/10 text-accent-green' : 'border-accent-amber/25 bg-accent-amber/10 text-accent-amber'}`}>
            {quality.grade} {quality.score !== null ? quality.score : 'n/a'}
          </span>
          <select
            className="input min-h-9 w-auto px-3 py-1.5 text-[12px]"
            value={listing.status}
            onChange={(event) => onUpdate({ status: event.target.value as ListingStatus, quality })}
            aria-label="Listing status"
          >
            <option value="draft">Draft</option>
            <option value="needs_review">Needs review</option>
            <option value="ready">Ready</option>
          </select>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_11rem]">
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Title</span>
          <input className="input text-[12px]" value={listing.title} onChange={(event) => onUpdate({ title: event.target.value })} />
        </label>
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Price</span>
          <input className="input text-[12px]" value={listing.price} onChange={(event) => onUpdate({ price: event.target.value })} />
        </label>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {quality.checks.map((check) => (
          <div key={check.label} className="rounded-md border border-surface-600/35 bg-surface-950/20 p-2">
            <div className={`text-[10px] font-extrabold uppercase tracking-wider ${check.complete ? 'text-accent-green' : 'text-accent-amber'}`}>{check.label}</div>
            <div className="mt-1 break-words text-[11px] text-surface-300">{check.detail}</div>
          </div>
        ))}
      </div>

      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Description</span>
        <textarea className="input min-h-36 resize-y text-[12px]" value={listing.description} onChange={(event) => onUpdate({ description: event.target.value })} />
      </label>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Tags</span>
          <textarea
            className="input min-h-24 resize-y text-[12px]"
            value={listing.tags.join(', ')}
            onChange={(event) => onUpdate({ tags: splitTags(event.target.value) })}
          />
        </label>
        <div className="rounded-md border border-surface-600/40 bg-surface-950/20 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-surface-300">Keyword plan</div>
          <div className="mt-2 text-[12px] text-surface-100">Primary: <span className="font-bold">{listing.primaryKeyword}</span></div>
          <div className="mt-2 break-words text-[11px] text-surface-300">
            Supporting: {listing.supportingKeywords.length ? listing.supportingKeywords.join(', ') : 'No supporting keywords saved'}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-surface-600/40 bg-surface-950/20 p-3">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-surface-300">Performance</div>
        <div className="grid gap-2 sm:grid-cols-4">
          <PerformanceInput label="Views" value={listing.performance?.views} onChange={(value) => onUpdate({ performance: updatePerformance(listing.performance, 'views', value) })} />
          <PerformanceInput label="Favorites" value={listing.performance?.favorites} onChange={(value) => onUpdate({ performance: updatePerformance(listing.performance, 'favorites', value) })} />
          <PerformanceInput label="Orders" value={listing.performance?.orders} onChange={(value) => onUpdate({ performance: updatePerformance(listing.performance, 'orders', value) })} />
          <PerformanceInput label="Revenue" value={listing.performance?.revenue} onChange={(value) => onUpdate({ performance: updatePerformance(listing.performance, 'revenue', value) })} />
        </div>
      </div>
    </div>
  )
}

function PerformanceInput({
  label,
  value,
  onChange,
}: {
  label: string
  value?: number | null
  onChange: (value: number | null) => void
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-400">{label}</span>
      <input
        className="input min-h-9 text-[12px]"
        type="number"
        min="0"
        inputMode="decimal"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
      />
    </label>
  )
}

function updatePerformance(
  current: StoreListingPerformance | undefined,
  field: keyof Omit<StoreListingPerformance, 'updatedAt'>,
  value: number | null,
): StoreListingPerformance {
  return {
    ...current,
    [field]: Number.isFinite(value) ? value : null,
    updatedAt: new Date().toISOString(),
  }
}

function downloadWorkspaceExport(store: StoreItem, workspace: StoreWorkspace, format: 'json' | 'csv'): void {
  const payload = workspaceExport(store, workspace)
  const content = format === 'json'
    ? JSON.stringify(payload, null, 2)
    : workspaceExportCsv(payload)
  const type = format === 'json' ? 'application/json' : 'text/csv'
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${slugifyLocal(store.name)}-workspace.${format}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function workspaceExportCsv(payload: Record<string, unknown>): string {
  const products = Array.isArray(payload.products) ? payload.products as Array<Record<string, unknown>> : []
  const listings = Array.isArray(payload.listings) ? payload.listings as Array<Record<string, unknown>> : []
  const rows = [
    ['type', 'title', 'keyword', 'product_type', 'status', 'fit_score', 'gap_score', 'quality_score', 'views', 'favorites', 'orders', 'revenue', 'supporting_keywords'],
    ...products.map((product) => [
      'product',
      stringCell(product.title),
      stringCell(product.keyword),
      stringCell(product.productType),
      stringCell(product.status),
      nestedMetric(product, ['productTypeFit', 'score']),
      nestedMetric(product, ['gapEvidence', 'score']),
      nestedMetric(product, ['designQuality', 'score']),
      '',
      '',
      '',
      '',
      arrayCell(product.supportingKeywords),
    ]),
    ...listings.map((listing) => [
      'listing',
      stringCell(listing.title),
      stringCell(listing.primaryKeyword),
      stringCell(listing.productType),
      stringCell(listing.status),
      '',
      '',
      nestedMetric(listing, ['quality', 'score']),
      nestedMetric(listing, ['performance', 'views']),
      nestedMetric(listing, ['performance', 'favorites']),
      nestedMetric(listing, ['performance', 'orders']),
      nestedMetric(listing, ['performance', 'revenue']),
      arrayCell(listing.supportingKeywords),
    ]),
  ]
  return rows.map((row) => row.map(csvCell).join(',')).join('\n')
}

function nestedMetric(value: Record<string, unknown>, path: string[]): string {
  let current: unknown = value
  for (const key of path) {
    if (!current || typeof current !== 'object') return ''
    current = (current as Record<string, unknown>)[key]
  }
  return Number.isFinite(current) ? String(current) : ''
}

function stringCell(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function arrayCell(value: unknown): string {
  return Array.isArray(value) ? value.map((item) => String(item || '').trim()).filter(Boolean).join('; ') : ''
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}

interface WorkspacePerformanceSummary {
  hasData: boolean
  views: number
  favorites: number
  orders: number
  revenue: number
  tracked: number
}

function workspacePerformance(workspace: StoreWorkspace): WorkspacePerformanceSummary {
  const initial: WorkspacePerformanceSummary = { hasData: false, views: 0, favorites: 0, orders: 0, revenue: 0, tracked: 0 }
  return workspace.listings.reduce<WorkspacePerformanceSummary>((summary, listing) => {
    const perf = listing.performance
    const hasData = !!perf && [perf.views, perf.favorites, perf.orders, perf.revenue].some((value) => Number.isFinite(value))
    if (!hasData) return summary
    return {
      hasData: true,
      tracked: summary.tracked + 1,
      views: summary.views + Number(perf?.views || 0),
      favorites: summary.favorites + Number(perf?.favorites || 0),
      orders: summary.orders + Number(perf?.orders || 0),
      revenue: summary.revenue + Number(perf?.revenue || 0),
    }
  }, initial)
}

function PerformanceSummaryPanel({ performance }: { performance: WorkspacePerformanceSummary }) {
  return (
    <div className="panel-soft p-4">
      <div className="section-label mb-3">Performance</div>
      <div className="grid grid-cols-2 gap-2">
        <MiniMetric label="Views" value={`${performance.views}`} />
        <MiniMetric label="Favorites" value={`${performance.favorites}`} />
        <MiniMetric label="Orders" value={`${performance.orders}`} />
        <MiniMetric label="Revenue" value={performance.revenue ? fmtPrice(performance.revenue) : '0'} />
      </div>
      <div className="mt-2 text-[11px] font-semibold text-surface-400">{performance.tracked} listings tracked</div>
    </div>
  )
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-surface-600/35 bg-surface-950/20 p-2">
      <div className="text-[13px] font-extrabold tabular-nums text-surface-50">{value}</div>
      <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-surface-400">{label}</div>
    </div>
  )
}

function MetricBlock({ icon, label, value, detail }: { icon: Parameters<typeof Icon>[0]['name']; label: string; value: string; detail: string }) {
  return (
    <div className="metric-panel">
      <div className="flex items-start justify-between gap-3">
        <Icon name={icon} size={17} className="text-primary-100" />
        <div className="text-right">
          <div className="text-2xl font-extrabold tabular-nums text-surface-50">{value}</div>
          <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-surface-400">{label}</div>
        </div>
      </div>
      <div className="mt-2 break-words text-[11px] text-surface-300">{detail}</div>
    </div>
  )
}

function KeywordRow({ keyword, rank }: { keyword: StoreKeywordCandidate; rank: number }) {
  return (
    <div className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)_3.25rem_3.25rem] items-center gap-2 rounded-md border border-surface-600/35 bg-surface-900/20 px-2.5 py-2">
      <div className="text-right text-[10px] font-extrabold tabular-nums text-surface-400">{rank}</div>
      <div className="min-w-0">
        <div className="break-words text-[12px] font-bold text-surface-100">{keyword.keyword}</div>
        <div className="mt-0.5 truncate text-[10px] text-surface-400">{keyword.product}</div>
      </div>
      <EvidenceNumber value={keyword.strength} label="strength" />
      <EvidenceNumber value={keyword.gap} label="gap" />
    </div>
  )
}

function EvidenceNumber({ value, label }: { value?: number | null; label: string }) {
  return (
    <div className="text-right">
      <div className={`text-[12px] font-extrabold tabular-nums ${scoreClass(value)}`}>{formatMetric(value)}</div>
      <div className="text-[9px] uppercase text-surface-500">{label}</div>
    </div>
  )
}

function StatusPill({ status }: { status: ProductStatus | ListingStatus }) {
  const ready = status === 'mockup_selected' || status === 'sent_to_listing' || status === 'ready'
  return (
    <span className={`inline-flex w-fit items-center justify-center rounded-md border px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${
      ready
        ? 'border-accent-green/25 bg-accent-green/10 text-accent-green'
        : 'border-surface-500/45 bg-surface-800/45 text-surface-200'
    }`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-surface-600/35 bg-surface-900/20 p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-surface-400">{label}</div>
      <div className="mt-1 break-words text-[12px] font-semibold text-surface-100">{value}</div>
    </div>
  )
}

function EmptyState({ icon, title, text }: { icon: Parameters<typeof Icon>[0]['name']; title: string; text: string }) {
  return (
    <div className="rounded-md border border-surface-600/35 bg-surface-900/20 px-4 py-8 text-center">
      <Icon name={icon} size={30} className="mx-auto mb-2 text-surface-400" />
      <div className="text-[13px] font-bold text-surface-200">{title}</div>
      <div className="mx-auto mt-1 max-w-sm text-[12px] text-surface-400">{text}</div>
    </div>
  )
}

function NoDataPanel({ icon, title, text }: { icon: Parameters<typeof Icon>[0]['name']; title: string; text: string }) {
  return (
    <div className="panel-soft p-4">
      <div className="flex items-start gap-3">
        <Icon name={icon} size={18} className="mt-0.5 flex-shrink-0 text-surface-300" />
        <div className="min-w-0">
          <div className="text-[12px] font-extrabold text-surface-100">{title}</div>
          <div className="mt-1 break-words text-[12px] leading-relaxed text-surface-300">{text}</div>
        </div>
      </div>
    </div>
  )
}

interface ProductTypeOption {
  value: string
  label: string
  fit: ProductTypeFit
}

function productTypeOptionsFor(store: StoreItem, keyword: StoreKeywordCandidate): ProductTypeOption[] {
  const values = uniqueStrings([
    ...(store.product_types || []),
    keyword.product,
  ].map(normalizeProductType).filter(Boolean))
  const productTypes = values.length ? values : ['digital_download']
  return productTypes
    .map((value) => ({ value, label: productTypeLabel(value), fit: scoreProductTypeFit(store, keyword, value) }))
    .sort((a, b) => (b.fit.score ?? -1) - (a.fit.score ?? -1))
}

function productIdeasForType(store: StoreItem, keyword: StoreKeywordCandidate, productType: string): StoreProductIdea[] {
  return createSpecificProductIdeas(store, keyword, productType, 6)
}

function normalizeProductType(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'digital_download'
}

function productTypeLabel(value: string): string {
  const label = formatProductType(value)
  return label === 'Digital Download' ? 'Digital' : label
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function slugifyLocal(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'item'
}

function productKey(product: Pick<StoreProductIdea, 'keyword' | 'title' | 'productType'>): string {
  return `${product.keyword.toLowerCase()}|${product.title.toLowerCase()}|${product.productType.toLowerCase()}`
}

function scoreClass(value?: number | null): string {
  return Number.isFinite(value) ? scoreColor(value as number) : 'text-surface-500'
}

function formatMetric(value?: number | null): string {
  return Number.isFinite(value) ? String(Math.round(value as number)) : 'n/a'
}

function formatProductType(value: string): string {
  return titleCase(value.replace(/_/g, ' '))
}

function titleCase(value: string): string {
  return value.replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
}

function splitTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean).slice(0, 13)
}

function storeMatchesMode(store: StoreItem, mode: AppMode): boolean {
  const storeMode = String(store.research_snapshot?.app_mode || 'developer')
  return mode === 'user' ? storeMode === 'user' : storeMode !== 'user'
}

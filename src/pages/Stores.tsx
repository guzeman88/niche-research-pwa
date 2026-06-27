import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getStores } from '../lib/api'
import type { StoreItem } from '../lib/api'
import Icon from '../components/Icon'
import PullToRefresh from '../components/PullToRefresh'
import { StoresSkeleton } from '../components/Skeleton'
import {
  createListingFromProduct,
  createProductIdeas,
  emptyWorkspace,
  extractKeywordClusters,
  extractStoreKeywords,
  readStoreWorkspace,
  saveListingDraft,
  saveProductIdea,
  updateListingDraft,
  updateProductIdea,
  validationItems,
  type ListingStatus,
  type ProductStatus,
  type StoreKeywordCandidate,
  type StoreListingDraft,
  type StoreProductIdea,
  type StoreWorkspace,
} from '../lib/storeWorkspace'
import { scoreColor } from '../lib/utils'

const COLORS = ['#6f96c8', '#a9c88f', '#f0cf89', '#c29ad4', '#c86f7a', '#7f9fc6']
const TABS = [
  { id: 'dashboard', label: 'Store Dashboard', shortLabel: 'Store', icon: 'dashboard' },
  { id: 'products', label: 'Product Creator', shortLabel: 'Products', icon: 'package' },
  { id: 'listings', label: 'Listing Manager', shortLabel: 'Listings', icon: 'file-text' },
] as const

type WorkspaceTab = typeof TABS[number]['id']

export default function Stores() {
  const qc = useQueryClient()
  const { data: rawStores, isLoading, isError } = useQuery<StoreItem[]>({ queryKey: ['stores'], queryFn: getStores })
  const stores = rawStores || []
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
    qc.invalidateQueries({ refetchType: 'active' })
    setWorkspaceVersion((value) => value + 1)
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
          <NoDataPanel icon="dollar-sign" title="Sales" text="No Etsy sales data connected for this store yet." />
          <NoDataPanel icon="activity" title="Traffic" text="No Etsy traffic data connected for this store yet." />
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
}: {
  store: StoreItem
  workspace: StoreWorkspace
  onSaveProduct: (product: StoreProductIdea) => void
  onUpdateProduct: (productId: string, patch: Partial<StoreProductIdea>) => void
  onSendProductToListings: (product: StoreProductIdea) => void
}) {
  const keywords = extractStoreKeywords(store)
  const [activeKeywordName, setActiveKeywordName] = useState('')
  const activeKeyword = keywords.find((keyword) => keyword.keyword === activeKeywordName) || null

  if (!keywords.length) {
    return (
      <div className="space-y-4">
        <ProductCreatorHeader title="Product Creator" detail="No keyword snapshot is saved for this store yet." />
        <EmptyState icon="search" title="No keywords saved" text="Add a store idea with keyword evidence before creating products." />
      </div>
    )
  }

  if (!activeKeyword) {
    return (
      <ProductKeywordPicker
        store={store}
        keywords={keywords}
        workspace={workspace}
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
    />
  )
}

function ProductCreatorHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="section-label">{title}</div>
        <p className="mt-0.5 max-w-3xl break-words text-[12px] leading-relaxed text-surface-300">{detail}</p>
      </div>
    </div>
  )
}

function ProductKeywordPicker({
  store,
  keywords,
  workspace,
  onSelectKeyword,
}: {
  store: StoreItem
  keywords: StoreKeywordCandidate[]
  workspace: StoreWorkspace
  onSelectKeyword: (keyword: StoreKeywordCandidate) => void
}) {
  const savedByKeyword = keywords.reduce<Record<string, number>>((counts, keyword) => {
    counts[keyword.keyword.toLowerCase()] = workspace.products.filter((product) => sameKeyword(product.keyword, keyword.keyword)).length
    return counts
  }, {})

  return (
    <div className="space-y-4">
      <ProductCreatorHeader
        title="Product Creator"
        detail="Start from the strongest keyword evidence saved with this store, then build products, briefs, mockup directions, and listing drafts from that keyword."
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <div className="panel p-4">
          <div className="mb-3 flex min-w-0 flex-wrap items-end justify-between gap-3">
            <div>
              <div className="section-label">Keyword workbench</div>
              <div className="mt-0.5 text-[12px] text-surface-300">{keywords.length} keywords ordered by strength</div>
            </div>
            <div className="rounded-md border border-surface-600/45 bg-surface-950/25 px-3 py-2 text-right">
              <div className="text-[15px] font-extrabold tabular-nums text-surface-50">{workspace.products.length}</div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-surface-500">saved products</div>
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
            {keywords.map((keyword, index) => {
              const savedCount = savedByKeyword[keyword.keyword.toLowerCase()] || 0
              return (
                <button
                  key={keyword.keyword}
                  type="button"
                  onClick={() => onSelectKeyword(keyword)}
                  className="group min-w-0 rounded-md border border-surface-600/45 bg-surface-900/20 p-3 text-left transition-all duration-150 hover:border-primary-300/35 hover:bg-primary-400/10"
                >
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[10px] font-extrabold uppercase tracking-wider text-surface-500">#{index + 1}</div>
                      <div className="mt-1 break-words text-[13px] font-extrabold leading-snug text-surface-50">{keyword.keyword}</div>
                      <div className="mt-1 truncate text-[11px] text-surface-300">{keyword.product}</div>
                    </div>
                    <EvidenceNumber value={keyword.strength} label="strength" />
                  </div>

                  <div className="mt-3 grid grid-cols-3 gap-2 rounded-md border border-surface-700/50 bg-surface-950/20 px-2 py-2">
                    <EvidenceNumber value={keyword.opportunity} label="opp" />
                    <EvidenceNumber value={keyword.gap} label="gap" />
                    <EvidenceNumber value={keyword.buyerIntent} label="intent" />
                  </div>

                  <div className="mt-3 flex min-w-0 items-center justify-between gap-3 text-[11px] font-bold">
                    <span className="min-w-0 truncate text-surface-300">{savedCount ? `${savedCount} saved` : 'No products yet'}</span>
                    <span className="inline-flex items-center gap-1 text-primary-100">
                      Open creator <Icon name="chevron-right" size={13} className="transition-transform duration-150 group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-4">
          <div className="panel p-4">
            <div className="section-label mb-3">Creation queue</div>
            {workspace.products.length ? (
              <div className="space-y-2">
                {workspace.products.slice(0, 6).map((product) => (
                  <button
                    key={product.id}
                    type="button"
                    onClick={() => {
                      const keyword = keywords.find((item) => sameKeyword(item.keyword, product.keyword))
                      if (keyword) onSelectKeyword(keyword)
                    }}
                    className="grid w-full min-w-0 gap-2 rounded-md border border-surface-600/40 bg-surface-900/20 px-3 py-2 text-left transition-all duration-150 hover:bg-surface-700/35 sm:grid-cols-[minmax(0,1fr)_6.5rem]"
                  >
                    <span className="min-w-0">
                      <span className="block break-words text-[12px] font-bold text-surface-100">{product.title}</span>
                      <span className="mt-0.5 block break-words text-[11px] text-surface-300">{product.keyword}</span>
                    </span>
                    <StatusPill status={product.status} />
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState icon="package" title="No product ideas yet" text="Open a keyword to create the first product idea for this store." />
            )}
          </div>

          <div className="panel-soft p-4">
            <div className="flex min-w-0 items-start gap-3">
              <Icon name="target" size={18} className="mt-0.5 flex-shrink-0 text-primary-100" />
              <div className="min-w-0">
                <div className="text-[12px] font-extrabold text-surface-100">{store.name}</div>
                <div className="mt-1 break-words text-[12px] leading-relaxed text-surface-300">
                  {store.target_audience || 'Target audience is not specified yet.'}
                </div>
              </div>
            </div>
          </div>
        </div>
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
}: {
  store: StoreItem
  keyword: StoreKeywordCandidate
  workspace: StoreWorkspace
  onBack: () => void
  onSaveProduct: (product: StoreProductIdea) => void
  onUpdateProduct: (productId: string, patch: Partial<StoreProductIdea>) => void
  onSendProductToListings: (product: StoreProductIdea) => void
}) {
  const ideas = createProductIdeas(store, keyword)
  const savedKeys = new Set(workspace.products.map((product) => productKey(product)))
  const savedProducts = workspace.products.filter((product) => sameKeyword(product.keyword, keyword.keyword))
  const supportingKeywords = Array.from(new Set(ideas.flatMap((idea) => idea.supportingKeywords))).slice(0, 12)

  return (
    <div className="space-y-4">
      <div className="panel p-4">
        <button type="button" className="btn-secondary mb-4 min-h-9 px-3 py-2 text-[12px]" onClick={onBack}>
          <Icon name="arrow-left" size={14} /> Keywords
        </button>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.42fr)]">
          <div className="min-w-0">
            <div className="section-label">Product creation page</div>
            <h3 className="mt-1 break-words text-2xl font-extrabold tracking-tight text-surface-50">{keyword.keyword}</h3>
            <p className="mt-1 max-w-3xl break-words text-[12px] leading-relaxed text-surface-300">
              Products, briefs, mockup directions, and listings created here stay attached to this keyword.
            </p>
            {supportingKeywords.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {supportingKeywords.map((term) => (
                  <span key={term} className="max-w-full break-words rounded-md border border-surface-600/45 bg-surface-950/25 px-2 py-1 text-[10px] font-bold text-surface-300">
                    {term}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-2">
            <EvidenceNumber value={keyword.strength} label="strength" />
            <EvidenceNumber value={keyword.opportunity} label="opportunity" />
            <EvidenceNumber value={keyword.gap} label="gap" />
            <EvidenceNumber value={keyword.buyerIntent} label="intent" />
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.72fr)]">
        <div className="panel p-4">
          <div className="mb-3 flex min-w-0 flex-wrap items-end justify-between gap-3">
            <div>
              <div className="section-label">Brainstorm board</div>
              <p className="mt-0.5 text-[12px] text-surface-300">Generated from this keyword and the store's saved product mix.</p>
            </div>
            <div className="rounded-md border border-surface-600/45 bg-surface-950/25 px-3 py-2 text-right">
              <div className="text-[15px] font-extrabold tabular-nums text-surface-50">{ideas.length}</div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-surface-500">concepts</div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {ideas.map((idea) => {
              const isSaved = savedKeys.has(productKey(idea))
              return (
                <div key={idea.id} className="min-w-0 rounded-md border border-surface-600/45 bg-surface-900/20 p-3">
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="break-words text-[13px] font-extrabold text-surface-50">{idea.title}</div>
                      <div className="mt-0.5 break-words text-[11px] text-surface-300">{formatProductType(idea.productType)} / {idea.targetBuyer}</div>
                    </div>
                    <EvidenceNumber value={idea.evidence.strength} label="strength" />
                  </div>

                  <div className="mt-3 line-clamp-4 break-words text-[12px] leading-relaxed text-surface-200">{idea.designBrief}</div>
                  {idea.supportingKeywords.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {idea.supportingKeywords.slice(0, 5).map((term) => (
                        <span key={term} className="max-w-full break-words rounded-md bg-surface-950/35 px-2 py-1 text-[10px] font-bold text-surface-400">{term}</span>
                      ))}
                    </div>
                  )}

                  <button
                    type="button"
                    disabled={isSaved}
                    onClick={() => onSaveProduct(idea)}
                    className={`mt-3 inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-[12px] font-bold transition-all duration-150 ${
                      isSaved
                        ? 'border-accent-green/25 bg-accent-green/10 text-accent-green'
                        : 'border-primary-300/30 bg-primary-400/15 text-primary-100 hover:bg-primary-400/25'
                    }`}
                  >
                    <Icon name={isSaved ? 'check-circle' : 'plus-circle'} size={14} />
                    {isSaved ? 'Saved' : 'Add product idea'}
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        <div className="space-y-4">
          <div className="panel p-4">
            <div className="mb-3 flex min-w-0 flex-wrap items-end justify-between gap-3">
              <div>
                <div className="section-label">Mockup lab</div>
                <p className="mt-0.5 text-[12px] text-surface-300">Saved products for this keyword.</p>
              </div>
              <div className="rounded-md border border-surface-600/45 bg-surface-950/25 px-3 py-2 text-right">
                <div className="text-[15px] font-extrabold tabular-nums text-surface-50">{savedProducts.length}</div>
                <div className="text-[9px] font-bold uppercase tracking-wider text-surface-500">saved</div>
              </div>
            </div>

            {savedProducts.length ? (
              <div className="space-y-3">
                {savedProducts.map((product) => {
                const listingExists = workspace.listings.some((listing) => listing.productId === product.id)
                return (
                  <ProductWorkbenchCard
                    key={product.id}
                    store={store}
                    product={product}
                    listingExists={listingExists}
                    onUpdate={(patch) => onUpdateProduct(product.id, patch)}
                    onSend={() => onSendProductToListings(product)}
                  />
                )
              })}
            </div>
          ) : (
              <EmptyState icon="package" title="No saved products for this keyword" text="Add a product idea from the brainstorm board to start mockup work." />
          )}
          </div>

          <NoDataPanel icon="layers" title="Image rendering" text="No real mockup image generator is connected yet. This lab creates editable mockup directions and keeps them with the product record." />
        </div>
      </div>
    </div>
  )
}

function ProductWorkbenchCard({
  store,
  product,
  listingExists,
  onUpdate,
  onSend,
}: {
  store: StoreItem
  product: StoreProductIdea
  listingExists: boolean
  onUpdate: (patch: Partial<StoreProductIdea>) => void
  onSend: () => void
}) {
  return (
    <div className="rounded-md border border-surface-600/45 bg-surface-900/25 p-3">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-[13px] font-extrabold text-surface-50">{product.title}</div>
          <div className="mt-0.5 break-words text-[11px] text-surface-300">{product.keyword} / {formatProductType(product.productType)}</div>
        </div>
        <StatusPill status={product.status} />
      </div>

      <div className="mt-3 space-y-3">
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Brainstorm brief</span>
          <textarea
            className="input min-h-28 resize-y text-[12px]"
            value={product.designBrief}
            onChange={(event) => onUpdate({ designBrief: event.target.value })}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Mockup directions</span>
          <textarea
            className="input min-h-32 resize-y text-[12px]"
            value={product.mockupPrompt}
            onChange={(event) => onUpdate({ mockupPrompt: event.target.value })}
          />
        </label>
      </div>

      <div className="mt-3 rounded-md border border-dashed border-surface-500/60 bg-surface-950/25 p-3">
        <div className="flex min-w-0 items-start gap-3">
          <Icon name="layers" size={18} className="mt-0.5 flex-shrink-0 text-primary-100" />
          <div className="min-w-0">
            <div className="text-[12px] font-bold text-surface-100">{mockupLabel(product.status)}</div>
            <div className="mt-0.5 break-words text-[11px] text-surface-300">
              {product.status === 'mockup_selected' || product.status === 'sent_to_listing'
                ? 'A mockup direction has been selected and can be sent to listings.'
                : 'Generate or edit the production direction before selecting a mockup.'}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary min-h-9 px-3 py-2 text-[12px]"
          onClick={() => onUpdate({ designBrief: buildBrainstormBrief(store, product), status: 'brief_ready' })}
        >
          <Icon name="file-text" size={14} /> Generate brief
        </button>
        <button
          type="button"
          className="btn-secondary min-h-9 px-3 py-2 text-[12px]"
          onClick={() => onUpdate({ mockupPrompt: buildMockupDirection(store, product), status: 'brief_ready' })}
        >
          <Icon name="layers" size={14} /> Generate mockup directions
        </button>
        <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => onUpdate({ status: 'mockup_selected' })}>
          <Icon name="check-circle" size={14} /> Mockup selected
        </button>
        <button type="button" disabled={listingExists} className="btn-primary min-h-9 px-3 py-2 text-[12px]" onClick={onSend}>
          <Icon name={listingExists ? 'check-circle' : 'arrow-right'} size={14} /> {listingExists ? 'In listing manager' : 'Send to listings'}
        </button>
      </div>
    </div>
  )
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
        </div>

        {workspace.listings.length ? (
          <div className="space-y-4">
            {workspace.listings.map((listing) => (
              <ListingDraftEditor key={listing.id} listing={listing} onUpdate={(patch) => onUpdateListing(listing.id, patch)} />
            ))}
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

function ListingDraftEditor({ listing, onUpdate }: { listing: StoreListingDraft; onUpdate: (patch: Partial<StoreListingDraft>) => void }) {
  return (
    <div className="rounded-md border border-surface-600/50 bg-surface-900/25 p-3">
      <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-[13px] font-extrabold text-surface-50">{listing.title}</div>
          <div className="mt-0.5 break-words text-[11px] text-surface-300">{listing.primaryKeyword} / {formatProductType(listing.productType)}</div>
        </div>
        <select
          className="input min-h-9 w-auto px-3 py-1.5 text-[12px]"
          value={listing.status}
          onChange={(event) => onUpdate({ status: event.target.value as ListingStatus })}
          aria-label="Listing status"
        >
          <option value="draft">Draft</option>
          <option value="needs_review">Needs review</option>
          <option value="ready">Ready</option>
        </select>
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

function sameKeyword(left: string, right: string): boolean {
  return left.trim().toLowerCase() === right.trim().toLowerCase()
}

function buildBrainstormBrief(store: StoreItem, product: StoreProductIdea): string {
  const productType = formatProductType(product.productType).toLowerCase()
  const buyer = product.targetBuyer || store.target_audience || `buyers searching for ${product.keyword}`
  const aesthetic = store.aesthetic || store.niche || 'the store aesthetic'
  const supporting = product.supportingKeywords.slice(0, 5).join(', ')

  return [
    `Build a ${productType} concept for "${product.keyword}" aimed at ${buyer}.`,
    `Use ${aesthetic} as the visual direction and make the buyer outcome obvious in the first thumbnail.`,
    supporting ? `Work in supporting keyword angles: ${supporting}.` : '',
    'Avoid generic filler. The product should have one clear use case, one clear buyer, and one clear reason it belongs in this store.',
  ].filter(Boolean).join(' ')
}

function buildMockupDirection(store: StoreItem, product: StoreProductIdea): string {
  const productType = formatProductType(product.productType).toLowerCase()
  const aesthetic = store.aesthetic || store.niche || 'cohesive Etsy-ready style'
  const supporting = product.supportingKeywords.slice(0, 5).join(', ')

  return [
    `Create Etsy listing mockup directions for "${product.title}" as a ${productType}.`,
    `Primary keyword: ${product.keyword}.`,
    supporting ? `Secondary keyword cues: ${supporting}.` : '',
    `Style: ${aesthetic}. Keep the hero image clean, readable, and specific to the keyword.`,
    'Include a primary thumbnail, one detail close-up, and one in-use context image. Do not add fake reviews, sales badges, bestseller badges, or unsupported claims.',
  ].filter(Boolean).join(' ')
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

function mockupLabel(status: ProductStatus): string {
  if (status === 'mockup_selected' || status === 'sent_to_listing') return 'Mockup direction selected'
  if (status === 'brief_ready') return 'Mockup brief ready'
  return 'Mockup not generated yet'
}

function splitTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean).slice(0, 13)
}

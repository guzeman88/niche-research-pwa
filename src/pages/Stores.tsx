import { useMemo, useState } from 'react'
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
  { id: 'dashboard', label: 'Store Dashboard', icon: 'dashboard' },
  { id: 'products', label: 'Product Creator', icon: 'package' },
  { id: 'listings', label: 'Listing Manager', icon: 'file-text' },
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
        <div className="mt-4 overflow-x-auto">
          <div className="flex min-w-max gap-1 rounded-lg border border-surface-600/65 bg-surface-950/30 p-1">
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onTabChange(tab.id)}
                  className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-md px-3 text-[12px] font-bold transition-all duration-150 ${
                    isActive
                      ? 'bg-primary-400/18 text-primary-100 ring-1 ring-primary-300/25'
                      : 'text-surface-300 hover:bg-surface-800/80 hover:text-surface-100'
                  }`}
                >
                  <Icon name={tab.icon} size={14} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
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
  const [selectedKeyword, setSelectedKeyword] = useState('')
  const activeKeyword = keywords.find((keyword) => keyword.keyword === selectedKeyword) || keywords[0]
  const ideas = activeKeyword ? createProductIdeas(store, activeKeyword) : []
  const savedKeys = new Set(workspace.products.map((product) => productKey(product)))

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(16rem,0.7fr)_minmax(0,1.3fr)]">
      <div className="space-y-4">
        <div className="panel p-4">
          <div className="section-label mb-3">Store keywords</div>
          {keywords.length ? (
            <div className="max-h-[32rem] space-y-1.5 overflow-y-auto pr-1">
              {keywords.map((keyword, index) => {
                const isActive = activeKeyword?.keyword === keyword.keyword
                return (
                  <button
                    key={keyword.keyword}
                    type="button"
                    onClick={() => setSelectedKeyword(keyword.keyword)}
                    className={`grid w-full min-w-0 grid-cols-[2rem_minmax(0,1fr)_3rem] items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-all duration-150 ${
                      isActive
                        ? 'border-primary-300/35 bg-primary-400/12'
                        : 'border-surface-600/40 bg-surface-900/20 hover:bg-surface-700/35'
                    }`}
                  >
                    <span className="text-right text-[10px] font-extrabold tabular-nums text-surface-400">{index + 1}</span>
                    <span className="min-w-0">
                      <span className="block break-words text-[12px] font-bold text-surface-100">{keyword.keyword}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-surface-400">{keyword.product}</span>
                    </span>
                    <span className={`text-right text-[12px] font-extrabold tabular-nums ${scoreClass(keyword.strength)}`}>{formatMetric(keyword.strength)}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <EmptyState icon="search" title="No keywords saved" text="Add a store idea with keyword evidence before creating products." />
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div className="panel p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <div className="section-label">Generated product ideas</div>
              <p className="mt-0.5 text-[12px] text-surface-300">
                {activeKeyword ? `Based on "${activeKeyword.keyword}" and this store's saved product mix.` : 'Select a keyword to generate product ideas.'}
              </p>
            </div>
          </div>
          {activeKeyword ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {ideas.map((idea) => {
                const isSaved = savedKeys.has(productKey(idea))
                return (
                  <div key={idea.id} className="min-w-0 rounded-md border border-surface-600/45 bg-surface-900/20 p-3">
                    <div className="flex min-w-0 items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="break-words text-[13px] font-extrabold text-surface-50">{idea.title}</div>
                        <div className="mt-0.5 break-words text-[11px] text-surface-300">{formatProductType(idea.productType)} / {idea.keyword}</div>
                      </div>
                      <EvidenceNumber value={idea.evidence.strength} label="strength" />
                    </div>
                    <div className="mt-3 break-words text-[12px] leading-relaxed text-surface-200">{idea.designBrief}</div>
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
          ) : null}
        </div>

        <div className="panel p-4">
          <div className="section-label mb-3">Saved product ideas and mockups</div>
          {workspace.products.length ? (
            <div className="space-y-3">
              {workspace.products.map((product) => {
                const listingExists = workspace.listings.some((listing) => listing.productId === product.id)
                return (
                  <div key={product.id} className="rounded-md border border-surface-600/45 bg-surface-900/25 p-3">
                    <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="break-words text-[13px] font-extrabold text-surface-50">{product.title}</div>
                        <div className="mt-0.5 break-words text-[11px] text-surface-300">{product.keyword} / {formatProductType(product.productType)}</div>
                      </div>
                      <StatusPill status={product.status} />
                    </div>

                    <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
                      <label className="block">
                        <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Design brief</span>
                        <textarea
                          className="input min-h-28 resize-y text-[12px]"
                          value={product.designBrief}
                          onChange={(event) => onUpdateProduct(product.id, { designBrief: event.target.value })}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-surface-300">Mockup prompt</span>
                        <textarea
                          className="input min-h-28 resize-y text-[12px]"
                          value={product.mockupPrompt}
                          onChange={(event) => onUpdateProduct(product.id, { mockupPrompt: event.target.value })}
                        />
                      </label>
                    </div>

                    <div className="mt-3 rounded-md border border-dashed border-surface-500/60 bg-surface-950/25 p-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <Icon name="layers" size={18} className="mt-0.5 flex-shrink-0 text-primary-100" />
                        <div className="min-w-0">
                          <div className="text-[12px] font-bold text-surface-100">{mockupLabel(product.status)}</div>
                          <div className="mt-0.5 break-words text-[11px] text-surface-300">
                            {product.status === 'mockup_selected'
                              ? 'A mockup direction has been selected and can be sent to listings.'
                              : 'Mockup image generation is not connected yet. Use the brief and prompt here as the production direction.'}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => onUpdateProduct(product.id, { status: 'brief_ready' })}>
                        <Icon name="file-text" size={14} /> Brief ready
                      </button>
                      <button type="button" className="btn-secondary min-h-9 px-3 py-2 text-[12px]" onClick={() => onUpdateProduct(product.id, { status: 'mockup_selected' })}>
                        <Icon name="check-circle" size={14} /> Mockup selected
                      </button>
                      <button type="button" disabled={listingExists} className="btn-primary min-h-9 px-3 py-2 text-[12px]" onClick={() => onSendProductToListings(product)}>
                        <Icon name={listingExists ? 'check-circle' : 'arrow-right'} size={14} /> {listingExists ? 'In listing manager' : 'Send to listings'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState icon="package" title="No saved product ideas" text="Choose a keyword and save generated ideas before building mockups or listings." />
          )}
        </div>
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

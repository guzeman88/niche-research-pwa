import type { OpportunityDecision, StoreItem } from './api'
import { accountStorage } from './accountWorkspace'
import { readStoreWorkspace, scoreListingDraft, workspaceExport } from './storeWorkspace'

export type LaunchStageId = 'keyword' | 'evidence' | 'economics' | 'decision' | 'product' | 'package'

export interface LaunchApproval {
  acceptedAt: string
  operatorNote: string
  decisionFingerprint: string
}

export interface LaunchWorkflow {
  id: string
  keyword: string
  productType: string
  decision: OpportunityDecision | null
  approval: LaunchApproval | null
  storeSlug: string | null
  productId: string | null
  createdAt: string
  updatedAt: string
}

export interface LaunchStageStatus {
  id: LaunchStageId
  label: string
  state: 'complete' | 'current' | 'blocked' | 'upcoming'
  detail: string
}

const STORAGE_KEY = 'niche-research-pwa:launch-workflows:v1'

export function listLaunchWorkflows(): LaunchWorkflow[] {
  try {
    const raw = accountStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isLaunchWorkflow) : []
  } catch {
    return []
  }
}

export function createLaunchWorkflow(keyword: string, productType: string): LaunchWorkflow {
  const now = new Date().toISOString()
  const workflow: LaunchWorkflow = {
    id: `launch-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    keyword: keyword.trim().toLowerCase(),
    productType: normalizeProductType(productType),
    decision: null,
    approval: null,
    storeSlug: null,
    productId: null,
    createdAt: now,
    updatedAt: now,
  }
  return saveLaunchWorkflow(workflow)
}

export function saveLaunchWorkflow(workflow: LaunchWorkflow): LaunchWorkflow {
  const next = { ...workflow, updatedAt: new Date().toISOString() }
  const rows = listLaunchWorkflows().filter((item) => item.id !== workflow.id)
  accountStorage.setItem(STORAGE_KEY, JSON.stringify([next, ...rows].slice(0, 24)))
  return next
}

export function stageStatuses(workflow: LaunchWorkflow, store?: StoreItem): LaunchStageStatus[] {
  const decision = workflow.decision
  const marketReady = Boolean(decision?.evidence.market_pair)
    && decision!.evidence.listing_sample_count >= 10
  const economicsReady = Boolean(decision?.evidence.unit_economics)
    && Number(decision?.economics.contribution_profit_usd) > 0
  const approved = Boolean(workflow.approval)
    && workflow.approval?.decisionFingerprint === decision?.input_fingerprint
  const productReady = Boolean(workflow.storeSlug && workflow.productId)
  const workspace = workflow.storeSlug ? readStoreWorkspace(workflow.storeSlug) : null
  const product = workspace?.products.find((item) => item.id === workflow.productId)
  const listing = workspace?.listings.find((item) => item.productId === workflow.productId)
  const listingScore = store && listing ? scoreListingDraft(store, listing, product).score : null
  const packageReady = Boolean(product?.designQuality?.passed && listing && Number(listingScore) >= 80)

  const completed = new Set<LaunchStageId>()
  if (workflow.keyword && workflow.productType) completed.add('keyword')
  if (marketReady) completed.add('evidence')
  if (economicsReady) completed.add('economics')
  if (approved) completed.add('decision')
  if (productReady) completed.add('product')
  if (packageReady) completed.add('package')
  const order: LaunchStageId[] = ['keyword', 'evidence', 'economics', 'decision', 'product', 'package']
  const firstIncomplete = order.find((stage) => !completed.has(stage)) || 'package'

  const details: Record<LaunchStageId, string> = {
    keyword: workflow.keyword || 'Choose an exact phrase',
    evidence: marketReady ? 'Matched market evidence' : 'Demand, supply, and sample required',
    economics: economicsReady ? 'Positive contribution recorded' : 'Exact costs and fees required',
    decision: approved ? `Approved · ${decision?.model_version}` : 'Review and approve the evidence snapshot',
    product: productReady ? 'Product brief saved' : 'Choose one focused product concept',
    package: packageReady ? 'Design and listing gates passed' : 'Design, listing, and export remain',
  }
  const labels: Record<LaunchStageId, string> = {
    keyword: 'Keyword', evidence: 'Evidence', economics: 'Economics',
    decision: 'Decision', product: 'Product', package: 'Package',
  }

  return order.map((id, index) => {
    const priorIncomplete = order.slice(0, index).some((stage) => !completed.has(stage))
    return {
      id,
      label: labels[id],
      state: completed.has(id) ? 'complete' : id === firstIncomplete ? 'current' : priorIncomplete ? 'blocked' : 'upcoming',
      detail: details[id],
    }
  })
}

export function downloadLaunchPackage(workflow: LaunchWorkflow, store: StoreItem): void {
  const workspace = readStoreWorkspace(store.slug)
  const payload = {
    schemaVersion: 1,
    exportedAt: new Date().toISOString(),
    workflow: {
      ...workflow,
      decision: workflow.decision ? {
        ...workflow.decision,
        audit: {
          modelVersion: workflow.decision.model_version,
          inputFingerprint: workflow.decision.input_fingerprint,
          approvedAt: workflow.approval?.acceptedAt || null,
          operatorNote: workflow.approval?.operatorNote || '',
        },
      } : null,
    },
    workspace: workspaceExport(store, workspace),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${store.slug}-launch-package.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

function normalizeProductType(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'unspecified'
}

function isLaunchWorkflow(value: unknown): value is LaunchWorkflow {
  if (!value || typeof value !== 'object') return false
  const row = value as Partial<LaunchWorkflow>
  return typeof row.id === 'string' && typeof row.keyword === 'string' && typeof row.productType === 'string'
}

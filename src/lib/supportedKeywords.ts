import { validationRequest } from './productValidation'

export interface SupportedKeyword {
  keyword: string; status: string; demand_group: string; niche_key: string; supporting_keywords: string[]
  google_monthly_searches: number | null; google_geography: string | null; etsy_listing_count: number
  sample_count: number; automated_relevance: number; human_relevance_review_required: boolean
}
export interface ResearchDraft {
  id: string; project_id: string; title: string; description: string; tags: string[]; sync_status: string
  status: string; audit: {blockers: string[]; can_publish: boolean}; support: SupportedKeyword
}
export interface SupportedGoal {
  status: string; month?: string; timezone?: string; target: number; qualified_this_month: number
  baseline_groups?: number; available_supported_groups?: number; available_niches?: number
  etsy_demand_backed_groups?: number; observed_daily_pace?: number; required_daily_pace?: number
  projected_month_total?: number; candidates: SupportedKeyword[]; drafts: ResearchDraft[]
  blockers?: Array<{reason: string; keywords: number}>
}
export const readSupportedGoal = () => validationRequest<SupportedGoal>('/supported-keywords')

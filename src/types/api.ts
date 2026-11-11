export interface StatsResponse {
  attempted?: number;
  successful?: number;
  evidence_backed?: number;
  failed?: number;
  no_data?: number;
  stale?: number;
  total_seeds: number;
  scanned: number;
  unscanned: number;
  total_scans: number;
  coverage_pct: number | null;
  avg_opportunity: number | null;
  avg_gap_score: number | null;
  breakout_count: number | null;
  expansion_edges: number;
  top_gap_keyword: { keyword: string; gap_score: number } | null;
  domains: { domain: string; cnt: number }[];
}

export interface DashboardSummary {
  schema_version: number;
  snapshot_version: number | string;
  generated_at: string;
  data_status: 'healthy' | 'degraded';
  input_fingerprint: string;
  source_watermarks: Record<string, string | null>;
  duration_ms: number;
  scope?: string;
  connection?: {private_actions_available: boolean; status: string};
  sources?: Array<{source: string; rows: number; keywords: number; latest: string | null}>;
  score_distribution?: Array<{label: string; count: number}>;
  research_leads?: Array<{keyword: string; score: number}>;
  breakouts?: {status: string; reason: string; items: unknown[]};
  feed?: {status?: string; last_attempt?: string; last_completed?: string; errors?: string[]};
  coverage?: {as_of?: string; active_keywords?: number; active_current_competition?: number; active_google_monthly_direct?: number; active_paired_keywords?: number; providers?: Array<{provider: string; attempts: number; useful_attempts: number; failed_attempts: number; entries: number}>};
  intelligence?: {status: string; listings?: number; observations?: number; outcomes?: number; models?: number; reference_listings?: number; automatic_estimator?: {at?: string; tracked?: number; estimated?: number; statuses?: Record<string,number>}};
  production?: {status: string; jobs: number | null; review_queue: number | null; starting_recipes: number};
  validation?: {records: number; projects: number};
  supported?: {status: string; qualified_this_month?: number; target?: number; available_supported_groups?: number; etsy_demand_backed_groups?: number};
  stats: StatsResponse;
  evidence: {
    versioned_scores: number;
    versioned_gaps: number;
    marketplace_insights_rows: number;
    marketplace_insights_keywords: number;
    shop_stats_rows: number;
  };
  providers: Array<{
    provider: string;
    configured: boolean;
    status: string;
    last_attempt_at: string | null;
    last_success_at: string | null;
    row_count: number | null;
    updated_at: string;
  }>;
  delivery: {
    mode: 'live' | 'fallback';
    refresh_interval_seconds: number;
    fallback_generated_at?: string;
    reason?: string;
    stale?: boolean;
    scope?: string;
  };
}

export interface HealthResponse {
  db_path: string;
  size_mb: number;
  oldest_scan: string | null;
  newest_scan: string | null;
  orphan_seeds: number;
  integrity: string;
  schema_version: number;
}

export interface KeywordItem {
  keyword: string;
  domain: string;
  source: string;
  added_at: string;
  scanned: boolean;
  last_scanned_at: string | null;
  primary_score?: number | null;
  primary_score_source?: string | null;
  opportunity_score: number | null;
  gap_score: number | null;
  trajectory: string | null;
  breakout: boolean;
  scan_status?: string | null;
  scan_error?: string | null;
  evidence_status?: 'verified' | 'partial' | 'unverified' | 'failed' | 'imported' | string;
  score_version?: string | null;
  evidence_details_json?: string | null;
  observed_search_volume?: number | null;
  observed_search_volume_source?: 'google_ads_keyword_planner' | 'scan_evidence' | null;
  listing_count?: number | null;
  sampled_listing_count?: number | null;
  avg_price_usd?: number | null;
}

export interface AdapterStatus {
  [key: string]: {
    available: boolean;
    healthy?: boolean;
    error?: string;
  };
}

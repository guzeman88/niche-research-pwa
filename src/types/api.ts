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
  breakout_count: number;
  expansion_edges: number;
  top_gap_keyword: { keyword: string; gap_score: number } | null;
  domains: { domain: string; cnt: number }[];
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
  priority: number;
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

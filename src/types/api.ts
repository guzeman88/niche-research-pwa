export interface StatsResponse {
  total_seeds: number;
  scanned: number;
  unscanned: number;
  total_scans: number;
  coverage_pct: number;
  avg_opportunity: number;
  avg_gap_score: number;
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
  opportunity_score: number | null;
  gap_score: number | null;
  trajectory: string | null;
  breakout: boolean;
}

export interface AdapterStatus {
  [key: string]: {
    available: boolean;
    healthy?: boolean;
    error?: string;
  };
}

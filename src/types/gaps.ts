export interface GapReport {
  keyword: string;
  analyzed_at: string;
  volume_gap_score: number | null;
  quality_gap_score: number | null;
  tag_gap_score: number | null;
  style_gap_score: number | null;
  price_gap_score: number | null;
  recency_gap_score: number | null;
  buyer_intent_score?: number | null;
  profit_gap_score?: number | null;
  composite_gap_score: number | null;
  entry_angle: string;
  recommended_price_min: number | null;
  recommended_price_max: number | null;
  listings_analyzed: number;
  avg_listing_age_months: number | null;
  evidence_status?: string;
  score_version?: string | null;
  untagged_searches_json?: string[];
  dominant_competitor_tags_json?: string[];
  recommended_tags_json?: string[];
}

export interface GapReportListItem {
  keyword: string;
  composite_gap_score: number;
  volume_gap_score: number;
  quality_gap_score: number;
  tag_gap_score: number;
  style_gap_score: number;
  price_gap_score: number;
  recency_gap_score: number;
  buyer_intent_score?: number;
  profit_gap_score?: number;
  entry_angle: string;
}

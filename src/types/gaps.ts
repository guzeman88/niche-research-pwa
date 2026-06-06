export interface GapReport {
  keyword: string;
  analyzed_at: string;
  volume_gap_score: number;
  quality_gap_score: number;
  tag_gap_score: number;
  style_gap_score: number;
  price_gap_score: number;
  recency_gap_score: number;
  composite_gap_score: number;
  entry_angle: string;
  recommended_price_min: number;
  recommended_price_max: number;
  listings_analyzed: number;
  avg_listing_age_months: number;
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
  entry_angle: string;
}

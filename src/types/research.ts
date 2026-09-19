// Type definitions matching the Python NicheReport dataclass

export interface NicheSignal {
  keyword: string;
  monthly_searches: number | null;
  competition_score: number | null;
  avg_price_usd: number | null;
  trend_direction: 'rising' | 'stable' | 'declining' | null;
  source: string;
  relative_interest?: number | null;
  relative_interest_period?: string | null;
}

export interface KeywordSearchData {
  keyword: string;
  total_listing_count: number | null;
  avg_price_usd: number | null;
  price_min: number | null;
  price_p25: number | null;
  price_median: number | null;
  price_p75: number | null;
  price_max: number | null;
  price_sweet_spot: string | null;
  avg_review_count: number | null;
  pct_star_sellers: number | null;
  pct_bestsellers: number | null;
  competition_quality_score: number | null;
  estimated_market_monthly_revenue_usd: number | null;
  top_listing_titles: string[];
  avg_favorites: number | null;
  max_favorites: number | null;
  pct_high_favorites: number | null;
}

export interface SeasonalityPoint {
  month: number;
  relative_interest: number;
}

export interface KeywordCluster {
  cluster_name: string;
  keywords: string[];
  opportunity_score?: number | null;
  avg_competition_quality?: number | null;
  estimated_monthly_revenue_potential_usd?: number | null;
  rationale: string;
}

export interface NicheReport {
  store_slug: string;
  generated_at: string;
  seed_keywords: string[];
  keyword_signals: NicheSignal[];
  keyword_search_data: KeywordSearchData[];
  demand_score: number | null;
  competition_score: number | null;
  margin_score: number | null;
  trend_velocity_score: number | null;
  opportunity_score: number | null;
  avg_price_usd: number | null;
  price_sweet_spot: string;
  estimated_market_monthly_revenue_usd: number | null;
  avg_competition_quality: number | null;
  seasonality: SeasonalityPoint[];
  peak_months: number[];
  keyword_clusters: KeywordCluster[];
  underserved_angles: string[];
  winning_styles: string[];
  recommended_product_types: string[];
  competitor_gaps: string[];
  pricing_insights: string;
  entry_strategy: string;
  sources_used: string[];
  report_id: string;
}

export interface ReportListItem {
  report_id: string;
  store_slug: string;
  seed_keywords: string[];
  opportunity_score: number | null;
  demand_score: number | null;
  competition_score: number | null;
  margin_score: number | null;
  trend_velocity_score: number | null;
  generated_at: string;
  sources_used: string[];
}

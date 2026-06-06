// Type definitions matching the Python NicheReport dataclass

export interface NicheSignal {
  keyword: string;
  monthly_searches: number;
  competition_score: number;
  avg_price_usd: number;
  trend_direction: 'rising' | 'stable' | 'declining';
  source: string;
}

export interface KeywordSearchData {
  keyword: string;
  total_listing_count: number;
  avg_price_usd: number;
  price_min: number;
  price_p25: number;
  price_median: number;
  price_p75: number;
  price_max: number;
  price_sweet_spot: string;
  avg_review_count: number;
  pct_star_sellers: number;
  pct_bestsellers: number;
  competition_quality_score: number;
  estimated_market_monthly_revenue_usd: number;
  top_listing_titles: string[];
  avg_favorites: number;
  max_favorites: number;
  pct_high_favorites: number;
}

export interface SeasonalityPoint {
  month: number;
  relative_interest: number;
}

export interface KeywordCluster {
  cluster_name: string;
  keywords: string[];
  opportunity_score: number;
  avg_competition_quality: number;
  estimated_monthly_revenue_potential_usd: number;
  rationale: string;
}

export interface NicheReport {
  store_slug: string;
  generated_at: string;
  seed_keywords: string[];
  keyword_signals: NicheSignal[];
  keyword_search_data: KeywordSearchData[];
  demand_score: number;
  competition_score: number;
  margin_score: number;
  trend_velocity_score: number;
  opportunity_score: number;
  avg_price_usd: number;
  price_sweet_spot: string;
  estimated_market_monthly_revenue_usd: number;
  avg_competition_quality: number;
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
  opportunity_score: number;
  demand_score: number;
  competition_score: number;
  margin_score: number;
  trend_velocity_score: number;
  generated_at: string;
  sources_used: string[];
}

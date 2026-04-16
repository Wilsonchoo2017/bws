export interface BricklinkItem {
  item_id: string;
  item_type: string;
  title: string;
  year_released: number | null;
  image_url: string | null;
  watch_status: 'active' | 'paused' | 'stopped' | 'archived';
  last_scraped_at: string | null;
  created_at: string;
}

export interface ItemWithAnalysis extends BricklinkItem {
  overall_score: number | null;
  confidence: number | null;
  action: 'strong_buy' | 'buy' | 'hold' | 'skip' | null;
  urgency: 'urgent' | 'moderate' | 'low' | 'no_rush' | null;
}

export interface UnifiedItem {
  set_number: string;
  title: string | null;
  theme: string | null;
  year_released: number | null;
  year_retired: number | null;
  retiring_soon: boolean | null;
  retired_date: string | null;
  availability: string | null;
  watchlist: boolean;
  image_url: string | null;
  rrp_cents: number | null;
  rrp_currency: string | null;
  updated_at: string | null;
  minifig_count: number | null;
  dimensions: string | null;
  shopee_price_cents: number | null;
  shopee_currency: string | null;
  shopee_url: string | null;
  shopee_shop_name: string | null;
  shopee_last_seen: string | null;
  shopee_shop_count: number;
  toysrus_price_cents: number | null;
  toysrus_currency: string | null;
  toysrus_url: string | null;
  toysrus_last_seen: string | null;
  mightyutan_price_cents: number | null;
  mightyutan_currency: string | null;
  mightyutan_url: string | null;
  mightyutan_last_seen: string | null;
  bricklink_new_cents: number | null;
  bricklink_new_currency: string | null;
  bricklink_new_last_seen: string | null;
  bricklink_used_cents: number | null;
  bricklink_used_currency: string | null;
  bricklink_used_last_seen: string | null;
  ml_growth_pct: number | null;
  ml_confidence: string | null;
  ml_tier: number | null;
  ml_avoid_probability: number | null;
  ml_great_buy_probability: number | null;
  ml_buy_category: 'GREAT' | 'GOOD' | 'SKIP' | 'WORST' | 'NONE' | null;
  ml_raw_growth_pct: number | null;
  ml_kelly_fraction: number | null;
  ml_win_probability: number | null;
  cohort_half_year: number | null;
  cohort_theme: number | null;
  cohort_price_tier: number | null;
  liquidity_score: number | null;
  liq_cohort_half_year: number | null;
  liq_cohort_theme: number | null;
  liq_cohort_price_tier: number | null;
}

export interface PriceRecord {
  source: string;
  price_cents: number;
  currency: string;
  title: string | null;
  url: string | null;
  shop_name: string | null;
  condition: string | null;
  recorded_at: string;
}

export type BuyRating = 1 | 2 | 3 | 4;

export interface ItemDetail {
  set_number: string;
  title: string | null;
  theme: string | null;
  year_released: number | null;
  year_retired: number | null;
  parts_count: number | null;
  minifig_count: number | null;
  dimensions: string | null;
  weight: string | null;
  image_url: string | null;
  buy_rating: BuyRating | null;
  watchlist: boolean;
  in_portfolio: boolean;
  listing_price_cents: number | null;
  listing_currency: string | null;
  prices: PriceRecord[];
  ml_prediction?: {
    growth_pct: number;
    confidence: string;
    tier: number;
    avoid_probability?: number;
    raw_growth_pct?: number;
    kelly_fraction?: number;
    win_probability?: number;
    interval_lower?: number;
    interval_upper?: number;
    drivers?: { feature: string; impact: number }[];
    shap_base?: number;
  } | null;
}

export interface MinifigurePrice {
  minifig_id: string;
  name: string | null;
  image_url: string | null;
  quantity: number;
  year_released: number | null;
  current_new_avg_cents: number | null;
  current_used_avg_cents: number | null;
  currency: string;
  last_scraped_at: string | null;
}

export interface SetMinifigureData {
  set_item_id: string;
  minifig_count: number;
  total_value_cents: number | null;
  total_value_currency: string;
  minifigures: MinifigurePrice[];
}

export interface MinifigValueSnapshot {
  scraped_at: string;
  total_new_cents: number;
  total_used_cents: number;
}

export interface PricingBoxData {
  times_sold: number | null;
  total_lots: number | null;
  total_qty: number | null;
  min_price_cents: number | null;
  avg_price_cents: number | null;
  qty_avg_price_cents: number | null;
  max_price_cents: number | null;
  currency: string;
}

export interface PriceHistorySnapshot {
  scraped_at: string;
  six_month_new: PricingBoxData | null;
  six_month_used: PricingBoxData | null;
  current_new: PricingBoxData | null;
  current_used: PricingBoxData | null;
}

export interface MonthlySaleRecord {
  year: number;
  month: number;
  condition: 'new' | 'used';
  times_sold: number;
  total_quantity: number;
  min_price_cents: number | null;
  max_price_cents: number | null;
  avg_price_cents: number | null;
  currency: string;
}

export interface BricklinkPriceData {
  item_id: string;
  price_history: PriceHistorySnapshot[];
  monthly_sales: MonthlySaleRecord[];
}

export interface CohortRank {
  key: string;
  size: number;
  rank: number | null;
  // Dynamic percentile fields: {signal_name}_pct
  [key: string]: string | number | null;
}

export interface ItemSignals {
  item_id: string;
  set_number: string;
  title: string | null;
  theme: string | null;
  year_released: number | null;
  year_retired: number | null;
  rrp_cents: number | null;
  rrp_currency: string | null;
  entry_price_cents: number;
  eval_year: number;
  eval_month: number;
  ml_growth_pct: number | null;
  demand_pressure: number | null;
  supply_velocity: number | null;
  price_trend: number | null;
  price_vs_rrp: number | null;
  lifecycle_position: number | null;
  stock_level: number | null;
  collector_premium: number | null;
  theme_growth: number | null;
  value_opportunity: number | null;
  price_wall: number | null;
  listing_ratio: number | null;
  new_used_spread: number | null;
  mod_shelf_life: number;
  mod_subtheme: number;
  mod_niche: number;
  release_date: string | null;
  parts_count: number | null;
  rrp_usd_cents: number | null;
  composite_score: number | null;
  cohorts: Record<string, CohortRank> | null;
}

export interface KellyHorizon {
  horizon: string;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  mean_return: number;
  return_variance: number;
  kelly_fraction: number;
  half_kelly: number;
  sample_count: number;
}

export interface KellySizing {
  set_number: string;
  ml_growth_pct: number | null;
  score_bin: string;
  entry_price_cents: number;
  flip: KellyHorizon | null;
  hold: KellyHorizon | null;
  recommended_pct: number;
  recommended_amount_cents: number | null;
  confidence: 'high' | 'moderate' | 'low' | 'insufficient';
  warnings: string[];
}

export interface DiscountRow {
  discount_pct: number;
  entry_price_cents: number;
  effective_annual_roi: number;
  effective_3yr_return: number;
  meets_target: boolean;
  recommended_amount_cents: number | null;
  target_position_cents: number | null;
  remaining_amount_cents: number | null;
}

export interface CapitalAllocationData {
  set_number: string;
  ml_buy_category: 'GREAT' | 'GOOD' | 'SKIP' | 'WORST' | 'NONE' | null;
  rrp_cents: number | null;
  rrp_currency: string;
  annual_roi: number;
  total_return_3yr: number;
  win_probability: number;
  kelly_fraction: number;
  half_kelly: number;
  recommended_pct: number;
  recommended_amount_cents: number | null;
  total_capital_cents: number | null;
  deployed_cents: number;
  available_cents: number;
  existing_quantity: number;
  existing_cost_cents: number;
  target_position_cents: number | null;
  remaining_amount_cents: number | null;
  target_value_cents: number | null;
  expected_value_cents: number | null;
  meets_target: boolean;
  theme?: string | null;
  year_retired?: number | null;
  theme_exposure_cents?: number;
  year_exposure_cents?: number;
  theme_cap_cents?: number | null;
  year_cap_cents?: number | null;
  set_cap_cents?: number | null;
  concentration_limited_by?: 'set' | 'theme' | 'year' | null;
  discount_table: DiscountRow[];
}

export interface BrickeconomyData {
  set_number: string;
  scraped_at: string;
  title: string | null;
  theme: string | null;
  subtheme: string | null;
  year_released: number | null;
  year_retired: number | null;
  pieces: number | null;
  minifigs: number | null;
  availability: string | null;
  brickeconomy_url: string | null;
  rrp_usd_cents: number | null;
  rrp_gbp_cents: number | null;
  rrp_eur_cents: number | null;
  value_new_cents: number | null;
  value_used_cents: number | null;
  annual_growth_pct: number | null;
  rating_value: string | null;
  review_count: number | null;
  future_estimate_cents: number | null;
  future_estimate_date: string | null;
  distribution_mean_cents: number | null;
  distribution_stddev_cents: number | null;
  value_chart_json: [string, number][] | null;
  sales_trend_json: [string, number][] | null;
  candlestick_json: [string, number, number, number, number][] | null;
}

export interface KeepaData {
  set_number: string;
  asin: string | null;
  title: string | null;
  keepa_url: string | null;
  scraped_at: string;
  current_buy_box_cents: number | null;
  current_amazon_cents: number | null;
  current_new_cents: number | null;
  lowest_ever_cents: number | null;
  highest_ever_cents: number | null;
  amazon_price_json: string | [string, number][] | null;
  new_price_json: string | [string, number][] | null;
  new_3p_fba_json: string | [string, number][] | null;
  new_3p_fbm_json: string | [string, number][] | null;
  used_price_json: string | [string, number][] | null;
  used_like_new_json: string | [string, number][] | null;
  buy_box_json: string | [string, number][] | null;
  list_price_json: string | [string, number][] | null;
  warehouse_deals_json: string | [string, number][] | null;
  collectible_json: string | [string, number][] | null;
  sales_rank_json: string | [string, number][] | null;
  rating: number | null;
  review_count: number | null;
  tracking_users: number | null;
  chart_screenshot_path: string | null;
}

export function getLatestPriceBySource(
  prices: PriceRecord[]
): Map<string, PriceRecord> {
  const latest = new Map<string, PriceRecord>();
  for (const p of prices) {
    const existing = latest.get(p.source);
    if (!existing || p.recorded_at > existing.recorded_at) {
      latest.set(p.source, p);
    }
  }
  return latest;
}

export { formatPrice } from '@/lib/formatting';

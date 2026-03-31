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
  composite_score: number | null;
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

export interface ItemDetail {
  set_number: string;
  title: string | null;
  theme: string | null;
  year_released: number | null;
  year_retired: number | null;
  parts_count: number | null;
  minifig_count: number | null;
  dimensions: string | null;
  image_url: string | null;
  prices: PriceRecord[];
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
  composite_score: number | null;
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
  composite_score: number | null;
  score_bin: string;
  entry_price_cents: number;
  flip: KellyHorizon | null;
  hold: KellyHorizon | null;
  recommended_pct: number;
  recommended_amount_cents: number | null;
  confidence: 'high' | 'moderate' | 'low' | 'insufficient';
  warnings: string[];
}

export function formatPrice(
  cents: number | null,
  currency?: string | null
): string {
  if (cents === null) return '-';
  const amount = (cents / 100).toFixed(2);
  if (currency === 'USD') return `$${amount}`;
  return `RM${amount}`;
}

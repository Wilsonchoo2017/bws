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
  image_url: string | null;
  updated_at: string | null;
  shopee_price_cents: number | null;
  shopee_currency: string | null;
  shopee_url: string | null;
  shopee_last_seen: string | null;
  toysrus_price_cents: number | null;
  toysrus_currency: string | null;
  toysrus_url: string | null;
  toysrus_last_seen: string | null;
  bricklink_new_cents: number | null;
  bricklink_new_currency: string | null;
  bricklink_new_last_seen: string | null;
  bricklink_used_cents: number | null;
  bricklink_used_currency: string | null;
  bricklink_used_last_seen: string | null;
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
  image_url: string | null;
  prices: PriceRecord[];
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

export function formatPrice(
  cents: number | null,
  currency?: string | null
): string {
  if (cents === null) return '-';
  const amount = (cents / 100).toFixed(2);
  if (currency === 'USD') return `$${amount}`;
  return `RM${amount}`;
}

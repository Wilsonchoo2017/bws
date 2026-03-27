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

export function formatPrice(
  cents: number | null,
  currency?: string | null
): string {
  if (cents === null) return '-';
  const amount = (cents / 100).toFixed(2);
  if (currency === 'USD') return `$${amount}`;
  return `RM${amount}`;
}

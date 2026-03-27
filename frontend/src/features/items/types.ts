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

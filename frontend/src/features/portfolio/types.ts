export interface Transaction {
  id: number;
  set_number: string;
  txn_type: 'BUY' | 'SELL';
  quantity: number;
  price_cents: number;
  currency: string;
  condition: 'new' | 'used';
  txn_date: string;
  notes: string | null;
  created_at: string;
  bill_id: string | null;
  supplier: string | null;
  platform: string | null;
  title: string | null;
  image_url: string | null;
  theme: string | null;
}

export interface Holding {
  set_number: string;
  condition: 'new' | 'used';
  quantity: number;
  total_cost_cents: number;
  avg_cost_cents: number;
  current_value_cents: number;
  unrealized_pl_cents: number;
  unrealized_pl_pct: number;
  market_price_cents: number;
  title: string | null;
  image_url: string | null;
  theme: string | null;
  listing_price_cents: number | null;
  listing_currency: string | null;
  apr: number | null;
  days_held: number | null;
}

export interface HoldingCondition {
  condition: 'new' | 'used';
  quantity: number;
  total_cost_cents: number;
  avg_cost_cents: number;
  current_value_cents: number;
  unrealized_pl_cents: number;
  realized_pl_cents: number;
}

export interface HoldingDetail {
  set_number: string;
  title: string | null;
  image_url: string | null;
  theme: string | null;
  market_price_cents: number;
  conditions: HoldingCondition[];
  transactions: Transaction[];
}

export interface PortfolioSummary {
  total_cost_cents: number;
  total_market_value_cents: number;
  unrealized_pl_cents: number;
  unrealized_pl_pct: number;
  realized_pl_cents: number;
  holdings_count: number;
  unique_sets: number;
}

export interface ForwardReturn {
  set_number: string;
  forward_annual_return: number | null;
  expected_future_price_cents: number | null;
  current_price_cents: number;
  expected_time_years: number;
  price_source: 'bl_trend' | 'bricklink' | 'be_estimate' | 'ml_growth' | 'none';
  decision: 'BUY' | 'SELL' | 'HOLD' | 'SKIP';
  exceeds_target: boolean;
  exceeds_hurdle: boolean;
}

export interface WBRMetrics {
  avg_buy_discount_pct: number;
  avg_expected_return_new_buys: number;
  inventory_turnover: number;
  pct_capital_above_hurdle: number;
  total_forward_return_weighted: number;
  worst_holding: { set_number: string; forward_annual_return: number } | null;
  best_candidate: { set_number: string; forward_annual_return: number } | null;
}

export interface HoldingReallocation {
  set_number: string;
  capital_cents: number;
  market_value_cents: number;
  forward_annual_return: number | null;
  opportunity_cost_pct: number;
  opportunity_cost_cents: number;
  decision: 'BUY' | 'SELL' | 'HOLD' | 'SKIP';
}

export interface ReallocationData {
  total_capital_cents: number;
  total_opportunity_cost_cents: number;
  weighted_forward_return: number;
  sell_candidates: string[];
  holdings: HoldingReallocation[];
}

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

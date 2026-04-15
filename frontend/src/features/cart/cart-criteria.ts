import type { UnifiedItem } from '@/features/items/types';

export interface CartSettings {
  min_liquidity_score: number;
  deal_threshold_pct: number;
  min_confidence: string;
  max_avoid_probability: number;
  min_growth_pct: number;
}

const CONFIDENCE_ORDER: Record<string, number> = {
  high: 3,
  moderate: 2,
  low: 1,
};

/**
 * Check whether an item meets all cart auto-scan criteria.
 *
 * All conditions use AND logic -- every one must pass.
 *
 * Deal check: retail price within X% ABOVE BrickLink NEW price,
 * i.e. `retail <= BL_new * (1 + threshold/100)`.
 * This is intentionally different from the items page "deal" filter
 * which checks for discounts below BL price.
 */
export function meetsCartCriteria(
  item: UnifiedItem,
  settings: CartSettings
): boolean {
  // 1. Liquidity score >= threshold
  if (
    item.liquidity_score == null ||
    item.liquidity_score < settings.min_liquidity_score
  ) {
    return false;
  }

  // 2. Deal: any retail price within threshold% of BL new price
  if (item.bricklink_new_cents == null) return false;
  const maxRetail =
    item.bricklink_new_cents * (1 + settings.deal_threshold_pct / 100);
  const hasDeal =
    (item.shopee_price_cents != null &&
      item.shopee_price_cents <= maxRetail) ||
    (item.toysrus_price_cents != null &&
      item.toysrus_price_cents <= maxRetail) ||
    (item.mightyutan_price_cents != null &&
      item.mightyutan_price_cents <= maxRetail);
  if (!hasDeal) return false;

  // 3. ML confidence >= minimum (normalize to lowercase for safety)
  const minConf = CONFIDENCE_ORDER[settings.min_confidence.toLowerCase()] ?? 0;
  const itemConf = CONFIDENCE_ORDER[(item.ml_confidence ?? '').toLowerCase()] ?? 0;
  if (itemConf < minConf) return false;

  // 4. Must be GREAT. OOF walk-forward showed GOOD hits the 10% hurdle
  //    only 52% of the time out-of-fold — unreliable for live capital.
  //    GOOD stays visible as a category label elsewhere in the UI.
  if (item.ml_buy_category !== 'GREAT') {
    return false;
  }

  return true;
}

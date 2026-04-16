import type { UnifiedItem } from './types';

export type FilterKey =
  | 'watchlist'
  | 'has_retail'
  | 'has_shopee'
  | 'has_tru'
  | 'has_mu'
  | 'retired'
  | 'active'
  | 'retiring_soon'
  | 'cat_great'
  | 'cat_good'
  | 'cat_skip'
  | 'cat_worst'
  | 'cat_none'
  | 'conf_high'
  | 'conf_moderate'
  | 'conf_low'
  | 'deal'
  | 'cohort_half_year'
  | 'cohort_theme'
  | 'cohort_price_tier'
  | 'liq_high'
  | 'liq_medium'
  | 'liq_low'
  | 'liq_none';

export interface FilterGroup {
  id: string;
  label: string;
  filters: { key: FilterKey; label: string }[];
}

export const FILTER_GROUPS: FilterGroup[] = [
  {
    id: 'status',
    label: 'Status',
    filters: [
      { key: 'retired', label: 'Retired' },
      { key: 'retiring_soon', label: 'Retiring Soon' },
      { key: 'active', label: 'Active' },
    ],
  },
  {
    id: 'retail',
    label: 'Retail Price',
    filters: [
      { key: 'has_retail', label: 'Any Retail' },
      { key: 'has_shopee', label: 'Has Shopee' },
      { key: 'has_tru', label: 'Has TRU' },
      { key: 'has_mu', label: 'Has MU' },
    ],
  },
  {
    id: 'buy_category',
    label: 'Buy Category',
    filters: [
      { key: 'cat_great', label: 'GREAT' },
      { key: 'cat_good', label: 'GOOD' },
      { key: 'cat_skip', label: 'SKIP' },
      { key: 'cat_worst', label: 'WORST' },
      { key: 'cat_none', label: 'No Prediction' },
    ],
  },
  {
    id: 'confidence',
    label: 'Confidence',
    filters: [
      { key: 'conf_high', label: 'High' },
      { key: 'conf_moderate', label: 'Moderate' },
      { key: 'conf_low', label: 'Low' },
    ],
  },
  {
    id: 'cohort',
    label: 'Cohort',
    filters: [
      { key: 'cohort_half_year', label: 'Half-Year' },
      { key: 'cohort_theme', label: 'Theme' },
      { key: 'cohort_price_tier', label: 'Price Tier' },
    ],
  },
  {
    id: 'liquidity',
    label: 'Liquidity',
    filters: [
      { key: 'liq_high', label: 'High (70+)' },
      { key: 'liq_medium', label: 'Medium (40+)' },
      { key: 'liq_low', label: 'Low (<40)' },
      { key: 'liq_none', label: 'No Data' },
    ],
  },
  {
    id: 'watchlist',
    label: 'Watchlist',
    filters: [
      { key: 'watchlist', label: 'Watchlist' },
    ],
  },
  {
    id: 'deals',
    label: 'Deals',
    filters: [
      { key: 'deal', label: 'Deals' },
    ],
  },
];

const PREDICATES: Record<FilterKey, (item: UnifiedItem, dealThreshold: number, cohortThreshold: number) => boolean> = {
  watchlist: (item) => item.watchlist,
  has_retail: (item) =>
    item.toysrus_price_cents != null ||
    item.shopee_price_cents != null ||
    item.mightyutan_price_cents != null,
  has_shopee: (item) => item.shopee_price_cents != null,
  has_tru: (item) => item.toysrus_price_cents != null,
  has_mu: (item) => item.mightyutan_price_cents != null,
  retired: (item) =>
    item.year_retired !== null || item.availability?.toLowerCase() === 'retired',
  active: (item) =>
    item.year_retired === null && item.availability?.toLowerCase() !== 'retired',
  retiring_soon: (item) =>
    item.retiring_soon === true && item.year_retired === null,
  cat_great: (item) => item.ml_buy_category === 'GREAT',
  cat_good: (item) => item.ml_buy_category === 'GOOD',
  cat_skip: (item) => item.ml_buy_category === 'SKIP',
  cat_worst: (item) => item.ml_buy_category === 'WORST',
  cat_none: (item) => item.ml_buy_category == null || item.ml_buy_category === 'NONE',
  conf_high: (item) => item.ml_confidence === 'high',
  conf_moderate: (item) => item.ml_confidence === 'moderate',
  conf_low: (item) => item.ml_confidence === 'low',
  cohort_half_year: (item, _dt, ct) => item.cohort_half_year != null && item.cohort_half_year >= ct,
  cohort_theme: (item, _dt, ct) => item.cohort_theme != null && item.cohort_theme >= ct,
  cohort_price_tier: (item, _dt, ct) => item.cohort_price_tier != null && item.cohort_price_tier >= ct,
  liq_high: (item) => item.liquidity_score != null && item.liquidity_score >= 70,
  liq_medium: (item) => item.liquidity_score != null && item.liquidity_score >= 40 && item.liquidity_score < 70,
  liq_low: (item) => item.liquidity_score != null && item.liquidity_score < 40,
  liq_none: (item) => item.liquidity_score == null,
  deal: (item, dealThreshold) => {
    const blNewCents = item.bricklink_new_cents;
    if (blNewCents == null) return false;
    const maxPrice = blNewCents * (1 - dealThreshold / 100);
    return (
      (item.toysrus_price_cents != null && item.toysrus_price_cents <= maxPrice) ||
      (item.shopee_price_cents != null && item.shopee_price_cents <= maxPrice) ||
      (item.mightyutan_price_cents != null && item.mightyutan_price_cents <= maxPrice)
    );
  },
};

/**
 * Apply chip-based filters to items.
 * Within each filter group, active filters use OR logic (item matches if ANY active filter in group matches).
 * Exception: cohort group uses AND logic (item must pass ALL selected cohort filters).
 * Across groups, AND logic applies (item must pass every group that has active filters).
 */
export function applyFilters(
  items: readonly UnifiedItem[],
  activeFilters: ReadonlySet<FilterKey>,
  dealThreshold: number,
  cohortThreshold: number = 65
): UnifiedItem[] {
  if (activeFilters.size === 0) return [...items];

  // Group active filters by their group id
  const activeByGroup = new Map<string, { keys: FilterKey[]; andLogic: boolean }>();
  for (const group of FILTER_GROUPS) {
    const activeInGroup = group.filters
      .filter((f) => activeFilters.has(f.key))
      .map((f) => f.key);
    if (activeInGroup.length > 0) {
      activeByGroup.set(group.id, {
        keys: activeInGroup,
        andLogic: group.id === 'cohort',
      });
    }
  }

  return items.filter((item) => {
    for (const [, { keys, andLogic }] of activeByGroup) {
      if (andLogic) {
        // AND within group: item must pass ALL selected filters
        const passesGroup = keys.every((key) => PREDICATES[key](item, dealThreshold, cohortThreshold));
        if (!passesGroup) return false;
      } else {
        // OR within group: item passes if ANY filter in the group matches
        const passesGroup = keys.some((key) => PREDICATES[key](item, dealThreshold, cohortThreshold));
        if (!passesGroup) return false;
      }
    }
    return true;
  });
}

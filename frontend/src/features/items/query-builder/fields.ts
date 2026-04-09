import type {
  FieldDefinition,
  FieldType,
  StringOperator,
  NumberOperator,
  BooleanOperator,
  DateOperator,
  Operator,
} from './types';

export const QUERY_FIELDS: readonly FieldDefinition[] = [
  // Catalog
  { key: 'set_number', label: 'Set Number', type: 'string', group: 'Catalog' },
  { key: 'title', label: 'Title', type: 'string', group: 'Catalog' },
  { key: 'theme', label: 'Theme', type: 'string', group: 'Catalog' },
  { key: 'year_released', label: 'Year Released', type: 'number', group: 'Catalog' },
  { key: 'year_retired', label: 'Year Retired', type: 'number', group: 'Catalog' },
  { key: 'availability', label: 'Availability', type: 'string', group: 'Catalog' },
  { key: 'retiring_soon', label: 'Retiring Soon', type: 'boolean', group: 'Catalog' },
  { key: 'watchlist', label: 'Watchlist', type: 'boolean', group: 'Catalog' },
  { key: 'minifig_count', label: 'Minifig Count', type: 'number', group: 'Catalog' },
  { key: 'rrp_cents', label: 'RRP (cents)', type: 'number', group: 'Catalog' },

  // Shopee
  { key: 'shopee_price_cents', label: 'Shopee Price (cents)', type: 'number', group: 'Shopee' },
  { key: 'shopee_shop_count', label: 'Shopee Shop Count', type: 'number', group: 'Shopee' },
  { key: 'shopee_last_seen', label: 'Shopee Last Seen', type: 'date', group: 'Shopee' },

  // ToysRUs
  { key: 'toysrus_price_cents', label: 'TRU Price (cents)', type: 'number', group: 'ToysRUs' },
  { key: 'toysrus_last_seen', label: 'TRU Last Seen', type: 'date', group: 'ToysRUs' },

  // Mighty Utan
  { key: 'mightyutan_price_cents', label: 'MU Price (cents)', type: 'number', group: 'Mighty Utan' },
  { key: 'mightyutan_last_seen', label: 'MU Last Seen', type: 'date', group: 'Mighty Utan' },

  // BrickLink
  { key: 'bricklink_new_cents', label: 'BL New (cents)', type: 'number', group: 'BrickLink' },
  { key: 'bricklink_used_cents', label: 'BL Used (cents)', type: 'number', group: 'BrickLink' },
  { key: 'bricklink_new_last_seen', label: 'BL New Last Seen', type: 'date', group: 'BrickLink' },

  // ML
  { key: 'ml_growth_pct', label: 'ML Growth %', type: 'number', group: 'ML' },
  { key: 'ml_confidence', label: 'ML Confidence', type: 'string', group: 'ML' },
  { key: 'ml_avoid_probability', label: 'ML Avoid Prob', type: 'number', group: 'ML' },
  { key: 'ml_kelly_fraction', label: 'Kelly Fraction', type: 'number', group: 'ML' },
  { key: 'ml_win_probability', label: 'Win Probability', type: 'number', group: 'ML' },

  // Cohort Percentiles
  { key: 'cohort_half_year', label: 'Cohort Half-Year', type: 'number', group: 'Cohort' },
  { key: 'cohort_year', label: 'Cohort Year', type: 'number', group: 'Cohort' },
  { key: 'cohort_theme', label: 'Cohort Theme', type: 'number', group: 'Cohort' },
  { key: 'cohort_year_theme', label: 'Cohort Year+Theme', type: 'number', group: 'Cohort' },
  { key: 'cohort_price_tier', label: 'Cohort Price Tier', type: 'number', group: 'Cohort' },
  { key: 'cohort_piece_group', label: 'Cohort Piece Grp', type: 'number', group: 'Cohort' },

  // Liquidity
  { key: 'liquidity_score', label: 'Liquidity Score', type: 'number', group: 'Liquidity' },
  { key: 'liq_cohort_half_year', label: 'Liq Half-Year', type: 'number', group: 'Liquidity' },
  { key: 'liq_cohort_year', label: 'Liq Year', type: 'number', group: 'Liquidity' },
  { key: 'liq_cohort_theme', label: 'Liq Theme', type: 'number', group: 'Liquidity' },
];

const STRING_OPERATORS: readonly { readonly value: StringOperator; readonly label: string }[] = [
  { value: 'equals', label: 'equals' },
  { value: 'not_equals', label: 'does not equal' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' },
  { value: 'starts_with', label: 'starts with' },
  { value: 'ends_with', label: 'ends with' },
  { value: 'is_empty', label: 'is empty' },
  { value: 'is_not_empty', label: 'is not empty' },
];

const NUMBER_OPERATORS: readonly { readonly value: NumberOperator; readonly label: string }[] = [
  { value: 'equals', label: '=' },
  { value: 'not_equals', label: '!=' },
  { value: 'greater_than', label: '>' },
  { value: 'greater_than_or_equal', label: '>=' },
  { value: 'less_than', label: '<' },
  { value: 'less_than_or_equal', label: '<=' },
  { value: 'between', label: 'between' },
  { value: 'is_empty', label: 'is empty' },
  { value: 'is_not_empty', label: 'is not empty' },
];

const BOOLEAN_OPERATORS: readonly { readonly value: BooleanOperator; readonly label: string }[] = [
  { value: 'is_true', label: 'is true' },
  { value: 'is_false', label: 'is false' },
];

const DATE_OPERATORS: readonly { readonly value: DateOperator; readonly label: string }[] = [
  { value: 'equals', label: 'equals' },
  { value: 'before', label: 'before' },
  { value: 'after', label: 'after' },
  { value: 'between', label: 'between' },
  { value: 'is_empty', label: 'is empty' },
  { value: 'is_not_empty', label: 'is not empty' },
];

export function getOperatorsForType(
  type: FieldType
): readonly { readonly value: Operator; readonly label: string }[] {
  switch (type) {
    case 'string':
      return STRING_OPERATORS;
    case 'number':
      return NUMBER_OPERATORS;
    case 'boolean':
      return BOOLEAN_OPERATORS;
    case 'date':
      return DATE_OPERATORS;
  }
}

export function getFieldByKey(key: string): FieldDefinition | undefined {
  return QUERY_FIELDS.find((f) => f.key === key);
}

const NO_VALUE_OPERATORS = new Set<string>([
  'is_empty',
  'is_not_empty',
  'is_true',
  'is_false',
]);

export function operatorNeedsValue(op: Operator): boolean {
  return !NO_VALUE_OPERATORS.has(op);
}

export function operatorNeedsSecondValue(op: Operator): boolean {
  return op === 'between';
}

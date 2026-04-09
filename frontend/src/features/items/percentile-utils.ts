// ---------------------------------------------------------------------------
// ML signal weights (mirrored from config/kelly.py SIGNAL_WEIGHTS)
// Higher weight = more important to the model = stricter green threshold
// ---------------------------------------------------------------------------
export const SIGNAL_WEIGHTS: Record<string, number> = {
  demand_pressure: 1.0,
  supply_velocity: 1.0,
  price_trend: 0.3,
  price_vs_rrp: 1.0,
  lifecycle_position: 1.5,
  stock_level: 1.0,
  collector_premium: 1.0,
  theme_growth: 1.2,
  value_opportunity: 1.8,
  price_wall: 1.0,
  listing_ratio: 1.2,
  new_used_spread: 1.2,
};

// Liquidity sub-metric weights (from api/routes/items.py composite formula)
export const LIQUIDITY_WEIGHTS: Record<string, number> = {
  volume: 1.4,       // 50% composite weight -> above-average importance
  consistency: 1.1,  // 38% composite weight -> slightly above average
  trend: 0.8,        // not in composite -> below average
  listing_ratio: 0.6, // 12% composite weight -> lowest importance
  quantity: 0.8,     // informational, not in composite
};

const DEFAULT_WEIGHT = 1.0;

// Scale factor: each 1.0 of weight above/below 1.0 shifts thresholds by this many points
const WEIGHT_SCALE = 10;

// Base thresholds (weight = 1.0)
const BASE_STRONG = 80;
const BASE_GOOD = 65;
const BASE_NEUTRAL = 50;
const BASE_WEAK = 35;

function weightedThresholds(weight: number): [number, number, number, number] {
  const shift = (weight - DEFAULT_WEIGHT) * WEIGHT_SCALE;
  return [
    Math.min(95, Math.max(60, BASE_STRONG + shift)),
    Math.min(85, Math.max(45, BASE_GOOD + shift)),
    Math.min(75, Math.max(30, BASE_NEUTRAL + shift)),
    Math.min(65, Math.max(20, BASE_WEAK + shift)),
  ];
}

export function scoreColor(score: number | null, weight?: number): string {
  if (score === null) return 'text-muted-foreground';
  const [strong, good, neutral, weak] = weightedThresholds(weight ?? DEFAULT_WEIGHT);
  if (score >= strong) return 'text-emerald-400';
  if (score >= good) return 'text-emerald-600 dark:text-emerald-500';
  if (score >= neutral) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= weak) return 'text-orange-500';
  return 'text-red-500';
}

export function scoreBg(score: number | null, weight?: number): string {
  if (score === null) return '';
  const [strong, good, neutral, weak] = weightedThresholds(weight ?? DEFAULT_WEIGHT);
  if (score >= strong) return 'bg-emerald-500/10';
  if (score >= good) return 'bg-emerald-500/5';
  if (score >= neutral) return 'bg-yellow-500/5';
  if (score >= weak) return 'bg-orange-500/5';
  return 'bg-red-500/10';
}

/** Look up the ML weight for a signal key. Falls back to 1.0. */
export function getSignalWeight(signalKey: string): number {
  return SIGNAL_WEIGHTS[signalKey] ?? DEFAULT_WEIGHT;
}

/** Look up the liquidity sub-metric weight. Falls back to 1.0. */
export function getLiquidityWeight(metricKey: string): number {
  return LIQUIDITY_WEIGHTS[metricKey] ?? DEFAULT_WEIGHT;
}

export function rankToPercentile(rank: number | null, size: number): number | null {
  if (rank === null || size <= 0) return null;
  return Math.round(((size - rank) / size) * 100);
}

export function formatMetricValue(key: string, value: number): string {
  if (key === 'consistency') return `${(value * 100).toFixed(0)}%`;
  if (key === 'trend') return `${value >= 1 ? '+' : ''}${((value - 1) * 100).toFixed(0)}%`;
  if (key === 'listing_ratio') return `${value.toFixed(1)}x`;
  return value?.toFixed(1) ?? '--';
}

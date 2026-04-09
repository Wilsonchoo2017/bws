import { describe, it, expect } from 'vitest';
import { scoreColor, scoreBg, rankToPercentile, formatMetricValue, getSignalWeight, getLiquidityWeight, SIGNAL_WEIGHTS } from './percentile-utils';

describe('scoreColor', () => {
  it('given null score, when rendering, then returns muted foreground', () => {
    expect(scoreColor(null)).toBe('text-muted-foreground');
  });

  it('given score >= 80, when rendering, then returns strong emerald', () => {
    expect(scoreColor(80)).toBe('text-emerald-400');
    expect(scoreColor(100)).toBe('text-emerald-400');
  });

  it('given score 65-79, when rendering, then returns good emerald', () => {
    expect(scoreColor(65)).toBe('text-emerald-600 dark:text-emerald-500');
    expect(scoreColor(79)).toBe('text-emerald-600 dark:text-emerald-500');
  });

  it('given score 50-64, when rendering, then returns neutral yellow', () => {
    expect(scoreColor(50)).toBe('text-yellow-600 dark:text-yellow-400');
    expect(scoreColor(64)).toBe('text-yellow-600 dark:text-yellow-400');
  });

  it('given score 35-49, when rendering, then returns weak orange', () => {
    expect(scoreColor(35)).toBe('text-orange-500');
    expect(scoreColor(49)).toBe('text-orange-500');
  });

  it('given score < 35, when rendering, then returns poor red', () => {
    expect(scoreColor(34)).toBe('text-red-500');
    expect(scoreColor(0)).toBe('text-red-500');
  });
});

describe('scoreBg', () => {
  it('given null score, when rendering, then returns empty string', () => {
    expect(scoreBg(null)).toBe('');
  });

  it('given score >= 80, when rendering, then returns strong emerald bg', () => {
    expect(scoreBg(80)).toBe('bg-emerald-500/10');
  });

  it('given score 65-79, when rendering, then returns good emerald bg', () => {
    expect(scoreBg(65)).toBe('bg-emerald-500/5');
  });

  it('given score 50-64, when rendering, then returns neutral yellow bg', () => {
    expect(scoreBg(50)).toBe('bg-yellow-500/5');
  });

  it('given score 35-49, when rendering, then returns weak orange bg', () => {
    expect(scoreBg(35)).toBe('bg-orange-500/5');
  });

  it('given score < 35, when rendering, then returns poor red bg', () => {
    expect(scoreBg(10)).toBe('bg-red-500/10');
  });
});

describe('rankToPercentile', () => {
  it('given rank 23 out of 184, when converting, then returns P88 (higher = better)', () => {
    expect(rankToPercentile(23, 184)).toBe(88);
  });

  it('given rank 1 out of 100, when converting, then returns P99 (best)', () => {
    expect(rankToPercentile(1, 100)).toBe(99);
  });

  it('given rank 100 out of 100, when converting, then returns P0 (worst)', () => {
    expect(rankToPercentile(100, 100)).toBe(0);
  });

  it('given rank 50 out of 100, when converting, then returns P50 (median)', () => {
    expect(rankToPercentile(50, 100)).toBe(50);
  });

  it('given null rank, when converting, then returns null', () => {
    expect(rankToPercentile(null, 100)).toBeNull();
  });

  it('given size 0, when converting, then returns null (no division by zero)', () => {
    expect(rankToPercentile(1, 0)).toBeNull();
  });

  it('given negative size, when converting, then returns null', () => {
    expect(rankToPercentile(1, -5)).toBeNull();
  });

  it('given rank 4 out of 13, when converting, then returns P69', () => {
    expect(rankToPercentile(4, 13)).toBe(69);
  });

  it('given rank 640 out of 2951, when converting, then returns P78', () => {
    expect(rankToPercentile(640, 2951)).toBe(78);
  });
});

describe('formatMetricValue', () => {
  it('given consistency 1.0, when formatting, then returns 100%', () => {
    expect(formatMetricValue('consistency', 1.0)).toBe('100%');
  });

  it('given consistency 0.8, when formatting, then returns 80%', () => {
    expect(formatMetricValue('consistency', 0.8)).toBe('80%');
  });

  it('given trend ratio 1.28, when formatting, then returns +28%', () => {
    expect(formatMetricValue('trend', 1.28)).toBe('+28%');
  });

  it('given trend ratio 0.85, when formatting, then returns -15%', () => {
    expect(formatMetricValue('trend', 0.85)).toBe('-15%');
  });

  it('given trend ratio 1.0, when formatting, then returns +0%', () => {
    expect(formatMetricValue('trend', 1.0)).toBe('+0%');
  });

  it('given listing_ratio 16.9, when formatting, then returns 16.9x', () => {
    expect(formatMetricValue('listing_ratio', 16.9)).toBe('16.9x');
  });

  it('given volume 5.2, when formatting, then returns 5.2', () => {
    expect(formatMetricValue('volume', 5.2)).toBe('5.2');
  });

  it('given quantity 6.0, when formatting, then returns 6.0', () => {
    expect(formatMetricValue('quantity', 6.0)).toBe('6.0');
  });
});

describe('consistency: all metrics are higher = better', () => {
  it('given rank #1/100, when converted to percentile, then returns highest value (99)', () => {
    const pct = rankToPercentile(1, 100);
    expect(pct).toBe(99);
    expect(scoreColor(pct)).toBe('text-emerald-400');
  });

  it('given rank #100/100, when converted to percentile, then returns lowest value (0)', () => {
    const pct = rankToPercentile(100, 100);
    expect(pct).toBe(0);
    expect(scoreColor(pct)).toBe('text-red-500');
  });

  it('given percentile P88, when checking color, then matches same color as scoreColor(88)', () => {
    const rankPct = rankToPercentile(23, 184);
    expect(rankPct).toBe(88);
    expect(scoreColor(rankPct)).toBe(scoreColor(88));
  });

  it('given cohort with composite_pct 64 and rank P88, when choosing display, then composite_pct takes priority', () => {
    const compositePct = 64;
    const rankPct = rankToPercentile(23, 184);
    const overall = compositePct ?? rankPct;
    expect(overall).toBe(64);
  });

  it('given cohort with null composite_pct and rank P88, when choosing display, then rank percentile is fallback', () => {
    const compositePct = null;
    const rankPct = rankToPercentile(23, 184);
    const overall = compositePct ?? rankPct;
    expect(overall).toBe(88);
  });
});

describe('weight-aware scoring', () => {
  it('given high weight (1.8), score 82 is NOT strong green (thresholds shift up)', () => {
    // Base strong threshold is 80, but at weight 1.8 it shifts to 88
    expect(scoreColor(82, 1.8)).toBe('text-emerald-600 dark:text-emerald-500');
  });

  it('given high weight (1.8), score 90 IS strong green', () => {
    expect(scoreColor(90, 1.8)).toBe('text-emerald-400');
  });

  it('given low weight (0.3), score 73 IS strong green (thresholds shift down)', () => {
    // Base strong threshold is 80, but at weight 0.3 it shifts to 73
    expect(scoreColor(73, 0.3)).toBe('text-emerald-400');
  });

  it('given low weight (0.3), score 60 is good green (more lenient)', () => {
    // At weight 0.3, good threshold shifts from 65 to 58
    expect(scoreColor(60, 0.3)).toBe('text-emerald-600 dark:text-emerald-500');
  });

  it('given default weight (1.0), thresholds match original behavior', () => {
    expect(scoreColor(80, 1.0)).toBe('text-emerald-400');
    expect(scoreColor(65, 1.0)).toBe('text-emerald-600 dark:text-emerald-500');
    expect(scoreColor(50, 1.0)).toBe('text-yellow-600 dark:text-yellow-400');
    expect(scoreColor(35, 1.0)).toBe('text-orange-500');
    expect(scoreColor(34, 1.0)).toBe('text-red-500');
  });

  it('given no weight, thresholds match default (1.0) behavior', () => {
    expect(scoreColor(80)).toBe(scoreColor(80, 1.0));
    expect(scoreColor(50)).toBe(scoreColor(50, 1.0));
  });

  it('scoreBg respects weight too', () => {
    // At weight 1.8, 82 is "good" not "strong"
    expect(scoreBg(82, 1.8)).toBe('bg-emerald-500/5');
    expect(scoreBg(90, 1.8)).toBe('bg-emerald-500/10');
  });
});

describe('signal weight lookups', () => {
  it('returns correct weight for known signals', () => {
    expect(getSignalWeight('value_opportunity')).toBe(1.8);
    expect(getSignalWeight('lifecycle_position')).toBe(1.5);
    expect(getSignalWeight('price_trend')).toBe(0.3);
    expect(getSignalWeight('demand_pressure')).toBe(1.0);
  });

  it('returns default 1.0 for unknown signals', () => {
    expect(getSignalWeight('unknown_signal')).toBe(1.0);
  });

  it('returns correct liquidity weights', () => {
    expect(getLiquidityWeight('volume')).toBe(1.4);
    expect(getLiquidityWeight('consistency')).toBe(1.1);
    expect(getLiquidityWeight('listing_ratio')).toBe(0.6);
  });

  it('SIGNAL_WEIGHTS mirrors config/kelly.py', () => {
    expect(Object.keys(SIGNAL_WEIGHTS)).toHaveLength(12);
  });
});

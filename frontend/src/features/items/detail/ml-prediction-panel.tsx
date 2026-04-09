'use client';

import { useEffect, useState } from 'react';
import { useDetailBundle } from './detail-bundle-context';
import { PredictionHistoryChart } from './prediction-history-chart';

interface Driver {
  feature: string;
  impact: number;
}

interface GrowthPrediction {
  set_number: string;
  growth_pct: number;
  confidence: string;
  tier?: number;
  buy_signal?: boolean;
  avoid?: boolean;
  avoid_probability?: number;
  drivers?: Driver[];
  shap_base?: number;
}

interface MissingDataResponse {
  set_number: string;
  error: string;
  missing: string[];
  has: Record<string, boolean>;
}

function growthColor(pct: number): string {
  if (pct >= 20) return 'text-emerald-400';
  if (pct >= 15) return 'text-emerald-500';
  if (pct >= 10) return 'text-green-500';
  if (pct >= 5) return 'text-yellow-500';
  return 'text-red-400';
}

function growthBg(pct: number): string {
  if (pct >= 20) return 'bg-emerald-500/10 border-emerald-500/20';
  if (pct >= 15) return 'bg-emerald-500/5 border-emerald-500/15';
  if (pct >= 10) return 'bg-green-500/5 border-green-500/15';
  if (pct >= 5) return 'bg-yellow-500/5 border-yellow-500/15';
  return 'bg-red-500/5 border-red-500/15';
}

function confidenceBadge(confidence: string): { label: string; className: string } {
  switch (confidence) {
    case 'high':
      return {
        label: 'High Confidence',
        className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
      };
    case 'moderate':
      return {
        label: 'Moderate',
        className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
      };
    default:
      return {
        label: 'Low',
        className: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
      };
  }
}

function tierLabel(tier: number): string {
  if (tier === 4) return 'Tier 4 (Ensemble)';
  if (tier === 3) return 'Tier 3 (Extractors)';
  if (tier === 2) return 'Tier 2 (Intrinsics + Keepa)';
  return 'Tier 1 (Intrinsics)';
}

const FEATURE_LABELS: Record<string, string> = {
  // Theme & subtheme
  theme_bayes: 'Theme track record',
  theme_growth_std: 'Theme volatility',
  theme_size: 'Theme popularity',
  theme_x_price: 'Theme x price fit',
  subtheme_loo: 'Subtheme track record',
  sub_size: 'Subtheme size',
  is_licensed: 'Licensed theme',
  // Set characteristics
  log_rrp: 'Retail price',
  log_parts: 'Piece count',
  price_per_part: 'Price per piece',
  mfigs: 'Minifigure count',
  minifig_density: 'Minifig density',
  mfig_value_to_rrp: 'Minifig value vs RRP',
  price_tier: 'Price tier',
  rating_value: 'Collector rating',
  rating_x_price: 'Rating x price',
  log_reviews: 'Review count',
  has_designer: 'Designer credited',
  retire_quarter: 'Retirement quarter',
  retires_before_q4: 'Retires before Q4',
  // Relative rankings
  review_rank_in_year: 'Popularity in year',
  review_rank_in_theme: 'Popularity in theme',
  review_rank_in_retire_year: 'Popularity at retirement',
  review_rank_in_pieces_tier: 'Popularity in size tier',
  shelf_life_x_reviews: 'Shelf life x reviews',
  // Pricing & regional
  usd_gbp_ratio: 'Regional pricing gap',
  usd_vs_mean: 'US price vs global avg',
  currency_cv: 'Cross-currency variance',
  dist_cv: 'Distribution variance',
  // Amazon / Keepa
  kp_below_rrp_pct: 'Time below RRP (Amazon)',
  kp_avg_discount: 'Avg discount (Amazon)',
  kp_max_discount: 'Max discount (Amazon)',
  kp_price_trend: 'Price trend (Amazon)',
  kp_price_cv: 'Price volatility (Amazon)',
  kp_months_stock: 'Months in stock (Amazon)',
  kp_bb_premium: 'Buy box premium at OOS',
  kp_fba_floor_vs_rrp: 'FBA floor vs RRP',
  kp_fbm_mean_vs_rrp: 'FBM price vs RRP',
  kp_fba_floor_above_rrp: 'FBA floor above RRP',
  kp_fba_never_below_rrp: 'FBA never below RRP',
};

function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature.replace(/_/g, ' ');
}

interface MLPredictionPanelProps {
  setNumber: string;
}

export function MLPredictionPanel({ setNumber }: MLPredictionPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [missingData, setMissingData] = useState<MissingDataResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (bundleLoading) return;
    const bundleMl = bundle?.ml_growth as GrowthPrediction | null;
    if (bundleMl) {
      if (bundleMl.growth_pct != null) { setPrediction(bundleMl); }
      else if ((bundleMl as unknown as MissingDataResponse).missing) { setMissingData(bundleMl as unknown as MissingDataResponse); }
      setLoading(false);
      return;
    }
    fetch(`/api/ml/growth/predictions/${setNumber}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.growth_pct != null) {
          setPrediction(json);
        } else if (json.missing) {
          setMissingData(json);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [setNumber, bundle, bundleLoading]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">ML Growth Prediction</h2>
        <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!prediction) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">ML Growth Prediction</h2>
        {missingData && missingData.missing.length > 0 ? (
          <MissingDataInfo data={missingData} />
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            No ML prediction available for this set.
          </p>
        )}
      </div>
    );
  }

  const { growth_pct, confidence, drivers, shap_base, buy_signal, avoid, avoid_probability } = prediction;
  const badge = confidenceBadge(confidence);
  const hasShap = shap_base != null;

  const signalLabel = avoid
    ? 'AVOID'
    : buy_signal
      ? 'BUY'
      : 'HOLD';
  const signalColor = avoid
    ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    : buy_signal
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
      : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">ML Growth Prediction</h2>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${signalColor}`}>
            {signalLabel}
          </span>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>
            {badge.label}
          </span>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-6">
        {/* Main growth number */}
        <div className={`rounded-xl border px-6 py-4 ${growthBg(growth_pct)}`}>
          <div className="text-xs font-medium text-muted-foreground">
            Predicted Annual Growth
          </div>
          <div className={`mt-1 text-3xl font-bold tabular-nums ${growthColor(growth_pct)}`}>
            +{growth_pct.toFixed(1)}%
          </div>
        </div>

        {/* Context */}
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Signal:</span>
            <span className="font-medium">
              {avoid
                ? 'Classifier flagged as loser — do not buy'
                : buy_signal
                  ? `Buy — growth above ${8}% hurdle`
                  : `Hold — growth below ${8}% hurdle`}
            </span>
          </div>
          {avoid_probability != null && (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Risk:</span>
              <span>{(avoid_probability * 100).toFixed(0)}% chance of underperformance</span>
            </div>
          )}
          <div className="text-xs text-muted-foreground">
            Based on theme, subtheme, set characteristics, and pricing strategy.
          </div>
        </div>
      </div>

      {/* Key drivers */}
      {drivers && drivers.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-muted-foreground">
            {hasShap ? 'Why this prediction' : 'Top factors'}
          </h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {drivers.map((d) => {
              const isPositive = d.impact >= 0;
              return (
                <span
                  key={d.feature}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                    isPositive
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-red-500/10 text-red-600 dark:text-red-400'
                  }`}
                  title={`${d.feature}: ${isPositive ? '+' : ''}${d.impact.toFixed(3)}`}
                >
                  {isPositive ? '\u2191' : '\u2193'} {featureLabel(d.feature)}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Growth scale */}
      <div className="mt-4">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Poor (&lt;5%)</span>
          <span>Hold (5-10%)</span>
          <span>Buy (10-15%)</span>
          <span>Strong (&gt;15%)</span>
        </div>
        <div className="relative mt-1 h-2 w-full rounded-full bg-muted">
          <div
            className={`absolute top-0 left-0 h-2 rounded-full transition-all ${
              growth_pct >= 15
                ? 'bg-emerald-500'
                : growth_pct >= 10
                  ? 'bg-green-500'
                  : growth_pct >= 5
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
            }`}
            style={{ width: `${Math.min(100, (growth_pct / 30) * 100)}%` }}
          />
          {/* Marker at current position */}
          <div
            className="absolute top-[-3px] h-4 w-1 rounded-full bg-foreground"
            style={{ left: `${Math.min(100, (growth_pct / 30) * 100)}%` }}
          />
        </div>
      </div>

      {/* Prediction history chart */}
      <PredictionHistoryChart setNumber={prediction.set_number} />

    </div>
  );
}


function MissingDataInfo({ data }: { data: MissingDataResponse }) {
  const { missing, has } = data;

  const sources: { key: string; label: string; present: boolean }[] = [
    { key: 'lego_item', label: 'Catalog entry', present: has.lego_item ?? false },
    { key: 'brickeconomy', label: 'BrickEconomy snapshot', present: has.brickeconomy ?? false },
    { key: 'rrp', label: 'RRP price', present: has.rrp ?? false },
    { key: 'pieces', label: 'Piece count', present: has.pieces ?? false },
    { key: 'rating', label: 'Rating', present: has.rating ?? false },
    { key: 'reviews', label: 'Review count', present: has.reviews ?? false },
    { key: 'keepa', label: 'Keepa Amazon data', present: has.keepa ?? false },
  ];

  // Only show sources that are relevant (skip sub-fields if parent is missing)
  const visible = has.brickeconomy === false
    ? sources.filter((s) => s.key === 'lego_item' || s.key === 'brickeconomy' || s.key === 'keepa')
    : sources;

  return (
    <div className="mt-3 space-y-3">
      <p className="text-sm text-muted-foreground">
        Cannot generate a prediction. The following data is needed:
      </p>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-3">
        {visible.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5">
            {s.present ? (
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
            ) : (
              <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
            )}
            <span className={s.present ? 'text-muted-foreground' : 'text-foreground font-medium'}>
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {missing.length > 0 && (
        <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
          {missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

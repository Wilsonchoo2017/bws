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
  great_buy_probability?: number;
  buy_category?: 'GREAT' | 'GOOD' | 'SKIP' | 'WORST' | 'NONE';
  has_keepa_data?: boolean;
  has_bl_data?: boolean;
  drivers?: Driver[];
  shap_base?: number;
}

interface MissingDataResponse {
  set_number: string;
  error: string;
  missing: string[];
  has: Record<string, boolean>;
}

const FEATURE_LABELS: Record<string, string> = {
  theme_bayes: 'Theme track record',
  theme_growth_std: 'Theme volatility',
  theme_size: 'Theme popularity',
  theme_x_price: 'Theme x price fit',
  subtheme_loo: 'Subtheme track record',
  sub_size: 'Subtheme size',
  is_licensed: 'Licensed theme',
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
  review_rank_in_year: 'Popularity in year',
  review_rank_in_theme: 'Popularity in theme',
  review_rank_in_retire_year: 'Popularity at retirement',
  review_rank_in_pieces_tier: 'Popularity in size tier',
  shelf_life_x_reviews: 'Shelf life x reviews',
  usd_gbp_ratio: 'Regional pricing gap',
  usd_vs_mean: 'US price vs global avg',
  currency_cv: 'Cross-currency variance',
  dist_cv: 'Distribution variance',
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

const CATEGORY_STYLES: Record<string, { label: string; description: string; color: string; border: string }> = {
  GREAT: {
    label: 'GREAT BUY',
    description: 'High probability of strong post-retirement growth',
    color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
    border: 'border-emerald-500/20',
  },
  GOOD: {
    label: 'GOOD BUY',
    description: 'Predicted to outperform with moderate confidence',
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    border: 'border-blue-500/20',
  },
  SKIP: {
    label: 'SKIP',
    description: 'Does not meet buy criteria',
    color: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800/40 dark:text-neutral-400',
    border: 'border-neutral-500/20',
  },
  WORST: {
    label: 'AVOID',
    description: 'Classifier flagged as likely underperformer',
    color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    border: 'border-red-500/20',
  },
  NONE: {
    label: 'NO DATA',
    description: 'Prediction unavailable: set is missing Keepa or BrickLink data (model trained on both)',
    color: 'bg-slate-100 text-slate-600 dark:bg-slate-800/40 dark:text-slate-400',
    border: 'border-slate-500/20',
  },
};

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

interface MLPredictionPanelProps {
  setNumber: string;
}

export function MLPredictionPanel({ setNumber }: MLPredictionPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [missingData, setMissingData] = useState<MissingDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);
  const [predictError, setPredictError] = useState<string | null>(null);

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
        <h2 className="text-lg font-semibold">ML Models</h2>
        <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const handlePredict = () => {
    setPredicting(true);
    setPredictError(null);
    fetch(`/api/ml/growth/predict/${setNumber}`, { method: 'POST' })
      .then((res) => res.json())
      .then((json) => {
        if (json.error) {
          setPredictError(json.error);
        } else if (json.growth_pct != null) {
          setPrediction(json);
        } else {
          setPredictError('No prediction returned');
        }
      })
      .catch(() => setPredictError('Failed to reach prediction endpoint'))
      .finally(() => setPredicting(false));
  };

  if (!prediction) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">ML Models</h2>
        {missingData && missingData.missing.length > 0 ? (
          <MissingDataInfo data={missingData} />
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            No ML prediction available for this set.
          </p>
        )}
        <button
          onClick={handlePredict}
          disabled={predicting}
          className="mt-3 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {predicting ? 'Predicting...' : 'Run Prediction'}
        </button>
        {predictError && (
          <p className="mt-2 text-sm text-destructive">{predictError}</p>
        )}
      </div>
    );
  }

  const { confidence, drivers, shap_base, avoid_probability, great_buy_probability, buy_category } = prediction;
  const badge = confidenceBadge(confidence);
  const hasShap = shap_base != null;
  const category = buy_category ?? 'SKIP';
  const style = CATEGORY_STYLES[category] ?? CATEGORY_STYLES.SKIP;

  return (
    <div className="space-y-4">
      {/* Classification Model */}
      <div className="rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Classification Model</h2>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>
            {badge.label}
          </span>
        </div>

        <div className="mt-4 flex items-center gap-4">
          <div className={`rounded-xl border px-6 py-4 ${style.border} bg-muted/30`}>
            <span className={`rounded-full px-3 py-1 text-sm font-bold ${style.color}`}>
              {style.label}
            </span>
          </div>
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{style.description}</span>
            {great_buy_probability != null && (
              <span className="text-muted-foreground">
                P(great buy) = {(great_buy_probability * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>

        {/* Category breakdown bar */}
        <div className="mt-4">
          <div className="flex gap-1">
            {(['WORST', 'SKIP', 'GOOD', 'GREAT'] as const).map((cat) => {
              const isActive = category === cat;
              const barStyles: Record<string, string> = {
                WORST: 'bg-red-500',
                SKIP: 'bg-neutral-400 dark:bg-neutral-600',
                GOOD: 'bg-blue-500',
                GREAT: 'bg-emerald-500',
              };
              return (
                <div
                  key={cat}
                  className={`h-2 flex-1 rounded-full transition-opacity ${barStyles[cat]} ${isActive ? 'opacity-100' : 'opacity-20'}`}
                  title={cat}
                />
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
            <span>WORST</span>
            <span>SKIP</span>
            <span>GOOD</span>
            <span>GREAT</span>
          </div>
        </div>

        {/* Key drivers */}
        {drivers && drivers.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-muted-foreground">
              {hasShap ? 'Why this classification' : 'Top factors'}
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
      </div>

      {/* AVOID Inversion Model */}
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">Inversion Model (AVOID)</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          &quot;Tell me where I&apos;m going to die, so I&apos;ll never go there.&quot; -- Munger
        </p>

        {avoid_probability != null ? (
          <div className="mt-4">
            <div className="flex items-center gap-4">
              {/* Risk gauge */}
              <div className="flex flex-col items-center">
                <div className={`rounded-xl border px-5 py-3 ${
                  avoid_probability >= 0.5
                    ? 'border-red-500/30 bg-red-500/10'
                    : avoid_probability >= 0.2
                      ? 'border-yellow-500/30 bg-yellow-500/10'
                      : 'border-emerald-500/30 bg-emerald-500/10'
                }`}>
                  <div className="text-xs font-medium text-muted-foreground">
                    P(underperform)
                  </div>
                  <div className={`mt-1 text-2xl font-bold tabular-nums ${
                    avoid_probability >= 0.5
                      ? 'text-red-500'
                      : avoid_probability >= 0.2
                        ? 'text-yellow-500'
                        : 'text-emerald-500'
                  }`}>
                    {(avoid_probability * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-1.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Verdict:</span>
                  {avoid_probability >= 0.5 ? (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300">
                      AVOID
                    </span>
                  ) : avoid_probability >= 0.2 ? (
                    <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-xs font-bold text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300">
                      CAUTION
                    </span>
                  ) : (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                      CLEAR
                    </span>
                  )}
                </div>
                <span className="text-muted-foreground text-xs">
                  {avoid_probability >= 0.5
                    ? 'High risk of post-retirement underperformance. Do not buy.'
                    : avoid_probability >= 0.2
                      ? 'Moderate risk. Proceed with caution.'
                      : 'Low risk of underperformance based on classifier.'}
                </span>
              </div>
            </div>

            {/* Risk meter */}
            <div className="mt-4">
              <div className="relative h-2 w-full rounded-full bg-gradient-to-r from-emerald-500/30 via-yellow-500/30 to-red-500/30">
                <div
                  className={`absolute top-[-3px] h-4 w-1 rounded-full ${
                    avoid_probability >= 0.5 ? 'bg-red-500' : avoid_probability >= 0.2 ? 'bg-yellow-500' : 'bg-emerald-500'
                  }`}
                  style={{ left: `${Math.min(100, avoid_probability * 100)}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>Low risk (0%)</span>
                <span>Caution (20%)</span>
                <span>Avoid (50%)</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">
            Inversion model data not available for this set.
          </p>
        )}
      </div>

      {/* Prediction history chart */}
      <div className="rounded-lg border border-border p-4">
        <PredictionHistoryChart setNumber={prediction.set_number} />
      </div>
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

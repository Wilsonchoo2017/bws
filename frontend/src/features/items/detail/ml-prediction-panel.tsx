'use client';

import { useEffect, useState } from 'react';

interface Driver {
  feature: string;
  impact: number;
}

interface GrowthPrediction {
  set_number: string;
  growth_pct: number;
  confidence: string;
  tier: number;
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
  theme_bayes: 'Theme identity',
  subtheme_loo: 'Subtheme (e.g. UCS, Modular)',
  log_rrp: 'Retail price (RRP)',
  log_parts: 'Piece count',
  price_per_part: 'Price per piece',
  mfigs: 'Minifigure count',
  minifig_density: 'Minifigures per 100 pcs',
  price_tier: 'Price tier bracket',
  rating_value: 'Collector rating',
  review_count: 'Number of reviews',
  theme_size: 'Theme popularity (# sets)',
  is_licensed: 'Licensed theme (Star Wars, etc.)',
  usd_gbp_ratio: 'Regional pricing ratio',
  sub_size: 'Subtheme size',
  kp_below_rrp_pct: 'Time below RRP on Amazon',
  kp_avg_discount: 'Average Amazon discount',
  kp_max_discount: 'Deepest Amazon discount',
  kp_price_trend: 'Amazon price trend',
  kp_price_cv: 'Amazon price volatility',
  kp_months_stock: 'Months in stock on Amazon',
  kp_bb_premium: 'Buy box premium at OOS',
};

function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature.replace(/_/g, ' ');
}

interface MLPredictionPanelProps {
  setNumber: string;
}

export function MLPredictionPanel({ setNumber }: MLPredictionPanelProps) {
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [missingData, setMissingData] = useState<MissingDataResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
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
  }, [setNumber]);

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

  const { growth_pct, confidence, tier, drivers, shap_base } = prediction;
  const badge = confidenceBadge(confidence);
  const hasShap = shap_base != null;

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">ML Growth Prediction</h2>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>
            {badge.label}
          </span>
          <span className="text-xs text-muted-foreground">
            {tierLabel(tier)}
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
            <span className="text-muted-foreground">Verdict:</span>
            <span className="font-medium">
              {growth_pct >= 15
                ? 'Strong Buy'
                : growth_pct >= 10
                  ? 'Buy'
                  : growth_pct >= 5
                    ? 'Hold'
                    : 'Avoid'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Model:</span>
            <span>
              GBM with{' '}
              {tier === 2 ? '21 features (incl. Keepa Amazon data)' : '14 intrinsic features'}
            </span>
          </div>
          <div className="text-xs text-muted-foreground">
            Based on theme, subtheme, set characteristics, and pricing strategy.
            {tier === 2 && ' Enhanced with Amazon demand signals.'}
          </div>
        </div>
      </div>

      {/* Key drivers */}
      {drivers && drivers.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-muted-foreground">
            {hasShap ? 'Key Drivers (SHAP)' : 'Top Feature Importances'}
          </h3>
          <div className="mt-2 space-y-1.5">
            {drivers.map((d) => {
              const maxImpact = Math.max(...drivers.map((x) => Math.abs(x.impact)));
              const barWidth = maxImpact > 0 ? (Math.abs(d.impact) / maxImpact) * 100 : 0;
              const isPositive = d.impact >= 0;
              return (
                <div key={d.feature} className="flex items-center gap-2 text-sm">
                  <span className="w-44 shrink-0 truncate text-muted-foreground" title={d.feature}>
                    {featureLabel(d.feature)}
                  </span>
                  <div className="flex h-4 flex-1 items-center">
                    {hasShap ? (
                      /* SHAP: directional bar from center */
                      <div className="relative h-3 w-full">
                        <div className="absolute top-0 left-1/2 h-full w-px bg-border" />
                        {isPositive ? (
                          <div
                            className="absolute top-0 left-1/2 h-full rounded-r bg-emerald-500/70"
                            style={{ width: `${barWidth / 2}%` }}
                          />
                        ) : (
                          <div
                            className="absolute top-0 h-full rounded-l bg-red-400/70"
                            style={{ width: `${barWidth / 2}%`, right: '50%' }}
                          />
                        )}
                      </div>
                    ) : (
                      /* Global importance: simple bar */
                      <div className="h-3 w-full rounded bg-muted">
                        <div
                          className="h-full rounded bg-blue-500/60"
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                    )}
                  </div>
                  <span className="w-14 shrink-0 text-right tabular-nums text-xs text-muted-foreground">
                    {hasShap
                      ? `${isPositive ? '+' : ''}${d.impact.toFixed(2)}`
                      : `${(d.impact * 100).toFixed(0)}%`}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {hasShap
              ? 'SHAP values show how each feature pushed the prediction above or below the baseline.'
              : 'Global feature importances show which features the model relies on most across all sets.'}
          </p>
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

      {/* Tier upgrade hint for Tier 1 predictions */}
      {tier === 1 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Tier 1 only (intrinsic features). Add Keepa Amazon price history to unlock Tier 2 for higher confidence.
        </p>
      )}
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

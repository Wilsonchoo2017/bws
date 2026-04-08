'use client';

import { useEffect, useState } from 'react';

interface GrowthPrediction {
  growth_pct: number;
  confidence: string;
  tier: number;
  drivers?: { feature: string; impact: number }[];
}

interface InvestmentPanelProps {
  setNumber: string;
}

export function InvestmentPanel({ setNumber }: InvestmentPanelProps) {
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/ml/growth/predictions/${setNumber}`)
      .then((res) => res.json())
      .then((json) => { if (json.growth_pct != null) setPrediction(json); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [setNumber]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">Investment Analysis</h2>
        <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!prediction) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">Investment Analysis</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          No prediction available. Enrich with BrickEconomy data first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Growth drivers (from ML prediction) */}
      {prediction?.drivers && prediction.drivers.length > 0 && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Why This Set Grows</h3>
          <div className="mt-2 space-y-1.5">
            {prediction.drivers.map((d) => {
              const maxImpact = Math.max(...prediction.drivers!.map((x) => Math.abs(x.impact)));
              const barWidth = maxImpact > 0 ? (Math.abs(d.impact) / maxImpact) * 100 : 0;
              const isPositive = d.impact >= 0;
              return (
                <div key={d.feature} className="flex items-center gap-2 text-sm">
                  <span className="w-40 shrink-0 truncate text-muted-foreground">
                    {FEATURE_LABELS[d.feature] ?? d.feature.replace(/_/g, ' ')}
                  </span>
                  <div className="relative h-3 flex-1">
                    <div className="absolute top-0 left-1/2 h-full w-px bg-border" />
                    {isPositive ? (
                      <div className="absolute top-0 left-1/2 h-full rounded-r bg-emerald-500/70" style={{ width: `${barWidth / 2}%` }} />
                    ) : (
                      <div className="absolute top-0 h-full rounded-l bg-red-400/70" style={{ width: `${barWidth / 2}%`, right: '50%' }} />
                    )}
                  </div>
                  <span className="w-14 shrink-0 text-right tabular-nums text-xs text-muted-foreground">
                    {isPositive ? '+' : ''}{d.impact.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const FEATURE_LABELS: Record<string, string> = {
  theme_bayes: 'Theme identity',
  subtheme_loo: 'Subtheme strength',
  log_rrp: 'Price point',
  log_parts: 'Set size',
  price_per_part: 'Value ratio',
  mfigs: 'Minifigures',
  minifig_density: 'Minifig density',
  rating_value: 'Rating',
  log_reviews: 'Popularity',
  rating_x_reviews: 'Rating x Popularity',
  theme_size: 'Theme size',
  theme_growth_std: 'Theme volatility',
  is_licensed: 'Licensed IP',
  usd_gbp_ratio: 'Regional pricing',
  usd_vs_mean: 'USD vs global price',
  currency_cv: 'Price spread',
  sub_size: 'Subtheme size',
  theme_x_price: 'Theme x Price',
  licensed_x_parts: 'Licensed x Size',
  rating_x_price: 'Rating x Price',
  review_rank_in_theme: 'Reviews vs theme peers',
  review_rank_in_retire_year: 'Reviews vs retirement cohort',
  mfig_value_to_rrp: 'Minifig value ratio',
};

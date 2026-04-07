'use client';

import { useEffect, useState } from 'react';

interface BuySignalData {
  signal: string;
  reason: string;
  set_number: string;
  title: string;
  theme: string;
  rrp_myr: number;
  your_price_myr: number;
  discount_pct: number;
  predicted_growth_from_rrp_pct: number;
  effective_return_12m_pct: number;
  effective_return_24m_pct: number;
  expected_profit_12m_myr: number;
  expected_profit_24m_myr: number;
  expected_value_12m_myr: number;
  expected_value_24m_myr: number;
  max_buy_price_myr: number;
  min_discount_needed_pct: number;
  discount_scenarios: DiscountScenario[];
  avoid_probability?: number;
}

interface DiscountScenario {
  discount_pct: number;
  buy_price_myr: number;
  effective_return_12m_pct: number;
  profit_12m_myr: number;
  signal: string;
}

interface GrowthPrediction {
  growth_pct: number;
  confidence: string;
  tier: number;
  avoid_probability?: number;
  raw_growth_pct?: number;
  kelly_fraction?: number;
  win_probability?: number;
  drivers?: { feature: string; impact: number }[];
}

function signalColor(signal: string) {
  switch (signal) {
    case 'STRONG BUY':
      return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
    case 'BUY':
      return 'bg-green-500/15 text-green-400 border-green-500/30';
    case 'HOLD':
      return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30';
    case 'PASS':
      return 'bg-red-500/15 text-red-400 border-red-500/30';
    default:
      return 'bg-muted text-muted-foreground border-border';
  }
}

function signalBadgeColor(signal: string) {
  switch (signal) {
    case 'STRONG BUY':
      return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300';
    case 'BUY':
      return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
    case 'HOLD':
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300';
    case 'PASS':
      return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

function returnColor(pct: number) {
  if (pct >= 20) return 'text-emerald-400';
  if (pct >= 10) return 'text-green-400';
  if (pct >= 5) return 'text-yellow-400';
  if (pct >= 0) return 'text-orange-400';
  return 'text-red-400';
}

function formatMYR(amount: number) {
  return `RM ${amount.toFixed(0)}`;
}

interface InvestmentPanelProps {
  setNumber: string;
}

export function InvestmentPanel({ setNumber }: InvestmentPanelProps) {
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [buySignal, setBuySignal] = useState<BuySignalData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load both in parallel
    const predReq = fetch(`/api/ml/growth/predictions/${setNumber}`)
      .then((res) => res.json())
      .then((json) => { if (json.growth_pct != null) setPrediction(json); })
      .catch(() => {});

    const signalReq = fetch(`/api/ml/buy-signal/${setNumber}`)
      .then((res) => res.json())
      .then((json) => { if (json.signal) setBuySignal(json); })
      .catch(() => {});

    Promise.all([predReq, signalReq]).finally(() => setLoading(false));
  }, [setNumber]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">Investment Analysis</h2>
        <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!buySignal && !prediction) {
    return (
      <div className="rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold">Investment Analysis</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          No prediction available. Enrich with BrickEconomy data first.
        </p>
      </div>
    );
  }

  const data = buySignal;

  return (
    <div className="space-y-4">
      {/* Main signal card */}
      {data && (
        <div className={`rounded-xl border-2 p-5 ${signalColor(data.signal)}`}>
          <div className="flex items-start justify-between">
            <div>
              <span className={`inline-block rounded-full px-3 py-1 text-sm font-bold ${signalBadgeColor(data.signal)}`}>
                {data.signal}
              </span>
              <p className="mt-2 text-sm opacity-80">{data.reason}</p>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted-foreground">Your Effective Return</div>
              <div className={`text-3xl font-bold tabular-nums ${returnColor(data.effective_return_12m_pct)}`}>
                {data.effective_return_12m_pct > 0 ? '+' : ''}
                {data.effective_return_12m_pct.toFixed(1)}%
              </div>
              <div className="text-xs text-muted-foreground">12-month</div>
            </div>
          </div>
        </div>
      )}

      {/* Risk & position sizing */}
      {(prediction?.avoid_probability != null || prediction?.kelly_fraction != null) && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium text-muted-foreground">Risk & Position Sizing</h3>
          <div className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {prediction.avoid_probability != null && (
              <div>
                <div className="text-xs text-muted-foreground">Risk Level</div>
                <div className="mt-1">
                  <RiskBadge probability={prediction.avoid_probability} />
                </div>
                <div className={`mt-1 text-lg font-bold tabular-nums ${
                  prediction.avoid_probability < 0.2 ? 'text-emerald-400'
                  : prediction.avoid_probability < 0.5 ? 'text-yellow-400'
                  : prediction.avoid_probability < 0.8 ? 'text-orange-400'
                  : 'text-red-400'
                }`}>
                  {(prediction.avoid_probability * 100).toFixed(0)}%
                </div>
                <div className="text-[10px] text-muted-foreground">P(underperform)</div>
              </div>
            )}
            {prediction.win_probability != null && (
              <div>
                <div className="text-xs text-muted-foreground">Win Probability</div>
                <div className={`mt-1 text-lg font-bold tabular-nums ${
                  prediction.win_probability >= 0.8 ? 'text-emerald-400'
                  : prediction.win_probability >= 0.6 ? 'text-green-400'
                  : prediction.win_probability >= 0.4 ? 'text-yellow-400'
                  : 'text-red-400'
                }`}>
                  {(prediction.win_probability * 100).toFixed(0)}%
                </div>
                <div className="text-[10px] text-muted-foreground">P(return &gt; 8%)</div>
              </div>
            )}
            {prediction.kelly_fraction != null && prediction.kelly_fraction > 0 && (
              <div>
                <div className="text-xs text-muted-foreground">Kelly Size</div>
                <div className="mt-1 text-lg font-bold tabular-nums text-blue-400">
                  {(prediction.kelly_fraction * 100).toFixed(1)}%
                </div>
                <div className="text-[10px] text-muted-foreground">of portfolio</div>
              </div>
            )}
            {prediction.kelly_fraction != null && data?.rrp_myr && (
              <div>
                <div className="text-xs text-muted-foreground">Suggested Bet</div>
                <div className="mt-1 text-lg font-bold tabular-nums">
                  {formatMYR(prediction.kelly_fraction * 3000)}
                </div>
                <div className="text-[10px] text-muted-foreground">of RM 3,000 budget</div>
              </div>
            )}
          </div>
          {prediction.avoid_probability != null && (
            <p className="mt-2 text-xs text-muted-foreground">
              {prediction.avoid_probability < 0.2
                ? 'Low risk - model is confident this set will perform'
                : prediction.avoid_probability < 0.5
                ? 'Moderate risk - some uncertainty in performance'
                : prediction.avoid_probability < 0.8
                ? 'Elevated risk - consider smaller position or skip'
                : 'High risk - model flags this as likely underperformer'}
            </p>
          )}
        </div>
      )}

      {/* Price & profit summary */}
      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="RRP" value={formatMYR(data.rrp_myr)} />
          <StatCard label="Your Price" value={formatMYR(data.your_price_myr)} highlight={data.discount_pct > 0} sub={data.discount_pct > 0 ? `${data.discount_pct.toFixed(0)}% off` : 'At RRP'} />
          <StatCard label="12m Profit" value={formatMYR(data.expected_profit_12m_myr)} positive={data.expected_profit_12m_myr > 0} />
          <StatCard label="24m Profit" value={formatMYR(data.expected_profit_24m_myr)} positive={data.expected_profit_24m_myr > 0} />
        </div>
      )}

      {/* Break-even info */}
      {data && (
        <div className="rounded-lg border border-border p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Max price worth buying</span>
            <span className="font-semibold">{formatMYR(data.max_buy_price_myr)}</span>
          </div>
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Minimum discount needed</span>
            <span className="font-semibold">
              {data.min_discount_needed_pct <= 0
                ? `None (can pay ${(-data.min_discount_needed_pct).toFixed(0)}% above RRP)`
                : `${data.min_discount_needed_pct.toFixed(0)}% off RRP`}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Expected 12m value</span>
            <span className="font-semibold">{formatMYR(data.expected_value_12m_myr)}</span>
          </div>
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Expected 24m value</span>
            <span className="font-semibold">{formatMYR(data.expected_value_24m_myr)}</span>
          </div>
        </div>
      )}

      {/* Discount scenarios table */}
      {data?.discount_scenarios && data.discount_scenarios.length > 0 && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium">Buy Price Guide</h3>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="pb-2 text-left font-medium">Discount</th>
                  <th className="pb-2 text-right font-medium">Buy Price</th>
                  <th className="pb-2 text-right font-medium">12m Return</th>
                  <th className="pb-2 text-right font-medium">12m Profit</th>
                  <th className="pb-2 text-center font-medium">Signal</th>
                </tr>
              </thead>
              <tbody>
                {data.discount_scenarios.map((s) => (
                  <tr key={s.discount_pct} className="border-t border-border/50">
                    <td className="py-1.5">{s.discount_pct}% off</td>
                    <td className="py-1.5 text-right tabular-nums">{formatMYR(s.buy_price_myr)}</td>
                    <td className={`py-1.5 text-right tabular-nums font-medium ${returnColor(s.effective_return_12m_pct)}`}>
                      +{s.effective_return_12m_pct.toFixed(1)}%
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{formatMYR(s.profit_12m_myr)}</td>
                    <td className="py-1.5 text-center">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${signalBadgeColor(s.signal)}`}>
                        {s.signal}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

function RiskBadge({ probability }: { probability: number }) {
  if (probability < 0.2) {
    return <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">LOW RISK</span>;
  }
  if (probability < 0.5) {
    return <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-bold text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300">MODERATE</span>;
  }
  if (probability < 0.8) {
    return <span className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-bold text-orange-800 dark:bg-orange-900/40 dark:text-orange-300">ELEVATED</span>;
  }
  return <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-bold text-red-800 dark:bg-red-900/40 dark:text-red-300">HIGH RISK</span>;
}

function StatCard({ label, value, sub, highlight, positive }: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  positive?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 text-lg font-bold tabular-nums ${positive ? 'text-emerald-400' : highlight ? 'text-blue-400' : ''}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
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

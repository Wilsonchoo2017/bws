'use client';

import { useEffect, useState } from 'react';
import type { CohortRank, ItemSignals } from './types';

const SIGNALS = [
  { key: 'demand_pressure', label: 'Demand', desc: '3-month average sales volume' },
  { key: 'supply_velocity', label: 'Supply Velocity', desc: 'Rate of change in available inventory' },
  { key: 'price_trend', label: 'Price Trend', desc: '6-month linear regression slope' },
  { key: 'price_vs_rrp', label: 'Price vs RRP', desc: 'Current BrickLink price relative to RRP' },
  { key: 'lifecycle_position', label: 'Lifecycle', desc: 'Position in retirement J-curve' },
  { key: 'stock_level', label: 'Stock Level', desc: 'Current inventory scarcity' },
  { key: 'collector_premium', label: 'Collector Premium', desc: 'Price spread health (bid-ask)' },
  { key: 'theme_growth', label: 'Theme Growth', desc: 'Historical annual theme appreciation rate' },
  { key: 'value_opportunity', label: 'Value Opportunity', desc: 'Buy-the-dip: price below trailing average' },
  { key: 'price_wall', label: 'Price Wall', desc: 'Inventory clustering above/below average price' },
  { key: 'listing_ratio', label: 'Listing Ratio', desc: 'Months of inventory vs transaction velocity' },
  { key: 'new_used_spread', label: 'New-Used Spread', desc: 'Used-to-new price ratio and trend' },
] as const;

const MODIFIERS = [
  { key: 'mod_shelf_life', label: 'Shelf Life', desc: 'Shorter production = rarer' },
  { key: 'mod_subtheme', label: 'Subtheme', desc: 'Premium subtheme boost (UCS, Modular, etc.)' },
  { key: 'mod_niche', label: 'Niche', desc: 'Niche theme penalty' },
] as const;

function scoreColor(score: number | null): string {
  if (score === null) return 'text-muted-foreground';
  if (score >= 80) return 'text-emerald-400';
  if (score >= 65) return 'text-emerald-600 dark:text-emerald-500';
  if (score >= 50) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= 35) return 'text-orange-500';
  return 'text-red-500';
}

function scoreBg(score: number | null): string {
  if (score === null) return '';
  if (score >= 80) return 'bg-emerald-500/10';
  if (score >= 65) return 'bg-emerald-500/5';
  if (score >= 50) return 'bg-yellow-500/5';
  if (score >= 35) return 'bg-orange-500/5';
  return 'bg-red-500/10';
}

function ScoreBar({ value }: { value: number | null }) {
  if (value === null) return null;
  return (
    <div className="bg-muted h-1.5 w-full rounded-full">
      <div
        className={`h-1.5 rounded-full transition-all ${
          value >= 80
            ? 'bg-emerald-500'
            : value >= 65
              ? 'bg-emerald-600'
              : value >= 50
                ? 'bg-yellow-500'
                : value >= 35
                  ? 'bg-orange-500'
                  : 'bg-red-500'
        }`}
        style={{ width: `${Math.min(100, value)}%` }}
      />
    </div>
  );
}

const COHORT_LABELS: Record<string, { label: string; desc: string }> = {
  half_year: { label: 'Half-Year', desc: 'vs same release window' },
  year: { label: 'Year', desc: 'vs same release year' },
  theme: { label: 'Theme', desc: 'vs all sets in theme' },
  year_theme: { label: 'Year + Theme', desc: 'vs same theme & year' },
  price_tier: { label: 'Price Tier', desc: 'vs similar price range' },
  piece_group: { label: 'Piece Group', desc: 'vs similar complexity' },
};

function CohortSection({
  cohorts,
}: {
  cohorts: Record<string, CohortRank>;
}) {
  const entries = Object.entries(cohorts).filter(
    ([key]) => key in COHORT_LABELS
  );
  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border">
      <div className="bg-muted/50 border-b px-4 py-2">
        <span className="text-xs font-medium">Cohort Rankings</span>
        <span className="text-muted-foreground ml-2 text-xs">
          Percentile rank within peer group
        </span>
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b">
            <th className="px-4 py-1.5 text-left text-xs font-medium">
              Cohort
            </th>
            <th className="px-4 py-1.5 text-left text-xs font-medium">
              Bucket
            </th>
            <th className="w-16 px-4 py-1.5 text-right text-xs font-medium">
              Rank
            </th>
            <th className="w-20 px-4 py-1.5 text-right text-xs font-medium">
              Overall
            </th>
            <th className="w-20 px-4 py-1.5 text-right text-xs font-medium">
              Demand
            </th>
            <th className="w-20 px-4 py-1.5 text-right text-xs font-medium">
              Price
            </th>
            <th className="w-24 px-4 py-1.5 text-xs font-medium">Level</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([strategy, cohort]) => {
            const meta = COHORT_LABELS[strategy];
            return (
              <tr key={strategy} className="border-b last:border-b-0">
                <td className="px-4 py-2 text-sm font-medium">
                  {meta.label}
                  <span className="text-muted-foreground ml-1 text-xs">
                    {meta.desc}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className="bg-muted rounded px-1.5 py-0.5 font-mono text-xs">
                    {cohort.key}
                  </span>
                  <span className="text-muted-foreground ml-1 text-xs">
                    ({cohort.size} sets)
                  </span>
                </td>
                <td className="px-4 py-2 text-right font-mono text-sm">
                  {cohort.rank != null ? (
                    <span className={scoreColor(cohort.composite_pct)}>
                      #{cohort.rank}
                    </span>
                  ) : (
                    '--'
                  )}
                </td>
                <td className="px-4 py-2 text-right">
                  <PctBadge value={cohort.composite_pct} />
                </td>
                <td className="px-4 py-2 text-right">
                  <PctBadge value={cohort.demand_pct} />
                </td>
                <td className="px-4 py-2 text-right">
                  <PctBadge value={cohort.price_perf_pct} />
                </td>
                <td className="px-4 py-2">
                  <ScoreBar value={cohort.composite_pct} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PctBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground text-xs">--</span>;
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${scoreColor(value)} ${scoreBg(value)}`}
    >
      P{value.toFixed(0)}
    </span>
  );
}

interface SignalsPanelProps {
  setNumber: string;
}

export function SignalsPanel({ setNumber }: SignalsPanelProps) {
  const [data, setData] = useState<ItemSignals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/items/${setNumber}/signals`, { signal: controller.signal })
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        } else {
          setError(json.error ?? 'Failed to load signals');
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber]);

  if (loading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <p className="text-muted-foreground text-sm">Computing signals...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-32 items-center justify-center">
        <p className="text-destructive text-sm">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <p className="text-muted-foreground text-sm">
          No signal data. Needs at least 3 months of BrickLink sales history.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header with composite score */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Trading Signals</h2>
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground text-xs">
            As of {data.eval_year}-{String(data.eval_month).padStart(2, '0')}
          </span>
          <div
            className={`rounded-lg px-3 py-1.5 ${scoreBg(data.composite_score)}`}
          >
            <span className="text-muted-foreground text-xs">Composite </span>
            <span
              className={`font-mono text-lg font-bold ${scoreColor(data.composite_score)}`}
            >
              {data.composite_score !== null
                ? data.composite_score.toFixed(1)
                : '--'}
            </span>
            <span className="text-muted-foreground text-xs"> / 100</span>
          </div>
        </div>
      </div>

      {/* Signals grid */}
      <div className="rounded-lg border">
        <table className="w-full">
          <thead>
            <tr className="bg-muted/50 border-b">
              <th className="px-4 py-2 text-left text-xs font-medium">
                Signal
              </th>
              <th className="w-20 px-4 py-2 text-right text-xs font-medium">
                Score
              </th>
              <th className="w-32 px-4 py-2 text-xs font-medium">Level</th>
              <th className="px-4 py-2 text-left text-xs font-medium">
                Description
              </th>
            </tr>
          </thead>
          <tbody>
            {SIGNALS.map(({ key, label, desc }) => {
              const value = data[key as keyof ItemSignals] as number | null;
              return (
                <tr key={key} className="border-b last:border-b-0">
                  <td className="px-4 py-2.5 text-sm font-medium">{label}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span
                      className={`rounded px-2 py-0.5 font-mono text-sm font-semibold ${scoreColor(value)} ${scoreBg(value)}`}
                    >
                      {value != null ? value.toFixed(0) : '--'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <ScoreBar value={value} />
                  </td>
                  <td className="text-muted-foreground px-4 py-2.5 text-xs">
                    {desc}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Modifiers */}
      <div className="rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2">
          <span className="text-xs font-medium">Modifiers</span>
        </div>
        <div className="grid grid-cols-3 divide-x">
          {MODIFIERS.map(({ key, label, desc }) => {
            const value = data[key as keyof ItemSignals] as number | null;
            const numValue = value ?? 1.0;
            const color =
              numValue > 1.05
                ? 'text-emerald-400'
                : numValue < 0.95
                  ? 'text-red-400'
                  : 'text-muted-foreground';
            return (
              <div key={key} className="px-4 py-3">
                <div className="text-muted-foreground text-xs">{label}</div>
                <div className={`font-mono text-lg font-semibold ${color}`}>
                  {numValue.toFixed(2)}x
                </div>
                <div className="text-muted-foreground mt-0.5 text-xs">
                  {desc}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Cohort Rankings */}
      {data.cohorts && Object.keys(data.cohorts).length > 0 && (
        <CohortSection cohorts={data.cohorts} />
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs">
        <span className="text-muted-foreground">Score ranges:</span>
        <span className="text-emerald-400">80+ Strong</span>
        <span className="text-emerald-600 dark:text-emerald-500">
          65-79 Good
        </span>
        <span className="text-yellow-600 dark:text-yellow-400">
          50-64 Neutral
        </span>
        <span className="text-orange-500">35-49 Weak</span>
        <span className="text-red-500">&lt;35 Poor</span>
      </div>
    </div>
  );
}

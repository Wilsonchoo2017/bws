'use client';

import { useEffect, useState } from 'react';

interface MLPrediction {
  ml_growth_pct: number | null;
  ml_confidence: string | null;
  ml_tier: number | null;
}

interface GrowthPrediction {
  set_number: string;
  growth_pct: number;
  confidence: string;
  tier: number;
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
  return tier === 2 ? 'Tier 2 (Intrinsics + Keepa)' : 'Tier 1 (Intrinsics)';
}

interface MLPredictionPanelProps {
  setNumber: string;
}

export function MLPredictionPanel({ setNumber }: MLPredictionPanelProps) {
  const [prediction, setPrediction] = useState<GrowthPrediction | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/ml/growth/predictions/${setNumber}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.growth_pct != null) {
          setPrediction(json);
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
        <p className="mt-2 text-sm text-muted-foreground">
          No ML prediction available for this set.
        </p>
      </div>
    );
  }

  const { growth_pct, confidence, tier } = prediction;
  const badge = confidenceBadge(confidence);

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
    </div>
  );
}

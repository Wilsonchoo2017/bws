'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { KellyHorizon, KellySizing } from './types';

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function signedPct(value: number): string {
  const prefix = value >= 0 ? '+' : '';
  return `${prefix}${(value * 100).toFixed(1)}%`;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function confidenceColor(confidence: string): string {
  switch (confidence) {
    case 'high':
      return 'text-emerald-400 bg-emerald-500/10';
    case 'moderate':
      return 'text-yellow-600 dark:text-yellow-400 bg-yellow-500/10';
    case 'low':
      return 'text-orange-500 bg-orange-500/10';
    default:
      return 'text-muted-foreground bg-muted';
  }
}

function kellyColor(halfKelly: number): string {
  if (halfKelly >= 0.15) return 'text-emerald-400';
  if (halfKelly >= 0.08) return 'text-emerald-600 dark:text-emerald-500';
  if (halfKelly >= 0.03) return 'text-yellow-600 dark:text-yellow-400';
  if (halfKelly > 0) return 'text-orange-500';
  return 'text-muted-foreground';
}

function HorizonColumn({ data, label }: { data: KellyHorizon; label: string }) {
  return (
    <div className="flex-1 space-y-2 px-4 py-3">
      <div className="text-sm font-medium">{label}</div>
      <div className="text-muted-foreground text-xs">
        {data.horizon.replace('_', ' ')}
      </div>
      <div className="space-y-1.5">
        <Row label="Win Rate" value={pct(data.win_rate)} highlight={data.win_rate >= 0.6} />
        <Row label="Avg Win" value={signedPct(data.avg_win)} positive />
        <Row label="Avg Loss" value={signedPct(-data.avg_loss)} negative />
        <Row label="Expected" value={signedPct(data.mean_return)} highlight={data.mean_return > 0} />
        <div className="border-t pt-1.5">
          <Row label="Kelly f*" value={pct(data.kelly_fraction)} />
          <div className="mt-1 flex items-center justify-between">
            <span className="text-muted-foreground text-xs">Half-Kelly</span>
            <span className={`font-mono text-sm font-bold ${kellyColor(data.half_kelly)}`}>
              {pct(data.half_kelly)}
            </span>
          </div>
        </div>
        <div className="text-muted-foreground border-t pt-1.5 text-xs">
          {data.sample_count} samples
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  positive,
  negative,
  highlight,
}: {
  label: string;
  value: string;
  positive?: boolean;
  negative?: boolean;
  highlight?: boolean;
}) {
  const color = highlight
    ? 'text-emerald-400'
    : negative
      ? 'text-red-500'
      : positive
        ? 'text-emerald-500'
        : 'text-foreground';

  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className={`font-mono text-xs ${color}`}>{value}</span>
    </div>
  );
}

function readLocalStorage(key: string): string {
  try {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(key) || '';
    }
  } catch {
    // localStorage unavailable (private browsing, quota exceeded)
  }
  return '';
}

function writeLocalStorage(key: string, value: string): void {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(key, value);
    }
  } catch {
    // silently degrade
  }
}

interface KellyPanelProps {
  setNumber: string;
}

export function KellyPanel({ setNumber }: KellyPanelProps) {
  const [data, setData] = useState<KellySizing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [budget, setBudget] = useState<string>(() =>
    readLocalStorage('bws_kelly_budget')
  );

  const parsed = parseFloat(budget);
  const budgetCents = !isNaN(parsed) && parsed > 0
    ? Math.round(parsed * 100)
    : null;
  const debouncedBudgetCents = useDebounce(budgetCents, 500);

  const fetchKelly = useCallback(() => {
    const controller = new AbortController();
    setLoading(true);
    const query = debouncedBudgetCents ? `?budget=${debouncedBudgetCents}` : '';
    fetch(`/api/items/${setNumber}/kelly${query}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text();
          try {
            const json = JSON.parse(text);
            throw new Error(json.error ?? `HTTP ${res.status}`);
          } catch (e) {
            if (e instanceof Error && e.message !== `HTTP ${res.status}`) throw e;
            throw new Error(`HTTP ${res.status}`);
          }
        }
        return res.json();
      })
      .then((json) => {
        if (json.success) {
          setData(json.data);
        } else {
          setError(json.error ?? 'Failed to load Kelly sizing');
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber, debouncedBudgetCents]);

  useEffect(() => {
    return fetchKelly();
  }, [fetchKelly]);

  const handleBudgetChange = (value: string) => {
    setBudget(value);
    writeLocalStorage('bws_kelly_budget', value);
  };

  if (loading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <p className="text-muted-foreground text-sm">
          Computing position sizing...
        </p>
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
          No backtest data available for position sizing.
        </p>
      </div>
    );
  }

  const allocAmount =
    budgetCents && data.recommended_pct > 0
      ? (budgetCents * data.recommended_pct) / 100
      : null;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Position Sizing</h2>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-md px-2 py-1 text-xs font-medium ${confidenceColor(data.confidence)}`}
          >
            {data.confidence} confidence
          </span>
          <span className="text-muted-foreground text-xs">
            {data.score_bin}
          </span>
        </div>
      </div>

      {/* Flip vs Hold comparison */}
      {data.flip || data.hold ? (
        <div className="rounded-lg border">
          <div className="bg-muted/50 border-b px-4 py-2">
            <span className="text-xs font-medium">
              Kelly Criterion Analysis
            </span>
          </div>
          <div className="flex divide-x">
            {data.flip ? (
              <HorizonColumn data={data.flip} label="Flip" />
            ) : (
              <div className="flex flex-1 items-center justify-center px-4 py-6">
                <span className="text-muted-foreground text-xs">
                  No flip data
                </span>
              </div>
            )}
            {data.hold ? (
              <HorizonColumn data={data.hold} label="Hold" />
            ) : (
              <div className="flex flex-1 items-center justify-center px-4 py-6">
                <span className="text-muted-foreground text-xs">
                  No hold data
                </span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex h-20 items-center justify-center rounded-lg border">
          <span className="text-muted-foreground text-sm">
            Insufficient backtest data for this score range
          </span>
        </div>
      )}

      {/* Recommendation + budget */}
      <div className="rounded-lg border px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-muted-foreground text-xs">
              Recommended allocation
            </span>
            <div
              className={`font-mono text-2xl font-bold ${kellyColor(data.recommended_pct)}`}
            >
              {pct(data.recommended_pct)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground text-xs">Budget RM</span>
            <input
              type="number"
              min={0}
              step={100}
              value={budget}
              onChange={(e) => handleBudgetChange(e.target.value)}
              placeholder="5000"
              className="bg-background w-24 rounded border px-2 py-1.5 font-mono text-sm"
            />
            {allocAmount !== null && (
              <span className="font-mono text-sm font-semibold">
                = RM{(allocAmount / 100).toFixed(0)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Warnings / notes */}
      {data.warnings.length > 0 && (
        <div className="text-muted-foreground space-y-0.5 text-xs">
          {data.warnings.map((w, i) => (
            <div key={i}>* {w}</div>
          ))}
          <div>* Half-Kelly applied for estimation safety</div>
        </div>
      )}
    </div>
  );
}

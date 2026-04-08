'use client';

import { useEffect, useState } from 'react';

interface LiquidityMetric {
  value: number;
  pct: number;
  label: string;
  detail?: string;
}

interface LiquidityMonth {
  label: string;
  txns: number;
}

interface LiquidityData {
  set_number: string;
  source: string;
  total_months: number;
  months_with_sales: number;
  consistency: number;
  total_txns: number;
  total_qty: number | null;
  avg_monthly_txns: number;
  avg_monthly_qty: number | null;
  recent_avg_txns: number;
  trend_ratio: number | null;
  listing_ratio?: number;
  listing_lots?: number;
  listing_qty?: number;
  metrics: Record<string, LiquidityMetric>;
  composite_pct: number;
  rank: number | null;
  size: number;
  monthly: LiquidityMonth[];
}

// Match cohort panel color functions
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

function PctBadge({ value }: { value: number }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${scoreColor(value)} ${scoreBg(value)}`}
    >
      P{value.toFixed(0)}
    </span>
  );
}

function formatMetricValue(key: string, metric: LiquidityMetric): string {
  if (key === 'consistency') return `${(metric.value * 100).toFixed(0)}%`;
  if (key === 'trend') return `${metric.value >= 1 ? '+' : ''}${((metric.value - 1) * 100).toFixed(0)}%`;
  if (key === 'listing_ratio') return `${metric.value.toFixed(1)}x`;
  return metric.value?.toFixed(1) ?? '--';
}

function MetricDesc({ metricKey, data }: { metricKey: string; data: LiquidityData }) {
  if (metricKey === 'volume')
    return <>{data.total_txns} total over {data.total_months} months</>;
  if (metricKey === 'quantity')
    return <>{data.total_qty} total units sold</>;
  if (metricKey === 'consistency')
    return <>{data.months_with_sales}/{data.total_months} months with sales</>;
  if (metricKey === 'trend') return <>last 6 months vs prior</>;
  if (metricKey === 'listing_ratio') {
    const m = data.metrics.listing_ratio;
    return <>{m?.detail ?? 'current lots / recent sales'}</>;
  }
  return null;
}

function BarChart({ data, height = 32 }: { data: number[]; height?: number }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const barWidth = Math.max(2, Math.min(5, 160 / data.length));
  const gap = 1;
  const width = data.length * (barWidth + gap);

  return (
    <svg width={width} height={height} className="inline-block">
      {data.map((v, i) => {
        const barH = Math.max(1, (v / max) * (height - 2));
        return (
          <rect
            key={i}
            x={i * (barWidth + gap)}
            y={height - barH}
            width={barWidth}
            height={barH}
            className={v > 0 ? 'fill-blue-500 dark:fill-blue-400' : 'fill-muted'}
            rx={1}
          />
        );
      })}
    </svg>
  );
}

const METRIC_ORDER = ['volume', 'quantity', 'consistency', 'trend', 'listing_ratio'];

function LiquiditySource({
  label,
  data,
}: {
  label: string;
  data: LiquidityData | null | undefined;
  loading: boolean;
}) {
  if (data === null || data === undefined) {
    return (
      <div className="flex-1 rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2">
          <span className="text-xs font-medium">{label}</span>
        </div>
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-muted-foreground">No data available.</p>
        </div>
      </div>
    );
  }

  const metricEntries = METRIC_ORDER
    .filter((key) => key in data.metrics)
    .map((key) => ({ key, metric: data.metrics[key] }));

  const txnBars = data.monthly.map((m) => m.txns);

  return (
    <div className="flex-1 rounded-lg border">
      {/* Header */}
      <div className="bg-muted/50 border-b px-4 py-2">
        <span className="text-xs font-medium">{label}</span>
        <span className="text-muted-foreground ml-2 text-xs">
          {data.total_months} months of data
        </span>
      </div>

      {/* Overall composite row */}
      <div className="flex items-center justify-between border-b px-4 py-1.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium">Overall</span>
          <span className="text-muted-foreground text-xs">
            vol 50% + consistency 30% + trend 20%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <PctBadge value={data.composite_pct} />
          {data.rank != null && (
            <span
              className={`rounded px-1.5 py-0.5 text-xs font-semibold ${scoreColor(data.composite_pct)} ${scoreBg(data.composite_pct)}`}
            >
              #{data.rank}/{data.size}
            </span>
          )}
        </div>
      </div>

      {/* Individual metric rows */}
      <div className="divide-y">
        {metricEntries.map(({ key, metric }) => (
          <div key={key} className="flex items-center justify-between px-4 py-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium">{metric.label}</span>
              <span className="text-muted-foreground text-xs">
                <MetricDesc metricKey={key} data={data} />
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`font-mono text-xs ${scoreColor(metric.pct)}`}>
                {formatMetricValue(key, metric)}
              </span>
              <PctBadge value={metric.pct} />
            </div>
          </div>
        ))}
      </div>

      {/* Sales trend bar chart */}
      {txnBars.length >= 3 && (
        <div className="flex items-center gap-2 border-t px-4 py-2">
          <span className="text-muted-foreground shrink-0 text-xs">Trend:</span>
          <BarChart data={txnBars} />
        </div>
      )}
    </div>
  );
}

interface LiquidityPanelProps {
  setNumber: string;
}

export function LiquidityPanel({ setNumber }: LiquidityPanelProps) {
  const [bl, setBl] = useState<LiquidityData | null | undefined>(undefined);
  const [be, setBe] = useState<LiquidityData | null | undefined>(undefined);
  const [blLoading, setBlLoading] = useState(true);
  const [beLoading, setBeLoading] = useState(true);

  useEffect(() => {
    const controllers: AbortController[] = [];

    // Fetch BrickLink
    const blCtrl = new AbortController();
    controllers.push(blCtrl);
    fetch(`/api/items/${setNumber}/liquidity?source=bricklink`, { signal: blCtrl.signal })
      .then((res) => res.json())
      .then((json) => setBl(json.success ? json.data : null))
      .catch((err) => { if (err.name !== 'AbortError') setBl(null); })
      .finally(() => setBlLoading(false));

    // Fetch BrickEconomy
    const beCtrl = new AbortController();
    controllers.push(beCtrl);
    fetch(`/api/items/${setNumber}/liquidity?source=brickeconomy`, { signal: beCtrl.signal })
      .then((res) => res.json())
      .then((json) => setBe(json.success ? json.data : null))
      .catch((err) => { if (err.name !== 'AbortError') setBe(null); })
      .finally(() => setBeLoading(false));

    return () => controllers.forEach((c) => c.abort());
  }, [setNumber]);

  const bothEmpty = !blLoading && !beLoading && bl == null && be == null;

  if (blLoading && beLoading) {
    return (
      <div className="rounded-lg border border-border p-4">
        <span className="text-xs font-medium">Liquidity</span>
        <p className="mt-1 text-xs text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (bothEmpty) {
    return (
      <div className="rounded-lg border border-border p-4">
        <span className="text-xs font-medium">Liquidity</span>
        <p className="mt-1 text-xs text-muted-foreground">
          No sales data available from either source.
        </p>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <LiquiditySource label="BrickLink" data={bl} loading={blLoading} />
      <LiquiditySource label="BrickEconomy" data={be} loading={beLoading} />
    </div>
  );
}

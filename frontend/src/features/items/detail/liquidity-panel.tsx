'use client';

import { useEffect, useState } from 'react';
import { scoreColor, scoreBg, formatMetricValue as fmtMetric, getLiquidityWeight } from '../percentile-utils';
import { useDetailBundle } from './detail-bundle-context';

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


function PctBadge({ value, weight }: { value: number; weight?: number }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${scoreColor(value, weight)} ${scoreBg(value, weight)}`}
    >
      P{value.toFixed(0)}
    </span>
  );
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
            vol 50% + consistency 38% + listing ratio 12%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <PctBadge value={data.composite_pct} />
          {data.size > 0 && (
            <span className="text-muted-foreground text-xs">n={data.size}</span>
          )}
        </div>
      </div>

      {/* Individual metric rows */}
      <div className="divide-y">
        {metricEntries.map(({ key, metric }) => {
          const w = getLiquidityWeight(key);
          return (
            <div key={key} className="flex items-center justify-between px-4 py-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium">{metric.label}</span>
                <span className="text-muted-foreground text-xs">
                  <MetricDesc metricKey={key} data={data} />
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs ${scoreColor(metric.pct, w)}`}>
                  {fmtMetric(key, metric.value)}
                </span>
                <PctBadge value={metric.pct} weight={w} />
              </div>
            </div>
          );
        })}
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

interface LiquidityCohort {
  key: string;
  size: number;
  rank: number | null;
  volume_pct: number | null;
  consistency_pct: number | null;
  trend_pct: number | null;
  listing_ratio_pct: number | null;
  composite_pct: number | null;
}

const COHORT_LABELS: Record<string, { label: string; desc: string }> = {
  half_year: { label: 'Half-Year', desc: 'vs sets released same half' },
  year: { label: 'Year', desc: 'vs sets released same year' },
  theme: { label: 'Theme', desc: 'vs all sets in same theme' },
  year_theme: { label: 'Year + Theme', desc: 'vs same theme & year' },
  price_tier: { label: 'Price Tier', desc: 'vs similarly priced sets' },
  piece_group: { label: 'Piece Group', desc: 'vs similar piece count' },
};

const LIQ_PCT_FIELDS: { key: keyof LiquidityCohort; label: string; liqKey: string }[] = [
  { key: 'composite_pct', label: 'Overall', liqKey: '' },
  { key: 'volume_pct', label: 'Volume', liqKey: 'volume' },
  { key: 'consistency_pct', label: 'Consistency', liqKey: 'consistency' },
  { key: 'trend_pct', label: 'Trend', liqKey: 'trend' },
  { key: 'listing_ratio_pct', label: 'Listing', liqKey: 'listing_ratio' },
];

function LiquidityCohortGrid({ cohorts }: { cohorts: Record<string, LiquidityCohort> }) {
  const entries = Object.entries(cohorts).filter(([key]) => key in COHORT_LABELS);
  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border">
      <div className="bg-muted/50 border-b px-4 py-2 flex items-center justify-between">
        <div>
          <span className="text-xs font-medium mr-2">Liquidity</span>
          <span className="text-muted-foreground text-xs">
            percentile vs peer group (higher = better)
          </span>
        </div>
      </div>
      <div className="divide-y">
        {entries.map(([strategy, cohort]) => {
          const meta = COHORT_LABELS[strategy];
          const overall = cohort.composite_pct ?? null;
          return (
            <div key={strategy} className="px-4 py-2">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{meta.label}</span>
                  <span className="text-muted-foreground text-xs">{meta.desc}</span>
                  <span className="text-muted-foreground text-xs">
                    ({cohort.key})
                  </span>
                </div>
                {overall != null && (
                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${scoreColor(overall)} ${scoreBg(overall)}`}>
                    P{Math.round(overall)}
                    <span className="text-muted-foreground ml-1 font-normal">n={cohort.size}</span>
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                {LIQ_PCT_FIELDS.map(({ key, label, liqKey }) => {
                  const value = cohort[key];
                  const numVal = typeof value === 'number' ? value : null;
                  const w = liqKey ? getLiquidityWeight(liqKey) : undefined;
                  return (
                    <span
                      key={key}
                      className="inline-flex items-center gap-1"
                      title={label}
                    >
                      <span className="text-muted-foreground text-xs">{label}</span>
                      <span className={`font-mono text-xs font-semibold ${scoreColor(numVal, w)}`}>
                        {numVal !== null ? `P${numVal.toFixed(0)}` : '--'}
                      </span>
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface LiquidityPanelProps {
  setNumber: string;
}

export function LiquidityPanel({ setNumber }: LiquidityPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [bl, setBl] = useState<LiquidityData | null | undefined>(undefined);
  const [be, setBe] = useState<LiquidityData | null | undefined>(undefined);
  const [blLoading, setBlLoading] = useState(true);
  const [beLoading, setBeLoading] = useState(true);
  const [cohorts, setCohorts] = useState<Record<string, LiquidityCohort> | null>(null);

  useEffect(() => {
    if (bundleLoading) return;

    // Use bundle data if present (non-null means cache was warm)
    if (bundle?.liquidity_bricklink) {
      setBl(bundle.liquidity_bricklink as unknown as LiquidityData);
      setBlLoading(false);
    }
    if (bundle?.liquidity_brickeconomy) {
      setBe(bundle.liquidity_brickeconomy as unknown as LiquidityData);
      setBeLoading(false);
    }
    if (bundle?.liquidity_cohorts) {
      setCohorts(bundle.liquidity_cohorts as Record<string, LiquidityCohort>);
    }
    // If both came from bundle, done
    if (bundle?.liquidity_bricklink && bundle?.liquidity_brickeconomy) return;

    // Fetch individually for any missing data
    const controllers: AbortController[] = [];

    if (!bundle?.liquidity_bricklink) {
      const blCtrl = new AbortController();
      controllers.push(blCtrl);
      fetch(`/api/items/${setNumber}/liquidity?source=bricklink`, { signal: blCtrl.signal })
        .then((res) => res.json())
        .then((json) => setBl(json.success ? json.data : null))
        .catch((err) => { if (err.name !== 'AbortError') setBl(null); })
        .finally(() => setBlLoading(false));
    }

    if (!bundle?.liquidity_brickeconomy) {
      const beCtrl = new AbortController();
      controllers.push(beCtrl);
      fetch(`/api/items/${setNumber}/liquidity?source=brickeconomy`, { signal: beCtrl.signal })
        .then((res) => res.json())
        .then((json) => setBe(json.success ? json.data : null))
        .catch((err) => { if (err.name !== 'AbortError') setBe(null); })
        .finally(() => setBeLoading(false));
    }

    if (!bundle?.liquidity_cohorts) {
      const cohortCtrl = new AbortController();
      controllers.push(cohortCtrl);
      fetch(`/api/items/${setNumber}/liquidity/cohorts`, { signal: cohortCtrl.signal })
        .then((res) => res.json())
        .then((json) => {
          if (json.success && json.data) { setCohorts(json.data); }
        })
        .catch(() => {});
    }

    return () => controllers.forEach((c) => c.abort());
  }, [setNumber, bundle, bundleLoading]);

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
    <div className="flex flex-col gap-4">
      <div className="flex gap-4">
        <LiquiditySource label="BrickLink" data={bl} loading={blLoading} />
        <LiquiditySource label="BrickEconomy" data={be} loading={beLoading} />
      </div>
      {cohorts && Object.keys(cohorts).length > 0 && (
        <LiquidityCohortGrid cohorts={cohorts} />
      )}
    </div>
  );
}

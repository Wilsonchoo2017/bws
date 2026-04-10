'use client';

import { ExternalLinkIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { BrickeconomyData } from '../types';
import { useDetailBundle } from './detail-bundle-context';
import type { ChartDateRange } from './item-detail';

interface BrickeconomyPanelProps {
  setNumber: string;
  globalDateRange?: ChartDateRange | null;
  onDateRange?: (range: ChartDateRange) => void;
}

type ChartTab = 'value' | 'sales' | 'candlestick';

function formatUsd(cents: number | null): string {
  if (cents === null) return '-';
  return `$${(cents / 100).toFixed(2)}`;
}

function parseJson<T>(raw: T | string | null): T | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return raw;
}

// ---------------------------------------------------------------------------
// Rolling average with band (like BrickEconomy's trendline)
// ---------------------------------------------------------------------------

interface ValuePoint {
  ts: number;
  date: string;
  value: number;
}

interface TrendPoint {
  date: string;
  label: string;
  trend: number;
  upper: number;
  lower: number;
}

function computeTrend(
  points: ValuePoint[],
  windowDays: number = 30
): TrendPoint[] {
  if (points.length === 0) return [];

  const sorted = [...points].sort((a, b) => a.ts - b.ts);
  const windowMs = windowDays * 86_400_000;

  // Sample at regular intervals to keep chart data manageable
  const firstTs = sorted[0].ts;
  const lastTs = sorted[sorted.length - 1].ts;
  const totalDays = (lastTs - firstTs) / 86_400_000;
  const stepDays = Math.max(7, Math.floor(totalDays / 120));
  const stepMs = stepDays * 86_400_000;

  const result: TrendPoint[] = [];

  for (let ts = firstTs; ts <= lastTs; ts += stepMs) {
    const windowStart = ts - windowMs;
    const windowEnd = ts + windowMs;
    const inWindow = sorted.filter(
      (p) => p.ts >= windowStart && p.ts <= windowEnd
    );
    if (inWindow.length < 2) continue;

    const values = inWindow.map((p) => p.value);
    const mean = values.reduce((s, v) => s + v, 0) / values.length;
    const variance =
      values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
    const stddev = Math.sqrt(variance);

    const d = new Date(ts);
    result.push({
      date: d.toISOString().slice(0, 10),
      label: d.toLocaleDateString('en-US', {
        month: 'short',
        year: '2-digit',
      }),
      trend: mean,
      upper: mean + stddev,
      lower: Math.max(0, mean - stddev),
    });
  }

  return result;
}

// ---------------------------------------------------------------------------
// Data builders
// ---------------------------------------------------------------------------

function buildValueData(data: BrickeconomyData) {
  const chart = parseJson(data.value_chart_json) as
    | [string, number][]
    | null;
  if (!chart || chart.length === 0) return { points: [], trend: [] };

  const points: ValuePoint[] = chart.map(([date, cents]) => ({
    ts: new Date(date).getTime(),
    date,
    value: cents / 100,
  }));

  const trend = computeTrend(points);

  return { points, trend };
}

function buildSalesTrend(data: BrickeconomyData) {
  const trend = parseJson(data.sales_trend_json) as
    | [string, number][]
    | null;
  if (!trend) return [];
  return trend.map(([month, count]) => ({
    ts: new Date(month + '-15').getTime(),
    month,
    label: new Date(month + '-01').toLocaleDateString('en-US', {
      month: 'short',
      year: '2-digit',
    }),
    count,
  }));
}

function buildCandlestick(data: BrickeconomyData) {
  const candles = parseJson(data.candlestick_json) as
    | [string, number, number, number, number][]
    | null;
  if (!candles) return [];
  return candles.map(([month, low, open, close, high]) => ({
    ts: new Date(month + '-15').getTime(),
    month,
    label: new Date(month + '-01').toLocaleDateString('en-US', {
      month: 'short',
      year: '2-digit',
    }),
    low: low / 100,
    open: open / 100,
    close: close / 100,
    high: high / 100,
    base: low / 100,
    body: (close - open) / 100,
    range: (high - low) / 100,
  }));
}

// ---------------------------------------------------------------------------
// Tooltips
// ---------------------------------------------------------------------------

function ValueTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  // Find the scatter (sale) entry or the trend entry
  const sale = payload.find((p: any) => p.dataKey === 'sale');
  const trendEntry = payload.find((p: any) => p.dataKey === 'trend');

  if (sale?.value != null) {
    const d = sale.payload;
    const dateStr = d?.date
      ? new Date(d.date).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        })
      : new Date(d?.ts).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        });
    return (
      <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
        <p className='font-medium'>{dateStr}</p>
        <p className='text-blue-600 font-semibold'>${sale.value.toFixed(2)}</p>
      </div>
    );
  }

  if (trendEntry?.value != null) {
    const d = trendEntry.payload;
    return (
      <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
        <p className='font-medium'>{d?.label ?? ''}</p>
        <p className='text-blue-600'>Trend: ${trendEntry.value.toFixed(2)}</p>
      </div>
    );
  }

  return null;
}

function SalesTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

function CandlestickTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      <p>Open: ${d.open?.toFixed(2)}</p>
      <p>Close: ${d.close?.toFixed(2)}</p>
      <p>High: ${d.high?.toFixed(2)}</p>
      <p>Low: ${d.low?.toFixed(2)}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

function SummaryCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className='rounded-lg border bg-white p-3 dark:bg-zinc-900'>
      <p className='text-muted-foreground text-xs'>{label}</p>
      <p className={`text-lg font-semibold ${color ?? ''}`}>{value}</p>
      {sub && <p className='text-muted-foreground text-xs'>{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Value scatter chart with trendline band
// ---------------------------------------------------------------------------

function ValueScatterChart({
  points,
  trend,
  globalDateRange,
}: {
  points: ValuePoint[];
  trend: TrendPoint[];
  globalDateRange?: ChartDateRange | null;
}) {
  // Merge all data into a single timeline for ComposedChart.
  // Trend points have trend/upper/lower; scatter points have sale value.
  // We combine them into one sorted array so the X axis covers everything.
  const merged: {
    ts: number;
    date?: string;
    label?: string;
    trend?: number;
    upper?: number;
    lower?: number;
    band?: [number, number];
    sale?: number;
  }[] = [];

  for (const t of trend) {
    merged.push({
      ts: new Date(t.date).getTime(),
      label: t.label,
      trend: t.trend,
      upper: t.upper,
      lower: t.lower,
      band: [t.lower, t.upper],
    });
  }

  for (const p of points) {
    merged.push({
      ts: p.ts,
      date: p.date,
      sale: p.value,
    });
  }

  merged.sort((a, b) => a.ts - b.ts);

  // Separate datasets for Area/Line (trend only) and Scatter (sales only)
  const trendData = merged.filter((d) => d.band != null);
  const scatterData = merged.filter((d) => d.sale != null);

  // Y domain from all values
  const allValues = [
    ...points.map((p) => p.value),
    ...trend.map((t) => t.upper),
    ...trend.map((t) => t.lower),
  ];
  const yMin = Math.floor(Math.min(...allValues) * 0.9);
  const yMax = Math.ceil(Math.max(...allValues) * 1.05);

  const formatTick = (ts: number) =>
    new Date(ts).toLocaleDateString('en-US', {
      month: 'short',
      year: '2-digit',
    });

  // X domain: use global range if available, else span sale data
  const saleTimestamps = points.map((p) => p.ts);
  const xMin = globalDateRange ? globalDateRange.min : Math.min(...saleTimestamps);
  const xMax = globalDateRange ? globalDateRange.max : Math.max(...saleTimestamps);

  return (
    <ResponsiveContainer width='100%' height='100%' minWidth={0} minHeight={0}>
      <ComposedChart margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray='3 3' opacity={0.15} />
        <XAxis
          dataKey='ts'
          type='number'
          scale='time'
          domain={[xMin, xMax]}
          tick={{ fontSize: 11 }}
          tickFormatter={formatTick}
          allowDuplicatedCategory={false}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => `$${v}`}
          domain={[yMin, yMax]}
        />
        <Tooltip content={<ValueTooltip />} />

        {/* Trendline confidence band */}
        <Area
          data={trendData}
          dataKey='band'
          type='monotone'
          stroke='none'
          fill='#3b82f6'
          fillOpacity={0.12}
          isAnimationActive={false}
          legendType='none'
        />

        {/* Trend center line */}
        <Line
          data={trendData}
          dataKey='trend'
          type='monotone'
          stroke='#3b82f6'
          strokeWidth={2}
          strokeOpacity={0.5}
          dot={false}
          isAnimationActive={false}
          name='Trend'
        />

        {/* Individual sale dots */}
        <Scatter
          data={scatterData}
          dataKey='sale'
          name='Sale Price'
          isAnimationActive={false}
          shape={(props: any) => {
            const { cx, cy } = props;
            if (cx == null || cy == null) return null;
            return (
              <circle
                cx={cx}
                cy={cy}
                r={3.5}
                fill='#3b82f6'
                fillOpacity={0.5}
                stroke='#3b82f6'
                strokeOpacity={0.2}
                strokeWidth={1}
              />
            );
          }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function BrickeconomyPanel({ setNumber, globalDateRange, onDateRange }: BrickeconomyPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [data, setData] = useState<BrickeconomyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<ChartTab>('value');

  useEffect(() => {
    if (bundleLoading) return;
    if (bundle?.brickeconomy) {
      setData(bundle.brickeconomy as unknown as BrickeconomyData);
      setLoading(false);
      return;
    }
    // Fallback: fetch individually (bundle loaded without BE data, or no bundle)
    fetch(`/api/items/${setNumber}/brickeconomy`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data) {
          setData(json.data);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [setNumber, bundle, bundleLoading]);

  const { points: valuePoints, trend: valueTrend } = data
    ? buildValueData(data)
    : { points: [], trend: [] };
  const salesTrend = data ? buildSalesTrend(data) : [];
  const candlestick = data ? buildCandlestick(data) : [];

  // Report date range to parent for cross-chart sync
  useEffect(() => {
    if (onDateRange && valuePoints.length > 0) {
      const timestamps = valuePoints.map((p) => p.ts);
      onDateRange({
        min: Math.min(...timestamps),
        max: Math.max(...timestamps),
      });
    }
  }, [valuePoints.length]);

  if (loading) {
    return (
      <div className='flex h-64 items-center justify-center'>
        <p className='text-muted-foreground text-sm'>
          Loading BrickEconomy data...
        </p>
      </div>
    );
  }

  if (!data) return null;

  const tabs: { key: ChartTab; label: string; disabled: boolean }[] = [
    { key: 'value', label: 'Set Value', disabled: valuePoints.length === 0 },
    { key: 'sales', label: 'Sales Trend', disabled: salesTrend.length === 0 },
    {
      key: 'candlestick',
      label: 'Price Range',
      disabled: candlestick.length === 0,
    },
  ];

  return (
    <div>
      <div className='mb-3 flex items-center justify-between'>
        <h2 className='text-lg font-semibold'>BrickEconomy Data</h2>
        {data.brickeconomy_url && (
          <a
            href={data.brickeconomy_url}
            target='_blank'
            rel='noopener noreferrer'
            className='text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs'
          >
            View on BrickEconomy
            <ExternalLinkIcon className='h-3 w-3' />
          </a>
        )}
      </div>

      {/* Summary cards -- factual metadata only, no BE pricing/growth */}
      <div className='mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6'>
        <SummaryCard
          label='RRP (USD)'
          value={formatUsd(data.rrp_usd_cents)}
        />
        <SummaryCard
          label='Pieces'
          value={data.pieces !== null && data.pieces !== undefined ? `${data.pieces}` : '-'}
        />
        <SummaryCard
          label='Minifigs'
          value={data.minifigs !== null && data.minifigs !== undefined ? `${data.minifigs}` : '-'}
        />
        <SummaryCard
          label='Rating'
          value={data.rating_value ? `${data.rating_value}/5` : '-'}
          sub={
            data.review_count ? `${data.review_count} reviews` : undefined
          }
        />
        <SummaryCard
          label='Status'
          value={data.availability ?? '-'}
        />
        <SummaryCard
          label='Released'
          value={data.year_released ? `${data.year_released}` : '-'}
          sub={data.year_retired ? `Retired ${data.year_retired}` : undefined}
        />
      </div>

      {/* Tab navigation */}
      <div className='mb-4 flex gap-1'>
        {tabs.map((t) => (
          <button
            key={t.key}
            disabled={t.disabled}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'text-muted-foreground hover:bg-muted'
            } ${t.disabled ? 'cursor-not-allowed opacity-40' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Charts */}
      <div className='h-80 w-full'>
        {tab === 'value' && valuePoints.length > 0 && (
          <ValueScatterChart points={valuePoints} trend={valueTrend} globalDateRange={globalDateRange} />
        )}

        {tab === 'sales' && salesTrend.length > 0 && (
          <ResponsiveContainer
            width='100%'
            height='100%'
            minWidth={0}
            minHeight={0}
          >
            <BarChart data={salesTrend}>
              <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
              <XAxis
                dataKey='ts'
                type='number'
                scale='time'
                domain={globalDateRange ? [globalDateRange.min, globalDateRange.max] : ['dataMin', 'dataMax']}
                tick={{ fontSize: 11 }}
                tickFormatter={(ts) =>
                  new Date(ts).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
                }
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip content={<SalesTooltip />} />
              <Legend />
              <Bar
                dataKey='count'
                name='Sales Count'
                fill='#8b5cf6'
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}

        {tab === 'candlestick' && candlestick.length > 0 && (
          <ResponsiveContainer
            width='100%'
            height='100%'
            minWidth={0}
            minHeight={0}
          >
            <BarChart data={candlestick}>
              <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
              <XAxis
                dataKey='ts'
                type='number'
                scale='time'
                domain={globalDateRange ? [globalDateRange.min, globalDateRange.max] : ['dataMin', 'dataMax']}
                tick={{ fontSize: 11 }}
                tickFormatter={(ts) =>
                  new Date(ts).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
                }
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${v}`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CandlestickTooltip />} />
              <Legend />
              <Bar
                dataKey='low'
                name='Low'
                fill='transparent'
                stackId='candle'
              />
              <Bar
                dataKey='body'
                name='Open-Close'
                fill='#3b82f6'
                fillOpacity={0.6}
                stackId='candle'
                radius={[2, 2, 0, 0]}
              />
              <Bar
                dataKey='range'
                name='High-Low Range'
                fill='#93c5fd'
                fillOpacity={0.3}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Distribution stats */}
      {(data.distribution_mean_cents || data.distribution_stddev_cents) && (
        <p className='text-muted-foreground mt-3 text-xs'>
          Sale distribution: mean {formatUsd(data.distribution_mean_cents)},
          std dev {formatUsd(data.distribution_stddev_cents)}
          {data.scraped_at &&
            ` | Last scraped ${new Date(data.scraped_at).toLocaleDateString()}`}
        </p>
      )}
    </div>
  );
}

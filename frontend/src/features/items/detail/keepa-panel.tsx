'use client';

import { ExternalLinkIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { KeepaData } from '../types';

interface KeepaDataPanelProps {
  setNumber: string;
}

type ChartTab = 'all' | 'amazon' | 'new' | 'used';

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

// Color palette for each price series
const SERIES_COLORS: Record<string, string> = {
  amazon: '#f59e0b',      // amber
  new: '#ef4444',         // red
  new_3p_fba: '#ec4899',  // pink
  new_3p_fbm: '#3b82f6',  // blue
  buy_box: '#6b7280',     // gray
  used: '#1f2937',        // dark gray
  warehouse: '#8b5cf6',   // purple
  list_price: '#9ca3af',  // light gray
};

interface PricePoint {
  date: string;
  label: string;
  ts: number;
  amazon?: number;
  new?: number;
  new_3p_fba?: number;
  new_3p_fbm?: number;
  buy_box?: number;
  used?: number;
  warehouse?: number;
  list_price?: number;
}

function buildChartData(data: KeepaData): PricePoint[] {
  const seriesMap: Record<string, [string, number][]> = {};

  const sources: [string, string | [string, number][] | null][] = [
    ['amazon', data.amazon_price_json],
    ['new', data.new_price_json],
    ['new_3p_fba', data.new_3p_fba_json],
    ['new_3p_fbm', data.new_3p_fbm_json],
    ['buy_box', data.buy_box_json],
    ['used', data.used_price_json],
    ['warehouse', data.warehouse_deals_json],
    ['list_price', data.list_price_json],
  ];

  for (const [key, raw] of sources) {
    const parsed = parseJson(raw) as [string, number][] | null;
    if (parsed && parsed.length > 0) {
      seriesMap[key] = parsed;
    }
  }

  // Collect all unique dates across all series
  const dateMap = new Map<string, PricePoint>();

  for (const [key, points] of Object.entries(seriesMap)) {
    for (const [date, cents] of points) {
      if (!dateMap.has(date)) {
        const d = new Date(date);
        const isValidDate = !isNaN(d.getTime());
        dateMap.set(date, {
          date,
          label: isValidDate
            ? d.toLocaleDateString('en-US', {
                month: 'short',
                year: '2-digit',
              })
            : date,
          ts: isValidDate ? d.getTime() : 0,
        });
      }
      const point = dateMap.get(date)!;
      (point as Record<string, unknown>)[key] = cents / 100;
    }
  }

  // Sort by timestamp
  return Array.from(dateMap.values())
    .filter((p) => p.ts > 0)
    .sort((a, b) => a.ts - b.ts);
}

function KeepaTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900">
      <p className="mb-1 font-medium">{label}</p>
      {payload
        .filter((entry: any) => entry.value != null)
        .map((entry: any) => (
          <p key={entry.dataKey} style={{ color: entry.color }}>
            {entry.name}: ${entry.value.toFixed(2)}
          </p>
        ))}
    </div>
  );
}

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
    <div className="rounded-lg border bg-white p-3 dark:bg-zinc-900">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className={`text-lg font-semibold ${color ?? ''}`}>{value}</p>
      {sub && <p className="text-muted-foreground text-xs">{sub}</p>}
    </div>
  );
}

// Series config for each tab
const TAB_SERIES: Record<ChartTab, { key: string; name: string; color: string }[]> = {
  all: [
    { key: 'amazon', name: 'Amazon', color: SERIES_COLORS.amazon },
    { key: 'new', name: 'New', color: SERIES_COLORS.new },
    { key: 'new_3p_fba', name: '3P FBA', color: SERIES_COLORS.new_3p_fba },
    { key: 'new_3p_fbm', name: '3P FBM', color: SERIES_COLORS.new_3p_fbm },
    { key: 'used', name: 'Used', color: SERIES_COLORS.used },
    { key: 'warehouse', name: 'Warehouse', color: SERIES_COLORS.warehouse },
  ],
  amazon: [
    { key: 'amazon', name: 'Amazon', color: SERIES_COLORS.amazon },
    { key: 'buy_box', name: 'Buy Box', color: SERIES_COLORS.buy_box },
  ],
  new: [
    { key: 'new', name: 'New (Lowest)', color: SERIES_COLORS.new },
    { key: 'new_3p_fba', name: '3P FBA', color: SERIES_COLORS.new_3p_fba },
    { key: 'new_3p_fbm', name: '3P FBM', color: SERIES_COLORS.new_3p_fbm },
    { key: 'list_price', name: 'List Price', color: SERIES_COLORS.list_price },
  ],
  used: [
    { key: 'used', name: 'Used', color: SERIES_COLORS.used },
    { key: 'warehouse', name: 'Warehouse Deals', color: SERIES_COLORS.warehouse },
  ],
};

export function KeepaPanel({ setNumber }: KeepaDataPanelProps) {
  const [data, setData] = useState<KeepaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<ChartTab>('all');

  useEffect(() => {
    fetch(`/api/items/${setNumber}/keepa`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data) {
          setData(json.data);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [setNumber]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-muted-foreground text-sm">
          Loading Keepa data...
        </p>
      </div>
    );
  }

  if (!data) return null;

  const chartData = buildChartData(data);
  const activeSeries = TAB_SERIES[tab].filter((s) =>
    chartData.some((p) => (p as Record<string, unknown>)[s.key] != null)
  );

  const tabs: { key: ChartTab; label: string }[] = [
    { key: 'all', label: 'All Prices' },
    { key: 'amazon', label: 'Amazon' },
    { key: 'new', label: 'New / 3P' },
    { key: 'used', label: 'Used' },
  ];

  // Compute Y domain from visible series
  const visibleKeys = activeSeries.map((s) => s.key);
  const allValues = chartData.flatMap((p) =>
    visibleKeys
      .map((k) => (p as Record<string, unknown>)[k] as number | undefined)
      .filter((v): v is number => v != null)
  );
  const yMin = allValues.length > 0 ? Math.floor(Math.min(...allValues) * 0.9) : 0;
  const yMax = allValues.length > 0 ? Math.ceil(Math.max(...allValues) * 1.05) : 100;

  const handleScrape = async () => {
    try {
      await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scraperId: 'keepa', url: setNumber }),
      });
    } catch {
      // ignore
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Keepa Amazon Price History</h2>
        <div className="flex items-center gap-2">
          {data.keepa_url && (
            <a
              href={data.keepa_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs"
            >
              View on Keepa
              <ExternalLinkIcon className="h-3 w-3" />
            </a>
          )}
          <button
            onClick={handleScrape}
            className="rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <SummaryCard label="Buy Box" value={formatUsd(data.current_buy_box_cents)} />
        <SummaryCard label="Amazon" value={formatUsd(data.current_amazon_cents)} />
        <SummaryCard label="New (Lowest)" value={formatUsd(data.current_new_cents)} />
        <SummaryCard
          label="Lowest Ever"
          value={formatUsd(data.lowest_ever_cents)}
          color="text-emerald-600"
        />
        <SummaryCard
          label="Highest Ever"
          value={formatUsd(data.highest_ever_cents)}
          color="text-red-500"
        />
      </div>

      {/* Tab navigation */}
      <div className="mb-4 flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="h-80 w-full">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${v}`}
                domain={[yMin, yMax]}
              />
              <Tooltip content={<KeepaTooltip />} />
              <Legend />

              {activeSeries.map((s, i) => (
                i === 0 ? (
                  <Area
                    key={s.key}
                    dataKey={s.key}
                    name={s.name}
                    type="stepAfter"
                    stroke={s.color}
                    fill={s.color}
                    fillOpacity={0.08}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                ) : (
                  <Line
                    key={s.key}
                    dataKey={s.key}
                    name={s.name}
                    type="stepAfter"
                    stroke={s.color}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                )
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="text-muted-foreground text-sm">No price data available</p>
          </div>
        )}
      </div>

      {/* ASIN and scrape info */}
      <div className="text-muted-foreground mt-3 flex items-center gap-4 text-xs">
        {data.asin && <span>ASIN: {data.asin}</span>}
        <span>{chartData.length} data points</span>
        {data.scraped_at && (
          <span>
            Last scraped {new Date(data.scraped_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}

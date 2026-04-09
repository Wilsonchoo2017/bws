'use client';

import { ExternalLinkIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useDetailBundle } from './detail-bundle-context';
import type { ChartDateRange } from './item-detail';

interface CompetitionPanelProps {
  setNumber: string;
  globalDateRange?: ChartDateRange | null;
  onDateRange?: (range: ChartDateRange) => void;
}

interface CompetitionHistoryEntry {
  set_number: string;
  listings_count: number;
  unique_sellers: number;
  total_sold_count: number | null;
  min_price_cents: number | null;
  max_price_cents: number | null;
  avg_price_cents: number | null;
  median_price_cents: number | null;
  saturation_score: number;
  saturation_level: string;
  scraped_at: string;
}

interface CompetitionListing {
  product_url: string;
  shop_id: string;
  title: string;
  price_cents: number | null;
  price_display: string;
  sold_count_raw: string | null;
  sold_count_numeric: number | null;
  rating: string | null;
  image_url: string | null;
  is_sold_out: boolean;
  is_delisted: boolean;
  discovery_method: string;
  scraped_at: string;
  sold_delta: number | null;
}

interface CompetitionData {
  history: CompetitionHistoryEntry[];
  listings: CompetitionListing[];
}

type ChartTab = 'saturation' | 'sellers' | 'sold' | 'competitors';

function buildChartData(history: CompetitionHistoryEntry[]) {
  return [...history]
    .sort((a, b) => (a.scraped_at ?? '').localeCompare(b.scraped_at ?? ''))
    .map((h) => ({
      ts: new Date(h.scraped_at).getTime(),
      label: new Date(h.scraped_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: '2-digit',
      }),
      saturation_score: h.saturation_score,
      listings_count: h.listings_count,
      unique_sellers: h.unique_sellers,
      total_sold_count: h.total_sold_count,
      avg_price: h.avg_price_cents != null ? h.avg_price_cents / 100 : null,
      min_price: h.min_price_cents != null ? h.min_price_cents / 100 : null,
      max_price: h.max_price_cents != null ? h.max_price_cents / 100 : null,
    }));
}

function ScoreTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : 'N/A'}
        </p>
      ))}
    </div>
  );
}

function CountTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {entry.value ?? 'N/A'}
        </p>
      ))}
    </div>
  );
}

function SaturationBadge({ level }: { level: string }) {
  const styles: Record<string, string> = {
    very_low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    moderate: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
    high: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[level] ?? styles.moderate}`}>
      {level.replace('_', ' ')}
    </span>
  );
}

function StatusBadge({ listing }: { listing: CompetitionListing }) {
  if (listing.is_delisted) {
    return (
      <span className='rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400'>
        delisted
      </span>
    );
  }
  if (listing.is_sold_out) {
    return (
      <span className='rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300'>
        sold out
      </span>
    );
  }
  return (
    <span className='rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300'>
      active
    </span>
  );
}

function CompetitorTable({ listings }: { listings: CompetitionListing[] }) {
  if (listings.length === 0) {
    return (
      <p className='text-muted-foreground text-sm'>No competitor listings found.</p>
    );
  }

  return (
    <div className='max-h-[400px] overflow-auto rounded border'>
      <table className='w-full text-sm'>
        <thead className='bg-muted/50 sticky top-0'>
          <tr>
            <th className='px-3 py-2 text-left font-medium'>Seller</th>
            <th className='px-3 py-2 text-left font-medium'>Product</th>
            <th className='px-3 py-2 text-right font-medium'>Price</th>
            <th className='px-3 py-2 text-right font-medium'>Sold</th>
            <th className='px-3 py-2 text-right font-medium'>Rating</th>
            <th className='px-3 py-2 text-center font-medium'>Status</th>
            <th className='px-3 py-2 text-center font-medium'>Source</th>
          </tr>
        </thead>
        <tbody>
          {listings.map((l, i) => (
            <tr key={i} className='border-border border-t'>
              <td className='px-3 py-1.5'>
                <a
                  href={`https://shopee.com.my/shop/${l.shop_id}`}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='text-blue-600 hover:underline dark:text-blue-400'
                >
                  {l.shop_id}
                </a>
              </td>
              <td className='max-w-[200px] truncate px-3 py-1.5'>
                {l.product_url ? (
                  <a
                    href={l.product_url}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='inline-flex items-center gap-1 text-blue-600 hover:underline dark:text-blue-400'
                  >
                    <span className='truncate'>{l.title}</span>
                    <ExternalLinkIcon className='size-3 shrink-0 opacity-50' />
                  </a>
                ) : (
                  <span className='truncate'>{l.title}</span>
                )}
              </td>
              <td className='px-3 py-1.5 text-right font-mono'>
                {l.price_cents != null
                  ? `RM${(l.price_cents / 100).toFixed(2)}`
                  : l.price_display || '-'}
              </td>
              <td className='px-3 py-1.5 text-right font-mono'>
                <span>{l.sold_count_numeric ?? l.sold_count_raw ?? '-'}</span>
                {l.sold_delta != null && l.sold_delta > 0 && (
                  <span className='ml-1 text-xs text-green-600 dark:text-green-400'>
                    +{l.sold_delta}
                  </span>
                )}
              </td>
              <td className='px-3 py-1.5 text-right font-mono'>
                {l.rating ?? '-'}
              </td>
              <td className='px-3 py-1.5 text-center'>
                <StatusBadge listing={l} />
              </td>
              <td className='px-3 py-1.5 text-center'>
                <span className={`rounded-full px-2 py-0.5 text-xs ${
                  l.discovery_method === 'search'
                    ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400'
                    : 'bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400'
                }`}>
                  {l.discovery_method}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CompetitionPanel({
  setNumber,
  globalDateRange,
  onDateRange,
}: CompetitionPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [data, setData] = useState<CompetitionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [tab, setTab] = useState<ChartTab>('saturation');

  useEffect(() => {
    if (bundleLoading) return;
    if (bundle?.competition) { setData(bundle.competition as unknown as CompetitionData); setLoading(false); return; }
    fetch(`/api/items/${setNumber}/competition`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json) => {
        if (json.success && json.data) {
          setData(json.data);
        }
      })
      .catch((err) => {
        setFetchError(err instanceof Error ? err.message : 'Failed to load competition data');
      })
      .finally(() => setLoading(false));
  }, [setNumber, bundle, bundleLoading]);

  const chartData = data ? buildChartData(data.history) : [];

  // Report date range to parent for cross-chart sync
  useEffect(() => {
    if (onDateRange && chartData.length > 0) {
      const timestamps = chartData.map((p) => p.ts);
      onDateRange({
        min: Math.min(...timestamps),
        max: Math.max(...timestamps),
      });
    }
  }, [chartData.length]);

  if (loading) {
    return (
      <div className='flex h-64 items-center justify-center'>
        <p className='text-muted-foreground text-sm'>Loading competition data...</p>
      </div>
    );
  }

  if (fetchError) {
    return null;
  }

  if (!data || (data.history.length === 0 && data.listings.length === 0)) {
    return null;
  }

  const latest = data.history.length > 0 ? data.history[0] : null;

  const tabs: { key: ChartTab; label: string; disabled: boolean }[] = [
    { key: 'saturation', label: 'Saturation Score', disabled: chartData.length === 0 },
    { key: 'sellers', label: 'Sellers', disabled: chartData.length === 0 },
    { key: 'sold', label: 'Total Sold', disabled: chartData.length === 0 },
    { key: 'competitors', label: `Competitors (${data.listings.length})`, disabled: data.listings.length === 0 },
  ];

  return (
    <div>
      <h2 className='mb-3 text-lg font-semibold'>Shopee Competition</h2>

      {/* Summary boxes */}
      {latest && (
        <div className='mb-4 grid grid-cols-4 gap-3'>
          <div className='border-border rounded-lg border px-3 py-2'>
            <div className='text-muted-foreground text-xs'>Saturation</div>
            <div className='mt-0.5 flex items-center gap-2'>
              <span className='font-mono text-lg font-semibold'>
                {latest.saturation_score.toFixed(1)}
              </span>
              <SaturationBadge level={latest.saturation_level} />
            </div>
          </div>
          <div className='border-border rounded-lg border px-3 py-2'>
            <div className='text-muted-foreground text-xs'>Listings</div>
            <div className='mt-0.5 font-mono text-lg font-semibold'>
              {latest.listings_count}
            </div>
          </div>
          <div className='border-border rounded-lg border px-3 py-2'>
            <div className='text-muted-foreground text-xs'>Unique Sellers</div>
            <div className='mt-0.5 font-mono text-lg font-semibold'>
              {latest.unique_sellers}
            </div>
          </div>
          <div className='border-border rounded-lg border px-3 py-2'>
            <div className='text-muted-foreground text-xs'>Total Sold</div>
            <div className='mt-0.5 font-mono text-lg font-semibold'>
              {latest.total_sold_count ?? '-'}
            </div>
          </div>
        </div>
      )}

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

      {/* Chart area */}
      {tab !== 'competitors' && chartData.length > 0 && (
        <div className='h-72 w-full'>
          {tab === 'saturation' && (
            <ResponsiveContainer width='100%' height='100%' minWidth={0} minHeight={0}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
                <XAxis
                  dataKey='ts'
                  type='number'
                  scale='time'
                  domain={
                    globalDateRange
                      ? [globalDateRange.min, globalDateRange.max]
                      : ['dataMin', 'dataMax']
                  }
                  tick={{ fontSize: 11 }}
                  tickFormatter={(ts) =>
                    new Date(ts).toLocaleDateString('en-US', {
                      month: 'short',
                      year: '2-digit',
                    })
                  }
                />
                <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                <Tooltip content={<ScoreTooltip />} />
                <Legend />
                <Area
                  type='monotone'
                  dataKey='saturation_score'
                  name='Saturation Score'
                  stroke='#f97316'
                  fill='#f97316'
                  fillOpacity={0.1}
                  strokeWidth={2}
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          )}

          {tab === 'sellers' && (
            <ResponsiveContainer width='100%' height='100%' minWidth={0} minHeight={0}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
                <XAxis
                  dataKey='ts'
                  type='number'
                  scale='time'
                  domain={
                    globalDateRange
                      ? [globalDateRange.min, globalDateRange.max]
                      : ['dataMin', 'dataMax']
                  }
                  tick={{ fontSize: 11 }}
                  tickFormatter={(ts) =>
                    new Date(ts).toLocaleDateString('en-US', {
                      month: 'short',
                      year: '2-digit',
                    })
                  }
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip content={<CountTooltip />} />
                <Legend />
                <Area
                  type='monotone'
                  dataKey='unique_sellers'
                  name='Unique Sellers'
                  stroke='#8b5cf6'
                  fill='#8b5cf6'
                  fillOpacity={0.1}
                  strokeWidth={2}
                  connectNulls
                />
                <Area
                  type='monotone'
                  dataKey='listings_count'
                  name='Total Listings'
                  stroke='#6366f1'
                  fill='#6366f1'
                  fillOpacity={0.05}
                  strokeWidth={1.5}
                  strokeDasharray='5 5'
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          )}

          {tab === 'sold' && (
            <ResponsiveContainer width='100%' height='100%' minWidth={0} minHeight={0}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
                <XAxis
                  dataKey='ts'
                  type='number'
                  scale='time'
                  domain={
                    globalDateRange
                      ? [globalDateRange.min, globalDateRange.max]
                      : ['dataMin', 'dataMax']
                  }
                  tick={{ fontSize: 11 }}
                  tickFormatter={(ts) =>
                    new Date(ts).toLocaleDateString('en-US', {
                      month: 'short',
                      year: '2-digit',
                    })
                  }
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip content={<CountTooltip />} />
                <Legend />
                <Bar
                  dataKey='total_sold_count'
                  name='Total Sold'
                  fill='#10b981'
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Competitors table */}
      {tab === 'competitors' && (
        <CompetitorTable listings={data.listings} />
      )}

      {/* Price summary under charts */}
      {latest && tab !== 'competitors' && latest.avg_price_cents != null && (
        <div className='mt-3 grid grid-cols-3 gap-3'>
          <div className='border-border rounded-lg border px-3 py-2 opacity-80'>
            <div className='text-muted-foreground text-xs'>Avg Price</div>
            <div className='mt-0.5 font-mono font-semibold'>
              RM{(latest.avg_price_cents / 100).toFixed(2)}
            </div>
          </div>
          <div className='border-border rounded-lg border px-3 py-2 opacity-80'>
            <div className='text-muted-foreground text-xs'>Min Price</div>
            <div className='mt-0.5 font-mono font-semibold'>
              {latest.min_price_cents != null
                ? `RM${(latest.min_price_cents / 100).toFixed(2)}`
                : '-'}
            </div>
          </div>
          <div className='border-border rounded-lg border px-3 py-2 opacity-80'>
            <div className='text-muted-foreground text-xs'>Max Price</div>
            <div className='mt-0.5 font-mono font-semibold'>
              {latest.max_price_cents != null
                ? `RM${(latest.max_price_cents / 100).toFixed(2)}`
                : '-'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

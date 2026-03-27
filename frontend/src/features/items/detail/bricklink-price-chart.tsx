'use client';

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
import type { BricklinkPriceData, MonthlySaleRecord } from '../types';
import { formatPrice } from '../types';

interface BricklinkPriceChartProps {
  setNumber: string;
}

type ChartTab = 'monthly-price' | 'monthly-volume' | 'snapshots';

const MONTH_NAMES = [
  '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

function buildMonthlySalesChart(sales: readonly MonthlySaleRecord[]) {
  const byMonth = new Map<string, {
    label: string;
    new_avg: number | null;
    used_avg: number | null;
    new_min: number | null;
    new_max: number | null;
    used_min: number | null;
    used_max: number | null;
    new_qty: number;
    used_qty: number;
    new_sold: number;
    used_sold: number;
  }>();

  for (const sale of sales) {
    const key = `${sale.year}-${String(sale.month).padStart(2, '0')}`;
    const label = `${MONTH_NAMES[sale.month]} ${sale.year}`;
    const existing = byMonth.get(key) ?? {
      label,
      new_avg: null,
      used_avg: null,
      new_min: null,
      new_max: null,
      used_min: null,
      used_max: null,
      new_qty: 0,
      used_qty: 0,
      new_sold: 0,
      used_sold: 0,
    };

    const avgDollars = sale.avg_price_cents !== null ? sale.avg_price_cents / 100 : null;
    const minDollars = sale.min_price_cents !== null ? sale.min_price_cents / 100 : null;
    const maxDollars = sale.max_price_cents !== null ? sale.max_price_cents / 100 : null;

    if (sale.condition === 'new') {
      existing.new_avg = avgDollars;
      existing.new_min = minDollars;
      existing.new_max = maxDollars;
      existing.new_qty = sale.total_quantity;
      existing.new_sold = sale.times_sold;
    } else {
      existing.used_avg = avgDollars;
      existing.used_min = minDollars;
      existing.used_max = maxDollars;
      existing.used_qty = sale.total_quantity;
      existing.used_sold = sale.times_sold;
    }

    byMonth.set(key, existing);
  }

  return [...byMonth.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, v]) => v);
}

function buildSnapshotChart(history: BricklinkPriceData['price_history']) {
  return [...history]
    .sort((a, b) => (a.scraped_at ?? '').localeCompare(b.scraped_at ?? ''))
    .map((h) => ({
      label: h.scraped_at
        ? new Date(h.scraped_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })
        : '?',
      current_new_avg:
        h.current_new?.avg_price_cents != null
          ? h.current_new.avg_price_cents / 100
          : null,
      current_used_avg:
        h.current_used?.avg_price_cents != null
          ? h.current_used.avg_price_cents / 100
          : null,
      six_month_new_avg:
        h.six_month_new?.avg_price_cents != null
          ? h.six_month_new.avg_price_cents / 100
          : null,
      six_month_used_avg:
        h.six_month_used?.avg_price_cents != null
          ? h.six_month_used.avg_price_cents / 100
          : null,
      current_new_lots: h.current_new?.total_lots ?? 0,
      current_used_lots: h.current_used?.total_lots ?? 0,
    }));
}

function PriceTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: RM{entry.value?.toFixed(2) ?? 'N/A'}
        </p>
      ))}
    </div>
  );
}

function VolumeTooltip({ active, payload, label }: any) {
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

export function BricklinkPriceChart({ setNumber }: BricklinkPriceChartProps) {
  const [data, setData] = useState<BricklinkPriceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<ChartTab>('monthly-price');

  useEffect(() => {
    fetch(`/api/items/${setNumber}/bricklink-prices`)
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
      <div className='flex h-64 items-center justify-center'>
        <p className='text-muted-foreground text-sm'>Loading price charts...</p>
      </div>
    );
  }

  if (
    !data ||
    (data.monthly_sales.length === 0 && data.price_history.length === 0)
  ) {
    return null;
  }

  const monthlyChart = buildMonthlySalesChart(data.monthly_sales);
  const snapshotChart = buildSnapshotChart(data.price_history);

  const tabs: { key: ChartTab; label: string; disabled: boolean }[] = [
    {
      key: 'monthly-price',
      label: 'Sold Prices',
      disabled: monthlyChart.length === 0,
    },
    {
      key: 'monthly-volume',
      label: 'Transaction Volume',
      disabled: monthlyChart.length === 0,
    },
    {
      key: 'snapshots',
      label: 'Sold vs Listing',
      disabled: snapshotChart.length === 0,
    },
  ];

  // Get currency from first available sale
  const currency = data.monthly_sales[0]?.currency ?? 'USD';

  return (
    <div>
      <h2 className='mb-3 text-lg font-semibold'>BrickLink Price Analysis</h2>

      {/* Current vs 6-month summary boxes */}
      {data.price_history.length > 0 && (
        <PriceSummaryBoxes
          latest={data.price_history[0]}
          currency={currency}
        />
      )}

      {/* Tab navigation */}
      <div className='mb-4 mt-4 flex gap-1'>
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
      <div className='h-72 w-full'>
        {tab === 'monthly-price' && monthlyChart.length > 0 && (
          <ResponsiveContainer width='100%' height='100%'>
            <AreaChart data={monthlyChart}>
              <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
              <XAxis
                dataKey='label'
                tick={{ fontSize: 11 }}
                interval='preserveStartEnd'
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `RM${v}`}
              />
              <Tooltip content={<PriceTooltip />} />
              <Legend />
              <Area
                type='monotone'
                dataKey='new_avg'
                name='Sold New (Avg)'
                stroke='#3b82f6'
                fill='#3b82f6'
                fillOpacity={0.1}
                strokeWidth={2}
                connectNulls
              />
              <Area
                type='monotone'
                dataKey='used_avg'
                name='Sold Used (Avg)'
                stroke='#06b6d4'
                fill='#06b6d4'
                fillOpacity={0.1}
                strokeWidth={2}
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        )}

        {tab === 'monthly-volume' && monthlyChart.length > 0 && (
          <ResponsiveContainer width='100%' height='100%'>
            <BarChart data={monthlyChart}>
              <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
              <XAxis
                dataKey='label'
                tick={{ fontSize: 11 }}
                interval='preserveStartEnd'
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip content={<VolumeTooltip />} />
              <Legend />
              <Bar
                dataKey='new_qty'
                name='New Transactions'
                fill='#3b82f6'
                radius={[2, 2, 0, 0]}
              />
              <Bar
                dataKey='used_qty'
                name='Used Transactions'
                fill='#06b6d4'
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}

        {tab === 'snapshots' && snapshotChart.length > 0 && (
          <ResponsiveContainer width='100%' height='100%'>
            <AreaChart data={snapshotChart}>
              <CartesianGrid strokeDasharray='3 3' opacity={0.3} />
              <XAxis
                dataKey='label'
                tick={{ fontSize: 11 }}
                interval='preserveStartEnd'
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `RM${v}`}
              />
              <Tooltip content={<PriceTooltip />} />
              <Legend />
              {/* Sold prices -- prominent */}
              <Area
                type='monotone'
                dataKey='six_month_new_avg'
                name='Sold New (6mo)'
                stroke='#3b82f6'
                fill='#3b82f6'
                fillOpacity={0.1}
                strokeWidth={2}
                connectNulls
              />
              <Area
                type='monotone'
                dataKey='six_month_used_avg'
                name='Sold Used (6mo)'
                stroke='#06b6d4'
                fill='#06b6d4'
                fillOpacity={0.1}
                strokeWidth={2}
                connectNulls
              />
              {/* Listing prices -- secondary */}
              <Area
                type='monotone'
                dataKey='current_new_avg'
                name='Listed New'
                stroke='#9ca3af'
                fill='none'
                strokeWidth={1.5}
                strokeDasharray='5 5'
                connectNulls
              />
              <Area
                type='monotone'
                dataKey='current_used_avg'
                name='Listed Used'
                stroke='#d1d5db'
                fill='none'
                strokeWidth={1.5}
                strokeDasharray='5 5'
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Monthly sales detail table */}
      {data.monthly_sales.length > 0 && (
        <MonthlySalesTable sales={data.monthly_sales} currency={currency} />
      )}
    </div>
  );
}

function PriceSummaryBoxes({
  latest,
  currency,
}: {
  latest: BricklinkPriceData['price_history'][number];
  currency: string;
}) {
  const soldBoxes = [
    { label: 'Sold New (6mo)', box: latest.six_month_new },
    { label: 'Sold Used (6mo)', box: latest.six_month_used },
  ];
  const listingBoxes = [
    { label: 'For Sale New', box: latest.current_new },
    { label: 'For Sale Used', box: latest.current_used },
  ];

  return (
    <div className='flex flex-col gap-3'>
      {/* Sold prices -- actual transactions */}
      <div>
        <div className='text-muted-foreground mb-1.5 text-xs font-medium uppercase tracking-wide'>
          Sold Prices (Transactions)
        </div>
        <div className='grid grid-cols-2 gap-3'>
          {soldBoxes.map(({ label, box }) => (
            <div
              key={label}
              className='border-border rounded-lg border px-3 py-2'
            >
              <div className='text-muted-foreground text-xs'>{label}</div>
              {box ? (
                <>
                  <div className='mt-0.5 font-mono text-lg font-semibold'>
                    {formatPrice(box.avg_price_cents, currency)}
                  </div>
                  <div className='text-muted-foreground mt-0.5 flex flex-col gap-0.5 text-xs'>
                    <span>
                      {formatPrice(box.min_price_cents, currency)} -{' '}
                      {formatPrice(box.max_price_cents, currency)}
                    </span>
                    <span>
                      {box.times_sold ?? 0} transactions, {box.total_qty ?? 0} qty
                    </span>
                  </div>
                </>
              ) : (
                <div className='text-muted-foreground mt-0.5 text-sm'>No data</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* For sale prices -- current listings */}
      <div>
        <div className='text-muted-foreground mb-1.5 text-xs font-medium uppercase tracking-wide'>
          Current Listings (For Sale)
        </div>
        <div className='grid grid-cols-2 gap-3'>
          {listingBoxes.map(({ label, box }) => (
            <div
              key={label}
              className='border-border rounded-lg border px-3 py-2 opacity-80'
            >
              <div className='text-muted-foreground text-xs'>{label}</div>
              {box ? (
                <>
                  <div className='mt-0.5 font-mono text-lg font-semibold'>
                    {formatPrice(box.avg_price_cents, currency)}
                  </div>
                  <div className='text-muted-foreground mt-0.5 flex flex-col gap-0.5 text-xs'>
                    <span>
                      {formatPrice(box.min_price_cents, currency)} -{' '}
                      {formatPrice(box.max_price_cents, currency)}
                    </span>
                    <span>
                      {box.total_lots ?? 0} listings, {box.total_qty ?? 0} qty
                    </span>
                  </div>
                </>
              ) : (
                <div className='text-muted-foreground mt-0.5 text-sm'>No data</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MonthlySalesTable({
  sales,
  currency,
}: {
  sales: readonly MonthlySaleRecord[];
  currency: string;
}) {
  // Sort chronologically (newest first)
  const sorted = [...sales].sort((a, b) => {
    const diff = b.year - a.year;
    return diff !== 0 ? diff : b.month - a.month;
  });

  return (
    <div className='mt-4'>
      <h3 className='mb-2 text-sm font-semibold'>Monthly Transaction History</h3>
      <div className='max-h-[300px] overflow-auto rounded border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/50 sticky top-0'>
            <tr>
              <th className='px-3 py-2 text-left font-medium'>Month</th>
              <th className='px-3 py-2 text-left font-medium'>Condition</th>
              <th className='px-3 py-2 text-right font-medium'>Txns</th>
              <th className='px-3 py-2 text-right font-medium'>Qty</th>
              <th className='px-3 py-2 text-right font-medium'>Min</th>
              <th className='px-3 py-2 text-right font-medium'>Avg</th>
              <th className='px-3 py-2 text-right font-medium'>Max</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => (
              <tr key={i} className='border-border border-t'>
                <td className='px-3 py-1.5'>
                  {MONTH_NAMES[s.month]} {s.year}
                </td>
                <td className='px-3 py-1.5'>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      s.condition === 'new'
                        ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
                        : 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300'
                    }`}
                  >
                    {s.condition}
                  </span>
                </td>
                <td className='px-3 py-1.5 text-right font-mono'>
                  {s.times_sold}
                </td>
                <td className='px-3 py-1.5 text-right font-mono'>
                  {s.total_quantity}
                </td>
                <td className='px-3 py-1.5 text-right font-mono'>
                  {formatPrice(s.min_price_cents, currency)}
                </td>
                <td className='px-3 py-1.5 text-right font-mono'>
                  {formatPrice(s.avg_price_cents, currency)}
                </td>
                <td className='px-3 py-1.5 text-right font-mono'>
                  {formatPrice(s.max_price_cents, currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

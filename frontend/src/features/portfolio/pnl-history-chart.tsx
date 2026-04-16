'use client';

import { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface MonthlyProfit {
  year: number;
  month: number;
  date: string;
  cumulative_buy_cents: number;
  cumulative_sell_cents: number;
  net_profit_cents: number;
  month_buy_cents: number;
  month_sell_cents: number;
}

interface ChartPoint {
  label: string;
  netProfit: number;
  priorNetProfit: number | null;
  yoyChange: number | null;
  yoyRoc: number | null;
}

function formatRM(cents: number): string {
  const amount = cents / 100;
  if (Math.abs(amount) >= 1000) {
    return `RM${(amount / 1000).toFixed(1)}k`;
  }
  return `RM${amount.toFixed(0)}`;
}

function formatPct(v: number | null): string {
  if (v === null) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

function ProfitTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as ChartPoint | undefined;
  if (!d) return null;

  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      <p>
        <span className='text-muted-foreground'>Net profit: </span>
        <span className={d.netProfit >= 0 ? 'font-semibold text-green-600' : 'font-semibold text-red-600'}>
          {formatRM(d.netProfit)}
        </span>
      </p>
      {d.priorNetProfit !== null && (
        <p>
          <span className='text-muted-foreground'>Prior year: </span>
          <span className={d.priorNetProfit >= 0 ? 'text-green-600' : 'text-red-600'}>
            {formatRM(d.priorNetProfit)}
          </span>
        </p>
      )}
      {d.yoyChange !== null && (
        <p>
          <span className='text-muted-foreground'>YoY change: </span>
          <span className={d.yoyChange >= 0 ? 'text-green-600' : 'text-red-600'}>
            {formatRM(d.yoyChange)}
          </span>
        </p>
      )}
      {d.yoyRoc !== null && (
        <p>
          <span className='text-muted-foreground'>YoY RoC: </span>
          <span className={d.yoyRoc >= 0 ? 'text-green-600' : 'text-red-600'}>
            {formatPct(d.yoyRoc)}
          </span>
        </p>
      )}
    </div>
  );
}

function RocTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as ChartPoint | undefined;
  if (!d || d.yoyRoc === null) return null;

  return (
    <div className='rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900'>
      <p className='mb-1 font-medium'>{label}</p>
      <p>
        <span className='text-muted-foreground'>YoY Rate of Change: </span>
        <span className={d.yoyRoc >= 0 ? 'font-semibold text-green-600' : 'font-semibold text-red-600'}>
          {formatPct(d.yoyRoc)}
        </span>
      </p>
    </div>
  );
}

function buildChartData(raw: MonthlyProfit[]): ChartPoint[] {
  if (raw.length < 13) {
    return raw.slice(-12).map((m) => ({
      label: `${MONTH_LABELS[m.month - 1]} ${m.year}`,
      netProfit: m.net_profit_cents,
      priorNetProfit: null,
      yoyChange: null,
      yoyRoc: null,
    }));
  }

  const current = raw.slice(-12);
  const prior = raw.slice(-24, -12);

  const priorByMonth: Record<number, MonthlyProfit> = {};
  for (const p of prior) {
    priorByMonth[p.month] = p;
  }

  return current.map((m) => {
    const priorMonth = priorByMonth[m.month] ?? null;
    const priorNet = priorMonth ? priorMonth.net_profit_cents : null;
    const yoyChange = priorNet !== null ? m.net_profit_cents - priorNet : null;
    const yoyRoc =
      priorNet !== null && priorNet !== 0
        ? ((m.net_profit_cents - priorNet) / Math.abs(priorNet)) * 100
        : null;

    return {
      label: `${MONTH_LABELS[m.month - 1]} ${m.year}`,
      netProfit: m.net_profit_cents,
      priorNetProfit: priorNet,
      yoyChange,
      yoyRoc,
    };
  });
}

export function PnlHistoryChart() {
  const [data, setData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio/pnl-history')
      .then((r) => r.json())
      .then((json) => {
        if (json.success) {
          setData(buildChartData(json.data));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className='bg-muted h-64 animate-pulse rounded-lg' />;
  }

  if (data.length === 0) {
    return null;
  }

  const hasYoy = data.some((d) => d.yoyRoc !== null);
  const latest = data[data.length - 1];

  return (
    <div className='rounded-lg border p-4'>
      <div className='flex items-baseline justify-between'>
        <div>
          <h3 className='text-sm font-semibold uppercase tracking-wider'>
            Net Profit
          </h3>
          <p className='text-muted-foreground mt-0.5 text-xs'>
            Cumulative sells minus buys over the last 12 months
          </p>
        </div>
        <div className='flex items-center gap-4 text-xs'>
          <div>
            <span className='text-muted-foreground'>Current </span>
            <span className={latest.netProfit >= 0 ? 'font-semibold text-green-600' : 'font-semibold text-red-600'}>
              {formatRM(latest.netProfit)}
            </span>
          </div>
          {hasYoy && latest.yoyChange !== null && (
            <div>
              <span className='text-muted-foreground'>YoY </span>
              <span className={latest.yoyChange >= 0 ? 'font-semibold text-green-600' : 'font-semibold text-red-600'}>
                {formatRM(latest.yoyChange)}
              </span>
            </div>
          )}
          {hasYoy && latest.yoyRoc !== null && (
            <div>
              <span className='text-muted-foreground'>YoY RoC </span>
              <span className={latest.yoyRoc >= 0 ? 'font-semibold text-green-600' : 'font-semibold text-red-600'}>
                {formatPct(latest.yoyRoc)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Net Profit Area Chart with YoY overlay */}
      <div className='mt-4'>
        <ResponsiveContainer width='100%' height={220}>
          <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id='profitPos' x1='0' y1='0' x2='0' y2='1'>
                <stop offset='5%' stopColor='#22c55e' stopOpacity={0.3} />
                <stop offset='95%' stopColor='#22c55e' stopOpacity={0} />
              </linearGradient>
              <linearGradient id='profitPrior' x1='0' y1='0' x2='0' y2='1'>
                <stop offset='5%' stopColor='#94a3b8' stopOpacity={0.2} />
                <stop offset='95%' stopColor='#94a3b8' stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray='3 3' className='opacity-30' />
            <XAxis
              dataKey='label'
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => formatRM(v)}
              width={70}
              domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]}
            />
            <Tooltip content={<ProfitTooltip />} />
            <ReferenceLine y={0} stroke='#94a3b8' strokeDasharray='3 3' />
            {hasYoy && (
              <Area
                type='monotone'
                dataKey='priorNetProfit'
                name='Prior Year'
                stroke='#94a3b8'
                fill='url(#profitPrior)'
                strokeDasharray='4 4'
                strokeWidth={1.5}
                dot={false}
                connectNulls
              />
            )}
            <Area
              type='monotone'
              dataKey='netProfit'
              name='Net Profit'
              stroke='#22c55e'
              fill='url(#profitPos)'
              strokeWidth={2}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* YoY Rate of Change Bar Chart */}
      {hasYoy && (
        <div className='mt-4'>
          <p className='text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider'>
            YoY Rate of Change
          </p>
          <ResponsiveContainer width='100%' height={120}>
            <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray='3 3' className='opacity-30' />
              <XAxis
                dataKey='label'
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                width={50}
                domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]}
              />
              <Tooltip content={<RocTooltip />} />
              <ReferenceLine y={0} stroke='#94a3b8' strokeDasharray='3 3' />
              <Bar
                dataKey='yoyRoc'
                name='YoY RoC'
                fill='#6366f1'
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Legend */}
      <div className='mt-3 flex items-center gap-4 text-xs'>
        <div className='flex items-center gap-1.5'>
          <div className='h-0.5 w-4 bg-green-500' />
          <span className='text-muted-foreground'>Net profit (sells - buys)</span>
        </div>
        {hasYoy && (
          <>
            <div className='flex items-center gap-1.5'>
              <div className='h-0.5 w-4 border-t border-dashed border-slate-400' />
              <span className='text-muted-foreground'>Prior year</span>
            </div>
            <div className='flex items-center gap-1.5'>
              <div className='h-3 w-3 rounded-sm bg-indigo-500' />
              <span className='text-muted-foreground'>YoY rate of change</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

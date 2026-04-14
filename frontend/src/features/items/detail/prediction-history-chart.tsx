'use client';

import { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useDetailBundle } from './detail-bundle-context';

interface PredictionPoint {
  date: string;
  growth_pct: number;
  confidence: string | null;
  buy_signal: boolean | null;
  buy_category: 'GREAT' | 'GOOD' | 'SKIP' | 'WORST' | null;
  avoid_probability: number | null;
  interval_lower: number | null;
  interval_upper: number | null;
  actual_growth_pct: number | null;
}

interface PredictionHistoryChartProps {
  setNumber: string;
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;

  const signal = d.buy_category ?? (d.buy_signal === true ? 'BUY' : d.buy_signal === false ? 'HOLD' : '--');

  return (
    <div className="rounded-lg border bg-white px-3 py-2 text-xs shadow-lg dark:bg-zinc-900">
      <p className="mb-1 font-medium">{label}</p>
      <p>
        <span className="text-muted-foreground">Predicted: </span>
        <span className="font-semibold">+{d.growth_pct?.toFixed(1)}%</span>
      </p>
      {d.interval_lower != null && d.interval_upper != null && (
        <p className="text-muted-foreground">
          Range: {d.interval_lower.toFixed(1)}% - {d.interval_upper.toFixed(1)}%
        </p>
      )}
      {d.actual_growth_pct != null && (
        <p>
          <span className="text-muted-foreground">Actual: </span>
          <span className="font-semibold">{d.actual_growth_pct.toFixed(1)}%</span>
        </p>
      )}
      <p className="text-muted-foreground">
        Signal: {signal} | Conf: {d.confidence ?? '--'}
      </p>
    </div>
  );
}

export function PredictionHistoryChart({ setNumber }: PredictionHistoryChartProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [data, setData] = useState<PredictionPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (bundleLoading) return;
    const bundleTracking = bundle?.ml_tracking as PredictionPoint[] | null;
    if (bundleTracking) { setData(bundleTracking); setLoading(false); return; }
    const controller = new AbortController();
    fetch(`/api/ml/tracking/${setNumber}`, { signal: controller.signal })
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data) {
          setData(json.data);
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          // silently degrade
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber, bundle, bundleLoading]);

  if (loading) {
    return (
      <p className="text-xs text-muted-foreground">Loading prediction history...</p>
    );
  }

  if (data.length < 2) {
    return null; // Not enough data points for a chart
  }

  const chartData = data.map((d) => ({
    ...d,
    label: new Date(d.date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }));

  const actualGrowth = data.find((d) => d.actual_growth_pct != null)?.actual_growth_pct;

  return (
    <div className="mt-4">
      <h3 className="text-sm font-medium text-muted-foreground">
        Prediction History
      </h3>
      <div className="mt-2 h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              className="fill-muted-foreground"
            />
            <YAxis
              tick={{ fontSize: 11 }}
              className="fill-muted-foreground"
              tickFormatter={(v: number) => `${v}%`}
              width={45}
            />
            <Tooltip content={<ChartTooltip />} />

            {/* Confidence interval band */}
            <Area
              dataKey="interval_upper"
              stroke="none"
              fill="hsl(var(--primary))"
              fillOpacity={0.08}
              isAnimationActive={false}
            />
            <Area
              dataKey="interval_lower"
              stroke="none"
              fill="hsl(var(--background))"
              fillOpacity={1}
              isAnimationActive={false}
            />

            {/* Main prediction line */}
            <Area
              dataKey="growth_pct"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              fill="hsl(var(--primary))"
              fillOpacity={0.1}
              dot={{ r: 3, fill: 'hsl(var(--primary))' }}
              isAnimationActive={false}
            />

            {/* Actual growth reference line */}
            {actualGrowth != null && (
              <ReferenceLine
                y={actualGrowth}
                stroke="hsl(var(--destructive))"
                strokeDasharray="6 3"
                label={{
                  value: `Actual ${actualGrowth.toFixed(1)}%`,
                  position: 'right',
                  fontSize: 10,
                  fill: 'hsl(var(--destructive))',
                }}
              />
            )}

            {/* 8% buy hurdle */}
            <ReferenceLine
              y={8}
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="3 3"
              strokeOpacity={0.5}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {data.length} snapshots since {data[0].date}
        {actualGrowth != null && ' | dashed red = actual growth'}
      </p>
    </div>
  );
}

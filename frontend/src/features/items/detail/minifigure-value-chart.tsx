'use client';

import { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { MinifigValueSnapshot } from '../types';
import { formatPrice } from '../types';

interface MinifigureValueChartProps {
  setNumber: string;
}

function ValueTooltip({ active, payload, label }: any) {
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

export function MinifigureValueChart({ setNumber }: MinifigureValueChartProps) {
  const [snapshots, setSnapshots] = useState<MinifigValueSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`/api/items/${setNumber}/minifigures/value-history`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data?.snapshots) {
          setSnapshots(json.data.snapshots);
        }
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [setNumber]);

  if (loading || (!error && snapshots.length === 0)) {
    return null;
  }

  if (error) {
    return null;
  }

  const chartData = snapshots.map((s) => ({
    label: s.scraped_at
      ? new Date(s.scraped_at).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        })
      : '?',
    total_new: s.total_new_cents / 100,
    total_used: s.total_used_cents / 100,
  }));

  return (
    <div>
      <h2 className='mb-3 text-lg font-semibold'>Minifigure Value Trend</h2>
      <div className='h-64 w-full'>
        <ResponsiveContainer width='100%' height='100%' minWidth={0} minHeight={0}>
          <AreaChart data={chartData}>
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
            <Tooltip content={<ValueTooltip />} />
            <Legend />
            <Area
              type='monotone'
              dataKey='total_new'
              name='Total New Value'
              stroke='#3b82f6'
              fill='#3b82f6'
              fillOpacity={0.1}
              strokeWidth={2}
              connectNulls
            />
            <Area
              type='monotone'
              dataKey='total_used'
              name='Total Used Value'
              stroke='#06b6d4'
              fill='#06b6d4'
              fillOpacity={0.1}
              strokeWidth={2}
              connectNulls
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

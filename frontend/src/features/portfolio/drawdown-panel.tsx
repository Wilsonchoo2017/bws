'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { formatPrice } from '@/lib/formatting';
import type { DrawdownSummary, PositionDrawdown } from './types';

interface DrawdownResponse {
  success: boolean;
  data: PositionDrawdown[];
  summary: DrawdownSummary;
  count: number;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function severityClass(pct: number): string {
  if (pct >= 0.30) return 'text-red-600 font-semibold';
  if (pct >= 0.20) return 'text-orange-500 font-semibold';
  if (pct >= 0.10) return 'text-amber-500';
  return 'text-muted-foreground';
}

export function DrawdownPanel() {
  const [data, setData] = useState<PositionDrawdown[] | null>(null);
  const [summary, setSummary] = useState<DrawdownSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio/drawdown')
      .then((r) => r.json())
      .then((json: DrawdownResponse) => {
        if (json.success) {
          setData(json.data);
          setSummary(json.summary);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className='bg-muted h-32 animate-pulse rounded-lg' />;
  }

  if (!data || !summary || data.length === 0) {
    return null;
  }

  const atRisk = data.filter((p) => p.at_risk);
  const hasAlerts = atRisk.length > 0;

  return (
    <div className='rounded-lg border p-4'>
      <div className='flex items-baseline justify-between'>
        <div>
          <h3 className='text-sm font-semibold uppercase tracking-wider'>
            Drawdown Watch
          </h3>
          <p className='text-muted-foreground mt-0.5 text-xs'>
            Peak-to-current since entry. Cost floor applied so positions that
            dropped on entry are reported honestly.
          </p>
        </div>
        <div className='flex items-center gap-4 text-xs'>
          <div>
            <span className='text-muted-foreground'>At risk </span>
            <span className={hasAlerts ? 'text-red-600 font-semibold' : ''}>
              {summary.at_risk_count}/{summary.position_count}
            </span>
          </div>
          <div>
            <span className='text-muted-foreground'>Max </span>
            <span className={severityClass(summary.max_drawdown_pct)}>
              {formatPct(summary.max_drawdown_pct)}
            </span>
          </div>
          <div>
            <span className='text-muted-foreground'>Weighted </span>
            <span className={severityClass(summary.weighted_drawdown_pct)}>
              {formatPct(summary.weighted_drawdown_pct)}
            </span>
          </div>
        </div>
      </div>

      {hasAlerts && (
        <div className='mt-3 overflow-x-auto'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='text-muted-foreground border-b text-left text-xs uppercase tracking-wider'>
                <th className='py-2 pr-3'>Set</th>
                <th className='py-2 pr-3 text-right'>Qty</th>
                <th className='py-2 pr-3 text-right'>Avg Cost</th>
                <th className='py-2 pr-3 text-right'>Current</th>
                <th className='py-2 pr-3 text-right'>Peak</th>
                <th className='py-2 pr-3 text-right'>Drawdown</th>
                <th className='py-2 pr-3 text-right'>Unrealized</th>
                <th className='py-2 pr-3 text-right'>Months</th>
              </tr>
            </thead>
            <tbody>
              {atRisk.map((p) => (
                <tr key={`${p.set_number}-${p.condition}`} className='border-b last:border-0'>
                  <td className='py-2 pr-3 font-mono'>
                    <Link
                      href={`/items/${p.set_number}`}
                      className='hover:underline'
                    >
                      {p.set_number}
                    </Link>
                    <span className='text-muted-foreground ml-1 text-xs'>
                      {p.condition}
                    </span>
                  </td>
                  <td className='py-2 pr-3 text-right font-mono'>{p.quantity}</td>
                  <td className='py-2 pr-3 text-right font-mono'>
                    {formatPrice(p.avg_cost_cents)}
                  </td>
                  <td className='py-2 pr-3 text-right font-mono'>
                    {formatPrice(p.current_value_cents)}
                  </td>
                  <td className='py-2 pr-3 text-right font-mono'>
                    {formatPrice(p.peak_value_cents)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${severityClass(p.drawdown_pct)}`}>
                    {formatPct(p.drawdown_pct)}
                  </td>
                  <td
                    className={`py-2 pr-3 text-right font-mono ${
                      p.unrealized_pl_cents >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {p.unrealized_pl_cents >= 0 ? '+' : ''}
                    {formatPrice(p.unrealized_pl_cents)}
                  </td>
                  <td className='py-2 pr-3 text-right font-mono text-xs'>
                    {p.months_in_drawdown}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!hasAlerts && (
        <p className='text-muted-foreground mt-3 text-xs'>
          No positions beyond the 20% drawdown alert threshold.
        </p>
      )}
    </div>
  );
}

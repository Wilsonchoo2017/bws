'use client';

import { useEffect, useState } from 'react';
import { formatPrice } from '@/lib/formatting';
import type { PortfolioSummary, WBRMetrics } from './types';

function PLText({ cents, pct }: { cents: number; pct?: number }) {
  const color =
    cents > 0 ? 'text-green-600' : cents < 0 ? 'text-red-600' : 'text-muted-foreground';
  const sign = cents > 0 ? '+' : '';
  return (
    <span className={color}>
      {sign}{formatPrice(cents)}
      {pct !== undefined && ` (${sign}${pct.toFixed(1)}%)`}
    </span>
  );
}

export function PortfolioSummaryCards() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [wbr, setWbr] = useState<WBRMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/portfolio/summary').then((r) => {
        if (!r.ok) throw new Error(`Summary fetch failed: ${r.status}`);
        return r.json();
      }),
      fetch('/api/portfolio/wbr').then((r) => {
        if (!r.ok) throw new Error(`WBR fetch failed: ${r.status}`);
        return r.json();
      }),
    ])
      .then(([summaryRes, wbrRes]) => {
        if (summaryRes.success) setSummary(summaryRes.data);
        if (wbrRes.success) setWbr(wbrRes.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className='bg-muted h-24 animate-pulse rounded-lg' />
        ))}
      </div>
    );
  }

  if (!summary) {
    return (
      <div className='text-muted-foreground text-sm'>
        No portfolio data yet. Add a transaction to get started.
      </div>
    );
  }

  const cards = [
    {
      label: 'Total Cost',
      value: formatPrice(summary.total_cost_cents),
      sub: `${summary.unique_sets} sets, ${summary.holdings_count} units`,
    },
    {
      label: 'Market Value',
      value: formatPrice(summary.total_market_value_cents),
    },
    {
      label: 'Unrealized P&L',
      value: (
        <PLText cents={summary.unrealized_pl_cents} pct={summary.unrealized_pl_pct} />
      ),
    },
    {
      label: 'Realized P&L',
      value: <PLText cents={summary.realized_pl_cents} />,
    },
  ];

  const wbrCards = wbr
    ? [
        {
          label: 'Capital > 20% Return',
          value: `${wbr.pct_capital_above_hurdle.toFixed(1)}%`,
        },
        {
          label: 'Avg Fwd Return',
          value: `${(wbr.total_forward_return_weighted * 100).toFixed(1)}%`,
          sub: 'capital-weighted',
        },
        {
          label: 'Worst Holding',
          value: wbr.worst_holding
            ? `${(wbr.worst_holding.forward_annual_return * 100).toFixed(1)}%`
            : '-',
          sub: wbr.worst_holding?.set_number,
        },
      ]
    : [];

  return (
    <div className='flex flex-col gap-4'>
      <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
        {cards.map((card) => (
          <div
            key={card.label}
            className='rounded-lg border p-4'
          >
            <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>
              {card.label}
            </p>
            <p className='mt-1 text-xl font-bold'>{card.value}</p>
            {card.sub && (
              <p className='text-muted-foreground mt-0.5 text-xs'>{card.sub}</p>
            )}
          </div>
        ))}
      </div>
      {wbrCards.length > 0 && (
        <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
          {wbrCards.map((card) => (
            <div
              key={card.label}
              className='rounded-lg border border-dashed p-4'
            >
              <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>
                {card.label}
              </p>
              <p className='mt-1 text-xl font-bold'>{card.value}</p>
              {card.sub && (
                <p className='text-muted-foreground mt-0.5 text-xs'>{card.sub}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

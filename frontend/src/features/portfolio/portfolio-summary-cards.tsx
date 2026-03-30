'use client';

import { useEffect, useState } from 'react';
import type { PortfolioSummary } from './types';

function formatRM(cents: number): string {
  return `RM${(cents / 100).toFixed(2)}`;
}

function PLText({ cents, pct }: { cents: number; pct?: number }) {
  const color =
    cents > 0 ? 'text-green-600' : cents < 0 ? 'text-red-600' : 'text-muted-foreground';
  const sign = cents > 0 ? '+' : '';
  return (
    <span className={color}>
      {sign}{formatRM(cents)}
      {pct !== undefined && ` (${sign}${pct.toFixed(1)}%)`}
    </span>
  );
}

export function PortfolioSummaryCards() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio/summary')
      .then((r) => r.json())
      .then((d) => {
        if (d.success) setSummary(d.data);
      })
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
      value: formatRM(summary.total_cost_cents),
      sub: `${summary.unique_sets} sets, ${summary.holdings_count} units`,
    },
    {
      label: 'Market Value',
      value: formatRM(summary.total_market_value_cents),
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

  return (
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
  );
}

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { formatPrice } from '@/lib/formatting';
import { useDebounce } from '@/lib/hooks/use-debounce';
import type { CapitalData, PortfolioSummary, WBRMetrics } from './types';

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

function readLS(key: string): string {
  try {
    if (typeof window !== 'undefined') return localStorage.getItem(key) || '';
  } catch { /* private browsing */ }
  return '';
}

function writeLS(key: string, value: string): void {
  try {
    if (typeof window !== 'undefined') localStorage.setItem(key, value);
  } catch { /* silently degrade */ }
}

export function PortfolioSummaryCards() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [wbr, setWbr] = useState<WBRMetrics | null>(null);
  const [capital, setCapital] = useState<CapitalData | null>(null);
  const [capitalInput, setCapitalInput] = useState<string>(() => readLS('bws_total_capital'));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const parsed = parseFloat(capitalInput);
  const capitalCents = !isNaN(parsed) && parsed > 0 ? Math.round(parsed * 100) : null;
  const debouncedCents = useDebounce(capitalCents, 800);
  const prevSavedRef = useRef<number | null>(null);

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
      fetch('/api/portfolio/capital').then((r) => {
        if (!r.ok) throw new Error(`Capital fetch failed: ${r.status}`);
        return r.json();
      }),
    ])
      .then(([summaryRes, wbrRes, capitalRes]) => {
        if (summaryRes.success) setSummary(summaryRes.data);
        if (wbrRes.success) setWbr(wbrRes.data);
        if (capitalRes.success) {
          setCapital(capitalRes.data);
          if (capitalRes.data.total_capital_cents != null) {
            prevSavedRef.current = capitalRes.data.total_capital_cents;
            if (!capitalInput) {
              const rm = (capitalRes.data.total_capital_cents / 100).toString();
              setCapitalInput(rm);
              writeLS('bws_total_capital', rm);
            }
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist capital to backend on debounced change
  useEffect(() => {
    if (debouncedCents === null || debouncedCents === prevSavedRef.current) return;
    prevSavedRef.current = debouncedCents;
    setSaving(true);
    fetch('/api/portfolio/capital', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ total_capital_cents: debouncedCents }),
    })
      .then((r) => r.json())
      .then((json) => {
        if (json.success) setCapital(json.data);
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  }, [debouncedCents]);

  const handleCapitalChange = useCallback((value: string) => {
    setCapitalInput(value);
    writeLS('bws_total_capital', value);
  }, []);

  if (loading) {
    return (
      <div className='grid grid-cols-2 gap-4 lg:grid-cols-5'>
        {Array.from({ length: 5 }).map((_, i) => (
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

  const deployed = capital?.deployed_cents ?? summary.total_cost_cents;
  const available = capital?.available_cents ?? 0;

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
      <div className='grid grid-cols-2 gap-4 lg:grid-cols-5'>
        {/* Capital input card */}
        <div className='rounded-lg border border-blue-500/30 bg-blue-500/5 p-4'>
          <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>
            Total Capital
          </p>
          <div className='mt-1 flex items-center gap-1'>
            <span className='text-sm font-medium'>RM</span>
            <input
              type='number'
              min={0}
              step={100}
              value={capitalInput}
              onChange={(e) => handleCapitalChange(e.target.value)}
              placeholder='10000'
              className='bg-background w-full rounded border px-2 py-1 font-mono text-lg font-bold'
            />
          </div>
          <div className='mt-1 flex items-center gap-2 text-xs'>
            <span className='text-muted-foreground'>
              Deployed {formatPrice(deployed)}
            </span>
            <span className='text-emerald-500 font-medium'>
              Avail {formatPrice(available)}
            </span>
            {saving && <span className='text-muted-foreground animate-pulse'>saving...</span>}
          </div>
        </div>
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

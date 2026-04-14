'use client';

import { useEffect, useState } from 'react';
import { formatPrice } from '@/lib/formatting';
import type { CapitalAllocationData, DiscountRow } from '../types';

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function categoryColor(cat: string | null): string {
  switch (cat) {
    case 'GREAT':
      return 'text-emerald-400 bg-emerald-500/10';
    case 'GOOD':
      return 'text-blue-400 bg-blue-500/10';
    case 'SKIP':
      return 'text-yellow-500 bg-yellow-500/10';
    case 'WORST':
      return 'text-red-500 bg-red-500/10';
    default:
      return 'text-muted-foreground bg-muted';
  }
}

function roiColor(meetsTarget: boolean, roi: number): string {
  if (roi <= 0) return 'text-red-500';
  if (meetsTarget) return 'text-emerald-400';
  return 'text-yellow-500';
}

function SummaryRow({
  label,
  value,
  color,
  bold,
}: {
  label: string;
  value: React.ReactNode;
  color?: string;
  bold?: boolean;
}) {
  return (
    <div className='flex items-center justify-between py-1'>
      <span className='text-muted-foreground text-sm'>{label}</span>
      <span
        className={`font-mono text-sm ${bold ? 'font-bold' : ''} ${color ?? 'text-foreground'}`}
      >
        {value}
      </span>
    </div>
  );
}

function DiscountTable({
  rows,
  currency,
  hasExistingPosition,
}: {
  rows: DiscountRow[];
  currency: string;
  hasExistingPosition: boolean;
}) {
  if (rows.length === 0) return null;

  // Find the first row that meets target for highlighting
  const firstMeetsIdx = rows.findIndex((r) => r.meets_target);

  return (
    <div className='mt-4'>
      <h3 className='mb-2 text-sm font-semibold'>Discount Guideline</h3>
      <div className='overflow-x-auto rounded-lg border'>
        <table className='w-full text-sm'>
          <thead>
            <tr className='bg-muted/50 text-muted-foreground border-b text-xs'>
              <th className='px-3 py-2 text-left'>Discount</th>
              <th className='px-3 py-2 text-right'>Entry Price</th>
              <th className='px-3 py-2 text-right'>Eff. Annual ROI</th>
              <th className='px-3 py-2 text-right'>Eff. 3yr Return</th>
              <th className='px-3 py-2 text-center'>20% APR?</th>
              <th className='px-3 py-2 text-right'>Capital</th>
              {hasExistingPosition && (
                <th className='px-3 py-2 text-right'>Remaining</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isTarget = i === firstMeetsIdx;
              const rowBg = isTarget
                ? 'bg-emerald-500/10 border-l-2 border-l-emerald-500'
                : row.meets_target
                  ? 'bg-emerald-500/5'
                  : '';
              return (
                <tr key={row.discount_pct} className={`border-b last:border-0 ${rowBg}`}>
                  <td className='px-3 py-1.5 font-mono'>
                    {row.discount_pct === 0 ? 'RRP' : `${(row.discount_pct * 100).toFixed(0)}%`}
                  </td>
                  <td className='px-3 py-1.5 text-right font-mono'>
                    {formatPrice(row.entry_price_cents, currency)}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono font-medium ${roiColor(row.meets_target, row.effective_annual_roi)}`}
                  >
                    {pct(row.effective_annual_roi)}
                  </td>
                  <td className='text-muted-foreground px-3 py-1.5 text-right font-mono'>
                    {pct(row.effective_3yr_return)}
                  </td>
                  <td className='px-3 py-1.5 text-center'>
                    {row.meets_target ? (
                      <span className='text-emerald-400 font-medium'>Yes</span>
                    ) : (
                      <span className='text-muted-foreground'>No</span>
                    )}
                  </td>
                  <td className='px-3 py-1.5 text-right font-mono'>
                    {row.recommended_amount_cents != null
                      ? formatPrice(row.recommended_amount_cents)
                      : '-'}
                  </td>
                  {hasExistingPosition && (
                    <td
                      className={`px-3 py-1.5 text-right font-mono ${
                        row.remaining_amount_cents === 0
                          ? 'text-muted-foreground'
                          : 'text-emerald-400'
                      }`}
                    >
                      {row.remaining_amount_cents != null
                        ? formatPrice(row.remaining_amount_cents)
                        : '-'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface CapitalAllocationPanelProps {
  setNumber: string;
}

export function CapitalAllocationPanel({ setNumber }: CapitalAllocationPanelProps) {
  const [data, setData] = useState<CapitalAllocationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetch(`/api/items/${setNumber}/kelly`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try {
            const json = JSON.parse(await res.text());
            if (json.error) msg = json.error;
          } catch { /* not JSON, use default */ }
          throw new Error(msg);
        }
        return res.json();
      })
      .then((json) => {
        if (json.success) setData(json.data);
        else setError(json.error ?? 'Failed to load allocation');
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber]);

  if (loading) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-muted-foreground text-sm'>Computing capital allocation...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-destructive text-sm'>{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const noRrp = data.rrp_cents == null;
  const noCategory = !data.ml_buy_category || !['GREAT', 'GOOD'].includes(data.ml_buy_category);
  const noCapital = data.total_capital_cents == null;
  const hasExistingPosition = data.existing_quantity > 0;
  const fullyAllocated =
    hasExistingPosition && data.remaining_amount_cents === 0;
  const avgCostCents =
    hasExistingPosition && data.existing_quantity > 0
      ? Math.round(data.existing_cost_cents / data.existing_quantity)
      : null;

  return (
    <div className='flex flex-col gap-2'>
      <div className='flex items-center justify-between'>
        <h2 className='text-lg font-semibold'>Capital Allocation</h2>
        {data.ml_buy_category && (
          <span
            className={`rounded-md px-2.5 py-1 text-xs font-semibold ${categoryColor(data.ml_buy_category)}`}
          >
            {data.ml_buy_category}
          </span>
        )}
      </div>

      {noRrp && (
        <div className='rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-4 py-3'>
          <p className='text-sm text-yellow-500'>
            RRP not available. Enrich this set to compute allocation.
          </p>
        </div>
      )}

      {!noRrp && noCategory && (
        <div className='rounded-lg border border-orange-500/30 bg-orange-500/5 px-4 py-3'>
          <p className='text-sm text-orange-500'>
            ML category is {data.ml_buy_category ?? 'unknown'} -- no allocation recommended for SKIP/WORST sets.
          </p>
        </div>
      )}

      {noCapital && (
        <div className='rounded-lg border border-blue-500/30 bg-blue-500/5 px-4 py-3'>
          <p className='text-sm text-blue-400'>
            Set your total capital on the Portfolio page to see allocation amounts.
          </p>
        </div>
      )}

      {/* Summary table */}
      <div className='rounded-lg border px-4 py-3'>
        <SummaryRow
          label='Entry Cost (RRP)'
          value={data.rrp_cents != null ? formatPrice(data.rrp_cents, data.rrp_currency) : '-'}
        />
        <SummaryRow
          label='Expected Annual ROI'
          value={data.annual_roi > 0 ? pct(data.annual_roi) : '-'}
          color={roiColor(data.meets_target, data.annual_roi)}
          bold
        />
        <SummaryRow
          label='3-Year Total Return'
          value={data.total_return_3yr > 0 ? pct(data.total_return_3yr) : '-'}
        />
        <SummaryRow
          label='Win Probability'
          value={data.win_probability > 0 ? pct(data.win_probability) : '-'}
          color={data.win_probability >= 0.9 ? 'text-emerald-400' : undefined}
        />

        <div className='my-1.5 border-t' />

        <SummaryRow
          label='Kelly Fraction (f*)'
          value={data.kelly_fraction > 0 ? pct(data.kelly_fraction) : '-'}
        />
        <SummaryRow
          label='Half-Kelly'
          value={data.half_kelly > 0 ? pct(data.half_kelly) : '-'}
        />
        <SummaryRow
          label='Position Cap'
          value={data.recommended_pct > 0 ? pct(data.recommended_pct) : '-'}
          color={data.recommended_pct >= 0.25 ? 'text-emerald-400' : undefined}
          bold
        />

        <div className='my-1.5 border-t' />

        <SummaryRow
          label='Portfolio Capital'
          value={data.total_capital_cents != null ? formatPrice(data.total_capital_cents) : 'Not set'}
        />
        <SummaryRow label='Deployed' value={formatPrice(data.deployed_cents)} />
        <SummaryRow
          label='Available'
          value={formatPrice(data.available_cents)}
          color='text-emerald-400'
        />

        {hasExistingPosition && (
          <>
            <div className='my-1.5 border-t' />
            <SummaryRow
              label='Current Position'
              value={`${data.existing_quantity} unit${data.existing_quantity === 1 ? '' : 's'}`}
              color='text-blue-400'
              bold
            />
            <SummaryRow
              label='Cost Basis'
              value={formatPrice(data.existing_cost_cents)}
            />
            {avgCostCents != null && (
              <SummaryRow
                label='Avg Cost / Unit'
                value={formatPrice(avgCostCents)}
              />
            )}
            {data.target_position_cents != null && (
              <SummaryRow
                label='Kelly Target Position'
                value={formatPrice(data.target_position_cents)}
              />
            )}
          </>
        )}

        {hasExistingPosition && data.remaining_amount_cents != null ? (
          <>
            <div className='my-1.5 border-t' />
            <div className='flex items-center justify-between py-1.5'>
              <span className='text-sm font-semibold'>
                {fullyAllocated ? 'Position Full' : 'Remaining Allocation'}
              </span>
              <span
                className={`font-mono text-xl font-bold ${
                  fullyAllocated
                    ? 'text-muted-foreground'
                    : data.meets_target
                      ? 'text-emerald-400'
                      : 'text-yellow-500'
                }`}
              >
                {formatPrice(data.remaining_amount_cents)}
              </span>
            </div>
            {fullyAllocated && (
              <p className='text-muted-foreground text-xs'>
                Existing position already meets the Kelly target for this set.
              </p>
            )}
          </>
        ) : (
          data.recommended_amount_cents != null && (
            <>
              <div className='my-1.5 border-t' />
              <div className='flex items-center justify-between py-1.5'>
                <span className='text-sm font-semibold'>Recommended Allocation</span>
                <span
                  className={`font-mono text-xl font-bold ${data.meets_target ? 'text-emerald-400' : 'text-yellow-500'}`}
                >
                  {formatPrice(data.recommended_amount_cents)}
                </span>
              </div>
            </>
          )
        )}

        {data.rrp_cents != null && data.expected_value_cents != null && (
          <>
            <div className='my-1.5 border-t' />
            <SummaryRow
              label='Expected 3yr Value (from RRP)'
              value={formatPrice(data.expected_value_cents, data.rrp_currency)}
              color={data.meets_target ? 'text-emerald-400' : 'text-yellow-500'}
            />
            <SummaryRow
              label='Target 3yr Value (20% APR)'
              value={
                data.target_value_cents != null
                  ? formatPrice(data.target_value_cents, data.rrp_currency)
                  : '-'
              }
              color='text-blue-400'
            />
          </>
        )}
      </div>

      {/* Discount guideline table */}
      {data.discount_table.length > 0 && (
        <DiscountTable
          rows={data.discount_table}
          currency={data.rrp_currency}
          hasExistingPosition={hasExistingPosition}
        />
      )}
    </div>
  );
}

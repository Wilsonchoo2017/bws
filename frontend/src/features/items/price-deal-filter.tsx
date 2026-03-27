'use client';

import { useState } from 'react';
import type { UnifiedItem } from './types';

interface PriceDealFilterProps {
  onFilterChange: (filterFn: ((items: UnifiedItem[]) => UnifiedItem[]) | null) => void;
}

const DEFAULT_THRESHOLD = 0;

export function PriceDealFilter({ onFilterChange }: PriceDealFilterProps) {
  const [enabled, setEnabled] = useState(false);
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);

  const applyFilter = (isEnabled: boolean, thresholdPct: number) => {
    if (!isEnabled) {
      onFilterChange(null);
      return;
    }

    onFilterChange((items) =>
      items.filter((item) => {
        const blNewCents = item.bricklink_new_cents;
        if (blNewCents === null) return false;

        const maxPrice = blNewCents * (1 - thresholdPct / 100);

        const truPrice = item.toysrus_price_cents;
        const shopeePrice = item.shopee_price_cents;

        return (
          (truPrice !== null && truPrice <= maxPrice) ||
          (shopeePrice !== null && shopeePrice <= maxPrice)
        );
      })
    );
  };

  const handleToggle = () => {
    const next = !enabled;
    setEnabled(next);
    applyFilter(next, threshold);
  };

  const handleThresholdChange = (value: string) => {
    const parsed = parseFloat(value);
    if (isNaN(parsed)) return;
    setThreshold(parsed);
    applyFilter(enabled, parsed);
  };

  return (
    <div className='bg-muted/50 flex items-center gap-4 rounded-lg border px-4 py-2.5'>
      <label className='flex cursor-pointer items-center gap-2 text-sm font-medium'>
        <input
          type='checkbox'
          checked={enabled}
          onChange={handleToggle}
          className='accent-primary h-4 w-4 rounded'
        />
        Deals Filter
      </label>

      {enabled && (
        <>
          <div className='bg-border h-5 w-px' />

          <label className='flex items-center gap-1.5 text-sm'>
            <span className='text-muted-foreground whitespace-nowrap'>
              Retail below BL New by
            </span>
            <input
              type='number'
              value={threshold}
              onChange={(e) => handleThresholdChange(e.target.value)}
              min={0}
              max={100}
              step={5}
              className='border-input bg-background w-16 rounded-md border px-2 py-1 text-center font-mono text-sm'
            />
            <span className='text-muted-foreground'>%</span>
          </label>
        </>
      )}
    </div>
  );
}

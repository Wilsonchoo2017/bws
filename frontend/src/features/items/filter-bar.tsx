'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { FILTER_GROUPS, type FilterKey } from './filter-utils';

const COHORT_KEYS = new Set([
  'cohort_half_year', 'cohort_theme', 'cohort_price_tier',
]);

interface FilterBarProps {
  activeFilters: ReadonlySet<FilterKey>;
  onToggle: (key: FilterKey) => void;
  onClearAll: () => void;
  dealThreshold: number;
  onDealThresholdChange: (value: number) => void;
  cohortThreshold: number;
  onCohortThresholdChange: (value: number) => void;
}

export function FilterBar({
  activeFilters,
  onToggle,
  onClearAll,
  dealThreshold,
  onDealThresholdChange,
  cohortThreshold,
  onCohortThresholdChange,
}: FilterBarProps) {
  const hasActive = activeFilters.size > 0;

  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap items-center gap-x-4 gap-y-2'>
        {FILTER_GROUPS.map((group) => (
          <div key={group.id} className='flex items-center gap-1.5'>
            <span className='text-muted-foreground text-[11px] font-medium uppercase tracking-wide'>
              {group.label}
            </span>
            <div className='flex items-center gap-1'>
              {group.filters.map((filter) => {
                const isActive = activeFilters.has(filter.key);
                return (
                  <Badge
                    key={filter.key}
                    variant={isActive ? 'default' : 'outline'}
                    className='cursor-pointer select-none px-2.5 py-1 text-xs hover:opacity-80'
                    onClick={() => onToggle(filter.key)}
                  >
                    {filter.label}
                  </Badge>
                );
              })}
            </div>
          </div>
        ))}

        {activeFilters.has('deal') && (
          <div className='flex items-center gap-1.5'>
            <span className='text-muted-foreground whitespace-nowrap text-xs'>
              below BL New by
            </span>
            <input
              type='number'
              value={dealThreshold}
              onChange={(e) => {
                const parsed = parseFloat(e.target.value);
                if (!isNaN(parsed)) onDealThresholdChange(parsed);
              }}
              min={0}
              max={100}
              step={5}
              className='border-input bg-transparent w-16 rounded-md border px-2 py-1 text-center font-mono text-sm shadow-xs'
            />
            <span className='text-muted-foreground text-xs'>%</span>
          </div>
        )}

        {[...activeFilters].some((k) => COHORT_KEYS.has(k)) && (
          <div className='flex items-center gap-1.5'>
            <span className='text-muted-foreground whitespace-nowrap text-xs'>
              min percentile
            </span>
            <input
              type='number'
              value={cohortThreshold}
              onChange={(e) => {
                const parsed = parseFloat(e.target.value);
                if (!isNaN(parsed)) onCohortThresholdChange(parsed);
              }}
              min={0}
              max={100}
              step={5}
              className='border-input bg-transparent w-16 rounded-md border px-2 py-1 text-center font-mono text-sm shadow-xs'
            />
          </div>
        )}

        {hasActive && (
          <Button
            variant='ghost'
            size='sm'
            onClick={onClearAll}
            className='text-muted-foreground text-xs'
          >
            Clear all
          </Button>
        )}
      </div>
    </div>
  );
}

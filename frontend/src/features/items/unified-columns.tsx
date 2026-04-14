import Link from 'next/link';
import type { ColumnDef, RowData } from '@tanstack/react-table';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface TableMeta<TData extends RowData> {
    toggleWatchlist?: (setNumber: string) => void;
    watchlistLoading?: Set<string>;
    enriching?: boolean;
    addToCart?: (setNumber: string) => void;
    cartLoading?: Set<string>;
    cartSetNumbers?: Set<string>;
    cartEntries?: Map<string, { set_number: string; source: string; added_at: string }>;
    removeFromCart?: (setNumber: string) => void;
    banFromCart?: (setNumber: string) => void;
  }
}

import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import type { UnifiedItem } from './types';
import { formatPrice } from './types';

export function PriceShimmer() {
  return <div className='bg-muted/50 h-4 w-14 animate-pulse rounded' />;
}

export function cohortColor(v: number | null): string {
  if (v === null) return 'text-muted-foreground';
  if (v >= 80) return 'text-emerald-400';
  if (v >= 65) return 'text-emerald-600 dark:text-emerald-500';
  if (v >= 50) return 'text-yellow-600 dark:text-yellow-400';
  if (v >= 35) return 'text-orange-500';
  return 'text-red-500';
}

export function CohortCell({ value }: { value: number | null }) {
  if (value == null) return <span className='text-muted-foreground'>-</span>;
  return (
    <span className={`font-mono text-sm font-semibold ${cohortColor(value)}`}>
      {value.toFixed(0)}
    </span>
  );
}

export const unifiedColumns: ColumnDef<UnifiedItem>[] = [
  {
    accessorKey: 'watchlist',
    header: '',
    cell: ({ row, table }) => {
      const isWatchlisted = row.original.watchlist;
      const onToggle = table.options.meta?.toggleWatchlist;
      const isLoading = table.options.meta?.watchlistLoading?.has(row.original.set_number);
      return (
        <button
          disabled={isLoading}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.(row.original.set_number);
          }}
          className={`text-lg transition-transform ${
            isLoading
              ? 'animate-pulse text-yellow-300'
              : isWatchlisted
                ? 'text-yellow-500 hover:scale-110'
                : 'text-muted-foreground/30 hover:text-yellow-400 hover:scale-110'
          }`}
          title={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
        >
          {isWatchlisted ? '\u2605' : '\u2606'}
        </button>
      );
    },
    size: 40,
    enableSorting: false,
  },
  {
    id: 'add_to_cart',
    header: '',
    cell: ({ row, table }) => {
      const setNumber = row.original.set_number;
      const inCart = table.options.meta?.cartSetNumbers?.has(setNumber);
      const isLoading = table.options.meta?.cartLoading?.has(setNumber);
      const onAdd = table.options.meta?.addToCart;
      if (inCart) {
        return (
          <span
            className='text-emerald-600 dark:text-emerald-400 text-xs font-semibold'
            title='In cart'
          >
            In Cart
          </span>
        );
      }
      return (
        <button
          disabled={isLoading}
          onClick={(e) => {
            e.stopPropagation();
            onAdd?.(setNumber);
          }}
          className={`text-xs px-1.5 py-0.5 rounded transition-colors ${
            isLoading
              ? 'animate-pulse text-muted-foreground'
              : 'text-muted-foreground hover:text-primary hover:bg-primary/10'
          }`}
          title='Add to cart'
        >
          {isLoading ? '...' : '+ Cart'}
        </button>
      );
    },
    size: 65,
    enableSorting: false,
  },
  {
    accessorKey: 'image_url',
    header: '',
    cell: ({ row }) => {
      const url = row.getValue('image_url') as string | null;
      return url ? (
        <img src={url} alt='' className='h-10 w-10 rounded object-cover' />
      ) : (
        <div className='bg-muted h-10 w-10 rounded' />
      );
    },
    size: 60,
    enableSorting: false
  },
  {
    accessorKey: 'set_number',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Set #' />
    ),
    cell: ({ row }) => (
      <Link
        href={`/items/${row.getValue('set_number')}`}
        className='text-primary font-mono text-sm hover:underline'
      >
        {row.getValue('set_number')}
      </Link>
    ),
    size: 90
  },
  {
    accessorKey: 'title',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Title' />
    ),
    cell: ({ row }) => (
      <span className='max-w-[300px] truncate font-medium'>
        {row.getValue('title') ?? '-'}
      </span>
    ),
    size: 300
  },
  {
    accessorKey: 'year_released',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Year' />
    ),
    cell: ({ row }) => row.getValue('year_released') ?? '-',
    size: 70
  },
  {
    id: 'retirement',
    accessorKey: 'year_retired',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Retirement' />
    ),
    cell: ({ row }) => {
      const yr = row.original.year_retired;
      const soon = row.original.retiring_soon;
      const retiredDate = row.original.retired_date;
      const availability = row.original.availability;
      if (yr) {
        const label = retiredDate ?? String(yr);
        return (
          <span className='text-orange-600 dark:text-orange-400' title={availability ?? 'Retired'}>{label}</span>
        );
      }
      if (soon) {
        return (
          <span className='rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-400'>SOON</span>
        );
      }
      if (availability && availability.toLowerCase() === 'retired') {
        return (
          <span className='text-orange-600 dark:text-orange-400' title='Retired (no date)'>Retired</span>
        );
      }
      return <span className='text-muted-foreground'>-</span>;
    },
    size: 90
  },
  {
    accessorKey: 'liquidity_score',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Liq' />
    ),
    cell: ({ row, table }) => {
      const score = row.getValue('liquidity_score') as number | null;
      if (table.options.meta?.enriching && score == null) return <PriceShimmer />;
      if (score == null) return <span className='text-muted-foreground'>-</span>;
      const color =
        score >= 70 ? 'text-emerald-400' :
        score >= 50 ? 'text-emerald-600 dark:text-emerald-500' :
        score >= 30 ? 'text-yellow-600 dark:text-yellow-400' :
        'text-red-500';
      return (
        <span
          className={`font-mono text-sm font-semibold ${color}`}
          title='vol 50% + consistency 38% + listing ratio 12%'
        >
          {score.toFixed(0)}
        </span>
      );
    },
    size: 55
  },
  {
    accessorKey: 'liq_cohort_half_year',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='L:HY' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('liq_cohort_half_year') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'liq_cohort_theme',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='L:Thm' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('liq_cohort_theme') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'liq_cohort_price_tier',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='L:$$' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('liq_cohort_price_tier') as number | null} />,
    size: 55
  },
  {
    id: 'ml_buy_category',
    accessorKey: 'ml_buy_category',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Buy' />
    ),
    cell: ({ row, table }) => {
      const category = row.original.ml_buy_category;
      if (table.options.meta?.enriching && category == null) return <PriceShimmer />;
      if (category == null) return <span className='text-muted-foreground'>-</span>;
      const styles: Record<string, { label: string; cls: string }> = {
        GREAT: { label: 'GREAT', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
        GOOD: { label: 'GOOD', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' },
        SKIP: { label: 'SKIP', cls: 'bg-neutral-100 text-neutral-500 dark:bg-neutral-800/40 dark:text-neutral-400' },
        WORST: { label: 'WORST', cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
      };
      const style = styles[category] ?? styles.SKIP;
      return (
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold leading-none ${style.cls}`}>
          {style.label}
        </span>
      );
    },
    sortingFn: (rowA, rowB) => {
      const order: Record<string, number> = { GREAT: 4, GOOD: 3, SKIP: 2, WORST: 1 };
      const a = order[rowA.original.ml_buy_category ?? ''] ?? 0;
      const b = order[rowB.original.ml_buy_category ?? ''] ?? 0;
      return a - b;
    },
    size: 65
  },
  {
    id: 'ml_avoid',
    accessorKey: 'ml_avoid_probability',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Avoid' />
    ),
    cell: ({ row, table }) => {
      const prob = row.original.ml_avoid_probability;
      if (table.options.meta?.enriching && prob == null) return <PriceShimmer />;
      if (prob == null) return <span className='text-muted-foreground'>-</span>;
      const isAvoid = row.original.ml_buy_category === 'WORST';
      if (isAvoid) {
        return (
          <span
            className='rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300'
            title={`P(avoid) = ${(prob * 100).toFixed(1)}%`}
          >
            AVOID
          </span>
        );
      }
      return (
        <span
          className='text-muted-foreground text-xs'
          title={`P(avoid) = ${(prob * 100).toFixed(1)}%`}
        >
          Neutral
        </span>
      );
    },
    size: 60
  },
  {
    accessorKey: 'cohort_half_year',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:HY' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_half_year') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'cohort_theme',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:Thm' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_theme') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'cohort_price_tier',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:$$' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_price_tier') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'rrp_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='RRP' />
    ),
    cell: ({ row }) => {
      const cents = row.getValue('rrp_cents') as number | null;
      if (!cents) return <span className='text-muted-foreground'>-</span>;
      return (
        <span className='font-mono text-sm'>
          {formatPrice(cents, row.original.rrp_currency)}
        </span>
      );
    },
    size: 100
  },
  {
    id: 'best_price',
    accessorKey: 'shopee_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Best Price' />
    ),
    cell: ({ row, table }) => {
      const sources: { label: string; cents: number | null; currency: string; url: string | null }[] = [
        { label: 'Shopee', cents: row.original.shopee_price_cents, currency: row.original.shopee_currency ?? 'MYR', url: row.original.shopee_url },
        { label: 'TRU', cents: row.original.toysrus_price_cents, currency: row.original.toysrus_currency ?? 'MYR', url: row.original.toysrus_url },
        { label: 'MU', cents: row.original.mightyutan_price_cents, currency: row.original.mightyutan_currency ?? 'MYR', url: row.original.mightyutan_url },
      ];
      const available = sources.filter((s) => s.cents != null && s.cents > 0) as { label: string; cents: number; currency: string; url: string | null }[];
      if (table.options.meta?.enriching && available.length === 0) return <PriceShimmer />;
      if (available.length === 0) return <span className='text-muted-foreground'>-</span>;
      const best = available.reduce((a, b) => (a.cents <= b.cents ? a : b));
      const formatted = formatPrice(best.cents, best.currency);
      return (
        <div className='flex flex-col gap-0.5'>
          {best.url ? (
            <a
              href={best.url}
              target='_blank'
              rel='noopener noreferrer'
              className='text-primary font-mono text-sm hover:underline'
            >
              {formatted}
            </a>
          ) : (
            <span className='font-mono text-sm'>{formatted}</span>
          )}
          <span className='text-muted-foreground text-[10px] leading-tight'>
            {best.label}
            {available.length > 1 && (
              <span className='ml-0.5 text-[9px]'>
                ({available.length} sources)
              </span>
            )}
          </span>
        </div>
      );
    },
    sortingFn: (rowA, rowB) => {
      const getMin = (row: typeof rowA) => {
        const vals = [row.original.shopee_price_cents, row.original.toysrus_price_cents, row.original.mightyutan_price_cents]
          .filter((v): v is number => v != null && v > 0);
        return vals.length > 0 ? Math.min(...vals) : Infinity;
      };
      return getMin(rowA) - getMin(rowB);
    },
    size: 130
  },
  {
    accessorKey: 'bricklink_new_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='BL New' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('bricklink_new_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      return (
        <span className='font-mono text-sm'>
          {formatPrice(cents, row.original.bricklink_new_currency)}
        </span>
      );
    },
    size: 100
  },
  {
    accessorKey: 'updated_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Updated' />
    ),
    cell: ({ row }) => {
      const date = row.getValue('updated_at') as string | null;
      if (!date) return <span className='text-muted-foreground'>-</span>;
      return (
        <span className='text-muted-foreground text-xs'>
          {new Date(date).toLocaleDateString()}
        </span>
      );
    },
    size: 100
  }
];

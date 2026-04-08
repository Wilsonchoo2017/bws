import Link from 'next/link';
import type { ColumnDef, RowData } from '@tanstack/react-table';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface TableMeta<TData extends RowData> {
    toggleWatchlist?: (setNumber: string) => void;
    watchlistLoading?: Set<string>;
    enriching?: boolean;
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
    accessorKey: 'liq_cohort_piece_group',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='L:Pc' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('liq_cohort_piece_group') as number | null} />,
    size: 55
  },
  {
    accessorKey: 'ml_growth_pct',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='ML Growth' />
    ),
    cell: ({ row, table }) => {
      const growth = row.getValue('ml_growth_pct') as number | null;
      if (table.options.meta?.enriching && growth == null) return <PriceShimmer />;
      if (growth == null || Number.isNaN(growth)) return <span className='text-muted-foreground'>-</span>;
      const color =
        growth >= 15 ? 'text-emerald-600 dark:text-emerald-500' :
        growth >= 10 ? 'text-green-600 dark:text-green-400' :
        growth >= 5 ? 'text-yellow-600 dark:text-yellow-400' :
        'text-red-500';
      const avoid = row.original.ml_avoid_probability;
      const isAvoid = avoid != null && avoid >= 0.5;
      const isBuy = !isAvoid && growth >= 8;
      const signalLabel = isAvoid ? 'AVOID' : isBuy ? 'BUY' : 'HOLD';
      const signalClass = isAvoid
        ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
        : isBuy
          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
          : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300';
      return (
        <div className='flex flex-col gap-0.5'>
          <div className='flex items-center gap-1'>
            <span className={`font-mono text-sm font-semibold ${color}`}>
              +{growth.toFixed(1)}%
            </span>
            <span className={`rounded px-1 text-[9px] font-bold ${signalClass}`}>
              {signalLabel}
            </span>
          </div>
        </div>
      );
    },
    size: 95
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
    accessorKey: 'cohort_year',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:Yr' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_year') as number | null} />,
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
    accessorKey: 'cohort_year_theme',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:YT' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_year_theme') as number | null} />,
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
    accessorKey: 'cohort_piece_group',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='C:Pc' />
    ),
    cell: ({ row }) => <CohortCell value={row.getValue('cohort_piece_group') as number | null} />,
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
    accessorKey: 'shopee_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Shopee' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('shopee_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      const url = row.original.shopee_url;
      const shopName = row.original.shopee_shop_name;
      const shopCount = row.original.shopee_shop_count ?? 0;
      const formatted = formatPrice(cents, 'MYR');
      if (!cents) return <span className='text-muted-foreground'>-</span>;
      return (
        <div className='flex flex-col gap-0.5'>
          {url ? (
            <a
              href={url}
              target='_blank'
              rel='noopener noreferrer'
              className='text-primary font-mono text-sm hover:underline'
            >
              {formatted}
            </a>
          ) : (
            <span className='font-mono text-sm'>{formatted}</span>
          )}
          {shopName && (
            <span className='text-muted-foreground truncate text-[10px] leading-tight max-w-[120px]'>
              {shopName}
              {shopCount > 1 && (
                <span className='ml-0.5 text-[9px]'>+{shopCount - 1}</span>
              )}
            </span>
          )}
        </div>
      );
    },
    size: 130
  },
  {
    accessorKey: 'toysrus_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='TRU' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('toysrus_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      const url = row.original.toysrus_url;
      const formatted = formatPrice(cents, 'MYR');
      if (!cents) return <span className='text-muted-foreground'>-</span>;
      return url ? (
        <a
          href={url}
          target='_blank'
          rel='noopener noreferrer'
          className='text-primary font-mono text-sm hover:underline'
        >
          {formatted}
        </a>
      ) : (
        <span className='font-mono text-sm'>{formatted}</span>
      );
    },
    size: 110
  },
  {
    accessorKey: 'mightyutan_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='MU' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('mightyutan_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      const url = row.original.mightyutan_url;
      const formatted = formatPrice(cents, 'MYR');
      if (!cents) return <span className='text-muted-foreground'>-</span>;
      return url ? (
        <a
          href={url}
          target='_blank'
          rel='noopener noreferrer'
          className='text-primary font-mono text-sm hover:underline'
        >
          {formatted}
        </a>
      ) : (
        <span className='font-mono text-sm'>{formatted}</span>
      );
    },
    size: 110
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

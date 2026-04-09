'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { DataTable } from '@/components/ui/table/data-table';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import { Badge } from '@/components/ui/badge';
import { formatPrice } from '@/lib/formatting';
import { useFetchData } from '@/lib/hooks/use-fetch-data';
import type { Holding, ForwardReturn } from './types';

type HoldingWithFR = Holding & {
  forward_annual_return?: number | null;
  decision?: string;
  price_source?: string;
  exceeds_target?: boolean;
  exceeds_hurdle?: boolean;
};

function ReturnBadge({ decision }: { decision?: string }) {
  if (!decision) return <span className='text-muted-foreground text-xs'>-</span>;
  const variant =
    decision === 'SELL'
      ? 'destructive'
      : decision === 'BUY'
        ? 'default'
        : 'secondary';
  return <Badge variant={variant}>{decision}</Badge>;
}

const columns: ColumnDef<HoldingWithFR>[] = [
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
    enableSorting: false,
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
    size: 90,
  },
  {
    accessorKey: 'title',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Title' />
    ),
    cell: ({ row }) => (
      <span className='max-w-[200px] truncate font-medium'>
        {row.getValue('title') ?? '-'}
      </span>
    ),
    size: 200,
  },
  {
    accessorKey: 'quantity',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Qty' />
    ),
    cell: ({ row }) => (
      <span className='font-mono'>{row.getValue('quantity')}</span>
    ),
    size: 60,
  },
  {
    accessorKey: 'avg_cost_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Avg Cost' />
    ),
    cell: ({ row }) => (
      <span className='font-mono text-sm'>
        {formatPrice(row.getValue('avg_cost_cents'))}
      </span>
    ),
    size: 100,
  },
  {
    accessorKey: 'market_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Market' />
    ),
    cell: ({ row }) => (
      <span className='font-mono text-sm'>
        {formatPrice(row.getValue('market_price_cents'))}
      </span>
    ),
    size: 100,
  },
  {
    accessorKey: 'listing_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Listing' />
    ),
    cell: ({ row }) => {
      const price = row.getValue('listing_price_cents') as number | null;
      return price ? (
        <span className='font-mono text-sm'>
          {formatPrice(price)}
        </span>
      ) : (
        <span className='text-muted-foreground text-xs'>-</span>
      );
    },
    size: 100,
  },
  {
    accessorKey: 'current_value_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Value' />
    ),
    cell: ({ row }) => (
      <span className='font-mono text-sm font-medium'>
        {formatPrice(row.getValue('current_value_cents'))}
      </span>
    ),
    size: 110,
  },
  {
    accessorKey: 'unrealized_pl_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='P&L' />
    ),
    cell: ({ row }) => {
      const pl = row.getValue('unrealized_pl_cents') as number;
      const pct = row.original.unrealized_pl_pct;
      const color =
        pl > 0 ? 'text-green-600' : pl < 0 ? 'text-red-600' : '';
      const sign = pl > 0 ? '+' : '';
      return (
        <div className={`font-mono text-sm ${color}`}>
          <div>{sign}{formatPrice(pl)}</div>
          <div className='text-xs opacity-70'>{sign}{pct.toFixed(1)}%</div>
        </div>
      );
    },
    size: 110,
  },
  {
    accessorKey: 'forward_annual_return',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Fwd Return' />
    ),
    cell: ({ row }) => {
      const ret = row.getValue('forward_annual_return') as number | null | undefined;
      if (ret == null) return <span className='text-muted-foreground text-xs'>-</span>;
      const pct = (ret * 100).toFixed(1);
      const color =
        ret >= 0.5 ? 'text-green-600' : ret >= 0.2 ? 'text-yellow-600' : 'text-red-600';
      const sign = ret > 0 ? '+' : '';
      return (
        <div className={`font-mono text-sm ${color}`}>
          {sign}{pct}%
          <div className='text-muted-foreground text-xs'>
            {row.original.price_source ?? ''}
          </div>
        </div>
      );
    },
    size: 100,
  },
  {
    accessorKey: 'decision',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Action' />
    ),
    cell: ({ row }) => <ReturnBadge decision={row.getValue('decision') as string | undefined} />,
    size: 80,
  },
];

export function HoldingsTable() {
  const { data: holdings, loading } = useFetchData<Holding>('/api/portfolio/holdings');
  const { data: forwardReturns } = useFetchData<ForwardReturn>('/api/portfolio/forward-returns');
  const [sorting, setSorting] = useState<SortingState>([]);

  const data = useMemo(() => {
    if (!forwardReturns.length) return holdings as HoldingWithFR[];
    const frMap = new Map(forwardReturns.map((fr) => [fr.set_number, fr]));
    return holdings.map((h) => {
      const fr = frMap.get(h.set_number);
      return {
        ...h,
        forward_annual_return: fr?.forward_annual_return,
        decision: fr?.decision,
        price_source: fr?.price_source,
        exceeds_target: fr?.exceeds_target,
        exceeds_hurdle: fr?.exceeds_hurdle,
      } as HoldingWithFR;
    });
  }, [holdings, forwardReturns]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });

  if (loading) {
    return <div className='text-muted-foreground py-8 text-center text-sm'>Loading holdings...</div>;
  }

  if (data.length === 0) {
    return (
      <div className='text-muted-foreground py-8 text-center text-sm'>
        No holdings yet. Record a BUY transaction to see your portfolio here.
      </div>
    );
  }

  return <DataTable table={table} />;
}

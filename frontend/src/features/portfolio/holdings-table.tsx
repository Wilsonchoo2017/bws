'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
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
import type { Holding } from './types';

function formatRM(cents: number | null): string {
  if (cents === null) return '-';
  return `RM${(cents / 100).toFixed(2)}`;
}

const columns: ColumnDef<Holding>[] = [
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
    accessorKey: 'condition',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Cond.' />
    ),
    cell: ({ row }) => (
      <Badge variant={row.getValue('condition') === 'new' ? 'default' : 'secondary'}>
        {row.getValue('condition')}
      </Badge>
    ),
    size: 70,
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
        {formatRM(row.getValue('avg_cost_cents'))}
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
        {formatRM(row.getValue('market_price_cents'))}
      </span>
    ),
    size: 100,
  },
  {
    accessorKey: 'current_value_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Value' />
    ),
    cell: ({ row }) => (
      <span className='font-mono text-sm font-medium'>
        {formatRM(row.getValue('current_value_cents'))}
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
          <div>{sign}{formatRM(pl)}</div>
          <div className='text-xs opacity-70'>{sign}{pct.toFixed(1)}%</div>
        </div>
      );
    },
    size: 110,
  },
];

export function HoldingsTable() {
  const [data, setData] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [sorting, setSorting] = useState<SortingState>([]);

  useEffect(() => {
    fetch('/api/portfolio/holdings')
      .then((r) => r.json())
      .then((d) => {
        if (d.success) setData(d.data);
      })
      .finally(() => setLoading(false));
  }, []);

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

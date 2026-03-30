'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
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
import { Button } from '@/components/ui/button';
import type { Transaction } from './types';

function formatRM(cents: number): string {
  return `RM${(cents / 100).toFixed(2)}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function TransactionsTable() {
  const [data, setData] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [sorting, setSorting] = useState<SortingState>([]);

  const fetchData = () => {
    setLoading(true);
    fetch('/api/portfolio/transactions?limit=500')
      .then((r) => r.json())
      .then((d) => {
        if (d.success) setData(d.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleDelete = async (id: number) => {
    const res = await fetch(`/api/portfolio/transactions/${id}`, {
      method: 'DELETE',
    });
    const result = await res.json();
    if (result.success) {
      setData((prev) => prev.filter((t) => t.id !== id));
    }
  };

  const columns: ColumnDef<Transaction>[] = [
    {
      accessorKey: 'txn_date',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title='Date' />
      ),
      cell: ({ row }) => (
        <span className='text-sm'>{formatDate(row.getValue('txn_date'))}</span>
      ),
      size: 110,
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
        <span className='max-w-[200px] truncate text-sm'>
          {row.getValue('title') ?? '-'}
        </span>
      ),
      size: 200,
    },
    {
      accessorKey: 'txn_type',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title='Type' />
      ),
      cell: ({ row }) => {
        const type = row.getValue('txn_type') as string;
        return (
          <Badge variant={type === 'BUY' ? 'default' : 'secondary'}>
            {type}
          </Badge>
        );
      },
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
      accessorKey: 'price_cents',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title='Price/Unit' />
      ),
      cell: ({ row }) => (
        <span className='font-mono text-sm'>
          {formatRM(row.getValue('price_cents'))}
        </span>
      ),
      size: 100,
    },
    {
      id: 'total',
      header: 'Total',
      cell: ({ row }) => (
        <span className='font-mono text-sm font-medium'>
          {formatRM(row.original.price_cents * row.original.quantity)}
        </span>
      ),
      size: 110,
    },
    {
      accessorKey: 'condition',
      header: 'Cond.',
      cell: ({ row }) => (
        <span className='text-xs capitalize'>{row.getValue('condition')}</span>
      ),
      size: 60,
    },
    {
      accessorKey: 'notes',
      header: 'Notes',
      cell: ({ row }) => (
        <span className='text-muted-foreground max-w-[150px] truncate text-xs'>
          {row.getValue('notes') ?? ''}
        </span>
      ),
      size: 150,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <Button
          variant='ghost'
          size='sm'
          className='text-destructive h-7 text-xs'
          onClick={() => handleDelete(row.original.id)}
        >
          Delete
        </Button>
      ),
      size: 70,
    },
  ];

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
    return (
      <div className='text-muted-foreground py-8 text-center text-sm'>
        Loading transactions...
      </div>
    );
  }

  return <DataTable table={table} />;
}

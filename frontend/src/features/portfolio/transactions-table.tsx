'use client';

import Link from 'next/link';
import { useCallback, useState } from 'react';
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
import { formatPrice } from '@/lib/formatting';
import { useFetchData } from '@/lib/hooks/use-fetch-data';
import { AddBillForm } from './add-bill-form';
import type { Transaction } from './types';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function TransactionsTable() {
  const { data, loading, setData, refetch } = useFetchData<Transaction>('/api/portfolio/transactions?limit=500');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [editingBillId, setEditingBillId] = useState<string | null>(null);

  const handleDelete = async (id: number) => {
    const res = await fetch(`/api/portfolio/transactions/${id}`, {
      method: 'DELETE',
    });
    const result = await res.json();
    if (result.success) {
      setData((prev) => prev.filter((t) => t.id !== id));
    }
  };

  const handleEdit = useCallback((txn: Transaction) => {
    if (txn.bill_id) {
      setEditingBillId(txn.bill_id);
    }
  }, []);

  const handleBillSaved = useCallback(() => {
    setEditingBillId(null);
    refetch();
  }, [refetch]);

  const billTransactions = editingBillId
    ? data.filter((t) => t.bill_id === editingBillId)
    : [];

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
        <div className='flex items-center gap-1'>
          <Link
            href={`/items/${row.getValue('set_number')}`}
            className='text-primary font-mono text-sm hover:underline'
          >
            {row.getValue('set_number')}
          </Link>
          {row.original.bill_id && (
            <span
              className='text-muted-foreground text-[10px]'
              title={`Bill: ${row.original.bill_id}`}
            >
              Bill
            </span>
          )}
        </div>
      ),
      size: 110,
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
          {formatPrice(row.getValue('price_cents'))}
        </span>
      ),
      size: 100,
    },
    {
      id: 'total',
      header: 'Total',
      cell: ({ row }) => (
        <span className='font-mono text-sm font-medium'>
          {formatPrice(row.original.price_cents * row.original.quantity)}
        </span>
      ),
      size: 110,
    },
    {
      accessorKey: 'supplier',
      header: 'Supplier',
      cell: ({ row }) => (
        <span className='text-muted-foreground max-w-[100px] truncate text-xs'>
          {row.getValue('supplier') ?? ''}
        </span>
      ),
      size: 100,
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
        <div className='flex gap-1'>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 text-xs'
            onClick={() => handleEdit(row.original)}
          >
            Edit Bill
          </Button>
          <Button
            variant='ghost'
            size='sm'
            className='text-destructive h-7 text-xs'
            onClick={() => handleDelete(row.original.id)}
          >
            Delete
          </Button>
        </div>
      ),
      size: 130,
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

  return (
    <div className='flex min-h-0 flex-1 flex-col space-y-4'>
      {editingBillId && billTransactions.length > 0 && (
        <AddBillForm
          key={editingBillId}
          editData={{ billId: editingBillId, transactions: billTransactions }}
          onSuccess={handleBillSaved}
          onCancel={() => setEditingBillId(null)}
        />
      )}
      <DataTable table={table} />
    </div>
  );
}

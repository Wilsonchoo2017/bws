'use client';

import { useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type SortingState
} from '@tanstack/react-table';
import { DataTable } from '@/components/ui/table/data-table';
import { useFetchData } from '@/lib/hooks/use-fetch-data';
import { columns } from './columns';
import type { ItemWithAnalysis } from './types';

export function ItemsTable() {
  const { data, loading, error } = useFetchData<ItemWithAnalysis>('/api/items');
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel()
  });

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading items...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-destructive'>{error}</p>
      </div>
    );
  }

  return <DataTable table={table} />;
}

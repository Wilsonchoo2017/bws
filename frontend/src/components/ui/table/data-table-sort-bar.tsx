'use client';

import { ArrowDownIcon, ArrowUpIcon } from 'lucide-react';
import type { Table as TanstackTable } from '@tanstack/react-table';

interface DataTableSortBarProps<TData> {
  table: TanstackTable<TData>;
}

function formatColumnId(id: string): string {
  return id
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DataTableSortBar<TData>({ table }: DataTableSortBarProps<TData>) {
  const sorting = table.getState().sorting;
  if (sorting.length === 0) return null;

  const columnLookup = new Map(
    table.getAllColumns().map((col) => [col.id, col])
  );

  return (
    <div className='flex items-center gap-1.5'>
      <span className='text-muted-foreground text-xs'>Sort:</span>
      {sorting.map((sort, i) => {
        const col = columnLookup.get(sort.id);
        const label =
          (typeof col?.columnDef.header === 'string'
            ? col.columnDef.header
            : null) ?? formatColumnId(sort.id);
        return (
          <button
            key={sort.id}
            onClick={() => col?.clearSorting()}
            className='bg-muted hover:bg-muted/70 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs transition-colors'
            title={`Remove ${label} sort`}
          >
            <span className='text-muted-foreground text-[10px]'>{i + 1}</span>
            {label}
            {sort.desc ? (
              <ArrowDownIcon className='size-3' />
            ) : (
              <ArrowUpIcon className='size-3' />
            )}
            <span className='text-muted-foreground ml-0.5'>&times;</span>
          </button>
        );
      })}
      {sorting.length > 1 && (
        <button
          onClick={() => table.resetSorting()}
          className='text-muted-foreground hover:text-foreground text-xs underline'
        >
          Clear all
        </button>
      )}
    </div>
  );
}

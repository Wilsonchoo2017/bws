'use client';

import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import type { ItemWithAnalysis } from './types';

const ACTION_STYLES: Record<string, string> = {
  strong_buy:
    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800',
  buy: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
  hold: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800',
  skip: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800'
};

const STATUS_STYLES: Record<string, string> = {
  active:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800',
  paused:
    'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800',
  stopped:
    'bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400 border-gray-200 dark:border-gray-800',
  archived:
    'bg-slate-100 text-slate-600 dark:bg-slate-900/30 dark:text-slate-400 border-slate-200 dark:border-slate-800'
};

export const columns: ColumnDef<ItemWithAnalysis>[] = [
  {
    accessorKey: 'item_id',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Item ID' />
    ),
    cell: ({ row }) => (
      <span className='font-mono text-xs'>{row.getValue('item_id')}</span>
    ),
    size: 120
  },
  {
    accessorKey: 'title',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Title' />
    ),
    cell: ({ row }) => (
      <span className='max-w-[300px] truncate font-medium'>
        {row.getValue('title')}
      </span>
    ),
    size: 300
  },
  {
    accessorKey: 'item_type',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Type' />
    ),
    size: 80
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
    accessorKey: 'watch_status',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Status' />
    ),
    cell: ({ row }) => {
      const status = row.getValue('watch_status') as string;
      return (
        <Badge variant='outline' className={STATUS_STYLES[status] ?? ''}>
          {status}
        </Badge>
      );
    },
    size: 100
  },
  {
    accessorKey: 'action',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Action' />
    ),
    cell: ({ row }) => {
      const action = row.getValue('action') as string | null;
      if (!action) return <span className='text-muted-foreground'>-</span>;
      return (
        <Badge variant='outline' className={ACTION_STYLES[action] ?? ''}>
          {action.replace('_', ' ')}
        </Badge>
      );
    },
    size: 110
  },
  {
    accessorKey: 'overall_score',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Score' />
    ),
    cell: ({ row }) => {
      const score = row.getValue('overall_score') as number | null;
      if (score === null) return <span className='text-muted-foreground'>-</span>;
      return <span className='font-mono tabular-nums'>{score}</span>;
    },
    size: 70
  },
  {
    accessorKey: 'confidence',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Conf.' />
    ),
    cell: ({ row }) => {
      const conf = row.getValue('confidence') as number | null;
      if (conf === null) return <span className='text-muted-foreground'>-</span>;
      return <span className='font-mono tabular-nums'>{conf}%</span>;
    },
    size: 70
  },
  {
    accessorKey: 'last_scraped_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Last Scraped' />
    ),
    cell: ({ row }) => {
      const date = row.getValue('last_scraped_at') as string | null;
      if (!date) return <span className='text-muted-foreground'>Never</span>;
      return (
        <span className='text-muted-foreground text-xs'>
          {new Date(date).toLocaleDateString()}
        </span>
      );
    },
    size: 110
  }
];

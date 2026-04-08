import type { ColumnDef } from '@tanstack/react-table';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import type { PriceRecord } from '../types';
import { formatPrice } from '../types';
import { SOURCE_LABELS, SOURCE_COLORS } from './item-detail';

export const priceColumns: ColumnDef<PriceRecord>[] = [
  {
    accessorKey: 'source',
    id: 'source',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Source' />
    ),
    cell: ({ row }) => (
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-medium ${SOURCE_COLORS[row.original.source] ?? ''}`}
      >
        {SOURCE_LABELS[row.original.source] ?? row.original.source}
      </span>
    ),
    sortingFn: (rowA, rowB) => {
      const a = (SOURCE_LABELS[rowA.original.source] ?? rowA.original.source).toLowerCase();
      const b = (SOURCE_LABELS[rowB.original.source] ?? rowB.original.source).toLowerCase();
      return a < b ? -1 : a > b ? 1 : 0;
    },
    size: 140,
  },
  {
    accessorKey: 'price_cents',
    id: 'price',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Price' />
    ),
    cell: ({ row }) => (
      <span className='whitespace-nowrap font-mono'>
        {formatPrice(row.original.price_cents, row.original.currency)}
      </span>
    ),
    size: 110,
  },
  {
    id: 'listing',
    header: 'Listing',
    cell: ({ row }) => {
      const { url, title } = row.original;
      if (url) {
        return (
          <a
            href={url}
            target='_blank'
            rel='noopener noreferrer'
            className='text-primary hover:underline'
          >
            {title ?? 'View'}
          </a>
        );
      }
      return <span className='text-muted-foreground'>{title ?? '-'}</span>;
    },
    enableSorting: false,
    size: 200,
  },
  {
    accessorKey: 'shop_name',
    id: 'seller',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Seller' />
    ),
    cell: ({ row }) => (
      <span className='text-muted-foreground'>
        {row.original.shop_name ?? '-'}
      </span>
    ),
    size: 140,
  },
  {
    accessorKey: 'recorded_at',
    id: 'date',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Date' />
    ),
    cell: ({ row }) => (
      <span className='text-muted-foreground whitespace-nowrap text-xs'>
        {new Date(row.original.recorded_at).toLocaleString()}
      </span>
    ),
    size: 160,
  },
];

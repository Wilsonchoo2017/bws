'use client';

import { useEffect, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState
} from '@tanstack/react-table';
import { DataTable } from '@/components/ui/table/data-table';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';

interface ShopeeItem {
  title: string;
  price_display: string;
  price_cents: number | null;
  sold_count: string | null;
  rating: string | null;
  shop_name: string | null;
  product_url: string | null;
  image_url: string | null;
  source_url: string | null;
  scraped_at: string | null;
}

const columns: ColumnDef<ShopeeItem>[] = [
  {
    accessorKey: 'image_url',
    header: '',
    cell: ({ row }) => {
      const url = row.getValue('image_url') as string | null;
      return url ? (
        <img src={url} alt='' className='h-10 w-10 rounded object-cover' />
      ) : null;
    },
    size: 60,
    enableSorting: false
  },
  {
    accessorKey: 'title',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Title' />
    ),
    cell: ({ row }) => {
      const url = row.original.product_url;
      const title = row.getValue('title') as string;
      return url ? (
        <a
          href={url}
          target='_blank'
          rel='noopener noreferrer'
          className='text-primary max-w-[400px] truncate hover:underline'
        >
          {title}
        </a>
      ) : (
        <span className='max-w-[400px] truncate'>{title}</span>
      );
    },
    size: 400
  },
  {
    accessorKey: 'price_display',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Price' />
    ),
    cell: ({ row }) => (
      <span className='font-mono'>{row.getValue('price_display')}</span>
    ),
    sortingFn: (a, b) => {
      const aVal = a.original.price_cents ?? 0;
      const bVal = b.original.price_cents ?? 0;
      return aVal - bVal;
    },
    size: 120
  },
  {
    accessorKey: 'sold_count',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Sold' />
    ),
    cell: ({ row }) => (
      <span className='text-muted-foreground'>
        {row.getValue('sold_count') ?? '-'}
      </span>
    ),
    size: 100
  },
  {
    accessorKey: 'rating',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Rating' />
    ),
    cell: ({ row }) => (
      <span className='text-muted-foreground'>
        {row.getValue('rating') ?? '-'}
      </span>
    ),
    size: 80
  },
  {
    accessorKey: 'scraped_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Scraped' />
    ),
    cell: ({ row }) => {
      const date = row.getValue('scraped_at') as string | null;
      if (!date) return <span className='text-muted-foreground'>-</span>;
      return (
        <span className='text-muted-foreground text-xs'>
          {new Date(date).toLocaleString()}
        </span>
      );
    },
    size: 160
  }
];

export function ShopeeItemsTable() {
  const [data, setData] = useState<ShopeeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);

  useEffect(() => {
    fetch('/api/items/shopee')
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        } else {
          setError(json.error ?? 'Failed to load items');
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

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
        <p className='text-muted-foreground'>Loading Shopee items...</p>
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

  if (data.length === 0) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>
          No Shopee items yet. Run a scrape from the{' '}
          <a href='/scrape/shopee' className='text-primary hover:underline'>
            Scrape page
          </a>
          .
        </p>
      </div>
    );
  }

  return <DataTable table={table} />;
}

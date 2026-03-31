'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
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
import { EnrichMissingButton } from './enrich-missing-button';
import { ScrapeMissingMinifigsButton } from './scrape-missing-minifigs-button';
import { EnrichMissingDimensionsButton } from './enrich-missing-dimensions-button';
import { PriceDealFilter } from './price-deal-filter';
import type { UnifiedItem } from './types';
import { formatPrice } from './types';

const columns: ColumnDef<UnifiedItem>[] = [
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
    accessorKey: 'year_retired',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Retired' />
    ),
    cell: ({ row }) => {
      const yr = row.getValue('year_retired') as number | null;
      return yr ? (
        <span className='text-orange-600 dark:text-orange-400'>{yr}</span>
      ) : (
        <span className='text-muted-foreground'>-</span>
      );
    },
    size: 80
  },
  {
    accessorKey: 'retiring_soon',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Retiring' />
    ),
    cell: ({ row }) => {
      const soon = row.getValue('retiring_soon') as boolean | null;
      return soon ? (
        <span className='rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-400'>SOON</span>
      ) : (
        <span className='text-muted-foreground'>-</span>
      );
    },
    size: 80
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
    cell: ({ row }) => {
      const cents = row.getValue('shopee_price_cents') as number | null;
      const url = row.original.shopee_url;
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
    accessorKey: 'toysrus_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='TRU' />
    ),
    cell: ({ row }) => {
      const cents = row.getValue('toysrus_price_cents') as number | null;
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
    accessorKey: 'bricklink_new_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='BL New' />
    ),
    cell: ({ row }) => {
      const cents = row.getValue('bricklink_new_cents') as number | null;
      return (
        <span className='font-mono text-sm'>
          {formatPrice(cents, row.original.bricklink_new_currency)}
        </span>
      );
    },
    size: 100
  },
  {
    accessorKey: 'bricklink_used_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='BL Used' />
    ),
    cell: ({ row }) => {
      const cents = row.getValue('bricklink_used_cents') as number | null;
      return (
        <span className='font-mono text-sm'>
          {formatPrice(cents, row.original.bricklink_used_currency)}
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

export function UnifiedItemsTable() {
  const [data, setData] = useState<UnifiedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [dealFilter, setDealFilter] = useState<
    ((items: UnifiedItem[]) => UnifiedItem[]) | null
  >(null);
  const [hideNoRetail, setHideNoRetail] = useState(false);
  const [retirementFilter, setRetirementFilter] = useState<'all' | 'retired' | 'active' | 'retiring_soon'>('all');
  const [newSetNumber, setNewSetNumber] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const filteredData = useMemo(() => {
    let result = data;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.set_number.toLowerCase().includes(q) ||
          (item.title?.toLowerCase().includes(q) ?? false)
      );
    }
    if (hideNoRetail) {
      result = result.filter(
        (item) =>
          item.toysrus_price_cents !== null ||
          item.shopee_price_cents !== null
      );
    }
    if (retirementFilter === 'retired') {
      result = result.filter((item) => item.year_retired !== null);
    } else if (retirementFilter === 'active') {
      result = result.filter((item) => item.year_retired === null);
    } else if (retirementFilter === 'retiring_soon') {
      result = result.filter((item) => item.retiring_soon === true && item.year_retired === null);
    }
    if (dealFilter) {
      result = dealFilter(result);
    }
    return result;
  }, [data, searchQuery, dealFilter, hideNoRetail, retirementFilter]);

  const minifigMissing = useMemo(
    () => filteredData.filter(i => i.minifig_count === null).map(i => i.set_number),
    [filteredData]
  );

  const dimensionsMissing = useMemo(
    () => filteredData.filter(i => i.dimensions === null).map(i => i.set_number),
    [filteredData]
  );

  const fetchItems = () => {
    fetch('/api/items')
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
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const SET_NUMBER_PATTERN = /^\d{3,6}(-\d+)?$/;

  const handleAddItem = async () => {
    const trimmed = newSetNumber.trim();
    setAddError(null);

    if (!trimmed) {
      setAddError('Set number is required');
      return;
    }
    if (!SET_NUMBER_PATTERN.test(trimmed)) {
      setAddError('Invalid format (3-6 digits, optional -N suffix)');
      return;
    }

    setAdding(true);
    try {
      const res = await fetch('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_number: trimmed }),
      });
      const json = await res.json();

      if (!res.ok) {
        setAddError(json.error || 'Failed to add item');
        return;
      }

      setNewSetNumber('');
      fetchItems();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add item');
    } finally {
      setAdding(false);
    }
  };

  const table = useReactTable({
    data: filteredData,
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

  if (data.length === 0) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>
          No items yet. Run a scrape from the{' '}
          <Link href='/scrape' className='text-primary hover:underline'>
            Scrape page
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className='flex flex-1 flex-col gap-3 overflow-hidden'>
      <div className='flex items-center gap-3'>
        <input
          type='text'
          placeholder='Search set number or title...'
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className='bg-muted/50 rounded-lg border px-4 py-2.5 text-sm font-medium w-64 placeholder:text-muted-foreground'
        />
        <label className='bg-muted/50 flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium'>
          <input
            type='checkbox'
            checked={hideNoRetail}
            onChange={() => setHideNoRetail((prev) => !prev)}
            className='accent-primary h-4 w-4 rounded'
          />
          Has retail price
        </label>
        <select
          value={retirementFilter}
          onChange={(e) => setRetirementFilter(e.target.value as 'all' | 'retired' | 'active' | 'retiring_soon')}
          className='bg-muted/50 rounded-lg border px-4 py-2.5 text-sm font-medium'
        >
          <option value='all'>All sets</option>
          <option value='retired'>Retired only</option>
          <option value='active'>Active only</option>
          <option value='retiring_soon'>Retiring soon</option>
        </select>
        <PriceDealFilter onFilterChange={(fn) => setDealFilter(() => fn)} />
        <EnrichMissingButton setNumbers={filteredData.map((i) => i.set_number)} />
        <ScrapeMissingMinifigsButton setNumbers={minifigMissing} />
        <EnrichMissingDimensionsButton setNumbers={dimensionsMissing} />
        <div className='ml-auto flex items-center gap-2'>
          <input
            type='text'
            placeholder='Add set #...'
            value={newSetNumber}
            onChange={(e) => {
              setNewSetNumber(e.target.value);
              setAddError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAddItem();
            }}
            className='bg-muted/50 rounded-lg border px-3 py-2.5 text-sm font-mono w-32 placeholder:text-muted-foreground'
          />
          <button
            onClick={handleAddItem}
            disabled={adding}
            className='bg-primary text-primary-foreground rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-50'
          >
            {adding ? 'Adding...' : 'Add'}
          </button>
          {addError && (
            <span className='text-destructive text-sm'>{addError}</span>
          )}
        </div>
      </div>
      <DataTable table={table} />
    </div>
  );
}

'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type RowData,
  type SortingState
} from '@tanstack/react-table';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface TableMeta<TData extends RowData> {
    toggleWatchlist?: (setNumber: string) => void;
    enriching?: boolean;
  }
}
import { DataTable } from '@/components/ui/table/data-table';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { EnrichMissingButton } from './enrich-missing-button';
import { ScrapeMissingMinifigsButton } from './scrape-missing-minifigs-button';
import { EnrichMissingDimensionsButton } from './enrich-missing-dimensions-button';
import { SyncRetirementButton } from './sync-retirement-button';
import { ScrapeMissingMetadataButton } from './scrape-missing-metadata-button';
import { PriceDealFilter } from './price-deal-filter';
import type { UnifiedItem } from './types';
import { formatPrice } from './types';

function PriceShimmer() {
  return <div className='bg-muted/50 h-4 w-14 animate-pulse rounded' />;
}

const columns: ColumnDef<UnifiedItem>[] = [
  {
    accessorKey: 'watchlist',
    header: '',
    cell: ({ row, table }) => {
      const isWatchlisted = row.original.watchlist;
      const onToggle = table.options.meta?.toggleWatchlist;
      return (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.(row.original.set_number);
          }}
          className={`text-lg hover:scale-110 transition-transform ${
            isWatchlisted
              ? 'text-yellow-500'
              : 'text-muted-foreground/30 hover:text-yellow-400'
          }`}
          title={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
        >
          {isWatchlisted ? '\u2605' : '\u2606'}
        </button>
      );
    },
    size: 40,
    enableSorting: false,
  },
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
    id: 'retirement',
    accessorKey: 'year_retired',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Retirement' />
    ),
    cell: ({ row }) => {
      const yr = row.original.year_retired;
      const soon = row.original.retiring_soon;
      if (yr) {
        return (
          <span className='text-orange-600 dark:text-orange-400'>{yr}</span>
        );
      }
      if (soon) {
        return (
          <span className='rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-400'>SOON</span>
        );
      }
      return <span className='text-muted-foreground'>-</span>;
    },
    size: 90
  },
  {
    accessorKey: 'ml_growth_pct',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='ML Growth' />
    ),
    cell: ({ row, table }) => {
      const growth = row.getValue('ml_growth_pct') as number | null;
      if (table.options.meta?.enriching && growth == null) return <PriceShimmer />;
      if (growth == null || Number.isNaN(growth)) return <span className='text-muted-foreground'>-</span>;
      const color =
        growth >= 15 ? 'text-emerald-600 dark:text-emerald-500' :
        growth >= 10 ? 'text-green-600 dark:text-green-400' :
        growth >= 5 ? 'text-yellow-600 dark:text-yellow-400' :
        'text-red-500';
      const tier = row.original.ml_tier;
      const conf = row.original.ml_confidence;
      return (
        <div className='flex flex-col gap-0.5'>
          <span className={`font-mono text-sm font-semibold ${color}`}>
            +{growth.toFixed(1)}%
          </span>
          {tier != null && (
            <span className='text-muted-foreground text-[10px] leading-tight'>
              T{tier}{conf === 'high' ? ' H' : conf === 'moderate' ? ' M' : conf === 'low' ? ' L' : ''}
            </span>
          )}
        </div>
      );
    },
    size: 85
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
    cell: ({ row, table }) => {
      const cents = row.getValue('shopee_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      const url = row.original.shopee_url;
      const shopName = row.original.shopee_shop_name;
      const shopCount = row.original.shopee_shop_count ?? 0;
      const formatted = formatPrice(cents, 'MYR');
      if (!cents) return <span className='text-muted-foreground'>-</span>;
      return (
        <div className='flex flex-col gap-0.5'>
          {url ? (
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
          )}
          {shopName && (
            <span className='text-muted-foreground truncate text-[10px] leading-tight max-w-[120px]'>
              {shopName}
              {shopCount > 1 && (
                <span className='ml-0.5 text-[9px]'>+{shopCount - 1}</span>
              )}
            </span>
          )}
        </div>
      );
    },
    size: 130
  },
  {
    accessorKey: 'toysrus_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='TRU' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('toysrus_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
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
    accessorKey: 'mightyutan_price_cents',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='MU' />
    ),
    cell: ({ row, table }) => {
      const cents = row.getValue('mightyutan_price_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
      const url = row.original.mightyutan_url;
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
    cell: ({ row, table }) => {
      const cents = row.getValue('bricklink_new_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
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
    cell: ({ row, table }) => {
      const cents = row.getValue('bricklink_used_cents') as number | null;
      if (table.options.meta?.enriching && cents == null) return <PriceShimmer />;
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
  const [enriching, setEnriching] = useState(false);
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
  const [growthFilter, setGrowthFilter] = useState<'all' | 'strong' | 'buy' | 'hold' | 'avoid' | 'no_pred'>('all');
  const [tierFilter, setTierFilter] = useState<'all' | '1' | '2' | '3' | '4'>('all');
  const [confidenceFilter, setConfidenceFilter] = useState<'all' | 'high' | 'moderate' | 'low'>('all');
  const [showWatchlistOnly, setShowWatchlistOnly] = useState(false);

  const filteredData = useMemo(() => {
    let result = data;
    if (showWatchlistOnly) {
      result = result.filter((item) => item.watchlist);
    }
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
          item.shopee_price_cents !== null ||
          item.mightyutan_price_cents !== null
      );
    }
    if (retirementFilter === 'retired') {
      result = result.filter((item) => item.year_retired !== null);
    } else if (retirementFilter === 'active') {
      result = result.filter((item) => item.year_retired === null);
    } else if (retirementFilter === 'retiring_soon') {
      result = result.filter((item) => item.retiring_soon === true && item.year_retired === null);
    }
    if (growthFilter === 'strong') {
      result = result.filter((item) => item.ml_growth_pct != null && item.ml_growth_pct >= 15);
    } else if (growthFilter === 'buy') {
      result = result.filter((item) => item.ml_growth_pct != null && item.ml_growth_pct >= 10);
    } else if (growthFilter === 'hold') {
      result = result.filter((item) => item.ml_growth_pct != null && item.ml_growth_pct >= 5);
    } else if (growthFilter === 'avoid') {
      result = result.filter((item) => item.ml_growth_pct != null && item.ml_growth_pct < 5);
    } else if (growthFilter === 'no_pred') {
      result = result.filter((item) => item.ml_growth_pct == null);
    }
    if (tierFilter !== 'all') {
      const t = Number(tierFilter);
      result = result.filter((item) => item.ml_tier === t);
    }
    if (confidenceFilter !== 'all') {
      result = result.filter((item) => item.ml_confidence === confidenceFilter);
    }
    if (dealFilter) {
      result = dealFilter(result);
    }
    return result;
  }, [data, searchQuery, dealFilter, hideNoRetail, retirementFilter, growthFilter, tierFilter, confidenceFilter, showWatchlistOnly]);

  const minifigMissing = useMemo(
    () => filteredData.filter(i => i.minifig_count === null).map(i => i.set_number),
    [filteredData]
  );

  const dimensionsMissing = useMemo(
    () => filteredData.filter(i => i.dimensions === null).map(i => i.set_number),
    [filteredData]
  );

  const metadataMissing = useMemo(
    () => filteredData
      .filter(i => i.title === null || i.theme === null || i.year_released === null || i.image_url === null)
      .map(i => i.set_number),
    [filteredData]
  );

  const toggleWatchlist = useCallback(async (setNumber: string) => {
    try {
      const res = await fetch(`/api/items/${setNumber}/watchlist`, {
        method: 'PATCH',
      });
      if (!res.ok) return;
      const json = await res.json();
      if (json.success) {
        setData((prev) =>
          prev.map((item) =>
            item.set_number === setNumber
              ? { ...item, watchlist: json.data.watchlist }
              : item
          )
        );
      }
    } catch {
      // silent fail for single-user tool
    }
  }, []);

  const enrichItems = useCallback(async () => {
    setEnriching(true);
    try {
      const [itemsRes, signalsRes] = await Promise.all([
        fetch('/api/items').then((r) => r.json()),
        fetch('/api/items/signals').then((r) => r.json()).catch(() => null),
      ]);

      if (!itemsRes.success) return;

      const mlMap = new Map<string, { growth: number; confidence: string | null; tier: number | null }>();
      if (signalsRes?.success && Array.isArray(signalsRes.data)) {
        for (const sig of signalsRes.data) {
          const setNum = (sig.set_number ?? sig.item_id?.replace(/-\d+$/, '')) as string | undefined;
          if (setNum && sig.ml_growth_pct != null && !Number.isNaN(sig.ml_growth_pct)) {
            mlMap.set(setNum, {
              growth: sig.ml_growth_pct,
              confidence: sig.ml_confidence ?? null,
              tier: sig.ml_tier ?? null,
            });
          }
        }
      }

      const merged = (itemsRes.data as UnifiedItem[]).map((item) => {
        const ml = mlMap.get(item.set_number);
        return {
          ...item,
          ml_growth_pct: ml?.growth ?? null,
          ml_confidence: ml?.confidence ?? null,
          ml_tier: ml?.tier ?? null,
        };
      });

      setData(merged);
    } catch {
      // Prices failed to load — lite data still visible
    } finally {
      setEnriching(false);
    }
  }, []);

  const fetchItems = useCallback(async () => {
    try {
      // Phase 1: Fast load — catalog data only (no price joins)
      const liteRes = await fetch('/api/items/lite').then((r) => r.json());
      if (!liteRes.success) {
        setError(liteRes.error ?? 'Failed to load items');
        return;
      }

      // Show items immediately with null prices
      const liteItems: UnifiedItem[] = (liteRes.data as Record<string, unknown>[]).map((item) => ({
        ...item,
        shopee_price_cents: null,
        shopee_currency: null,
        shopee_url: null,
        shopee_shop_name: null,
        shopee_last_seen: null,
        shopee_shop_count: 0,
        toysrus_price_cents: null,
        toysrus_currency: null,
        toysrus_url: null,
        toysrus_last_seen: null,
        mightyutan_price_cents: null,
        mightyutan_currency: null,
        mightyutan_url: null,
        mightyutan_last_seen: null,
        bricklink_new_cents: null,
        bricklink_new_currency: null,
        bricklink_new_last_seen: null,
        bricklink_used_cents: null,
        bricklink_used_currency: null,
        bricklink_used_last_seen: null,
        ml_growth_pct: null,
        ml_confidence: null,
        ml_tier: null,
      } as UnifiedItem));

      setData(liteItems);
      setLoading(false);

      // Phase 2: Enrich with prices + signals in background
      enrichItems();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items');
      setLoading(false);
    }
  }, [enrichItems]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

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
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      pagination: { pageSize: 10 },
      columnVisibility: { rrp_cents: false },
    },
    meta: { toggleWatchlist, enriching },
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
      <div className='flex flex-col gap-2'>
        {/* Row 1: General filters */}
        <div className='flex items-center gap-3'>
          <input
            type='text'
            placeholder='Search set number or title...'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className='border-input bg-transparent rounded-md border px-3 py-2 text-sm shadow-xs w-64 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
          />
          <Select
            value={retirementFilter}
            onValueChange={(val) => setRetirementFilter(val as 'all' | 'retired' | 'active' | 'retiring_soon')}
          >
            <SelectTrigger className='w-[160px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All sets</SelectItem>
              <SelectItem value='retired'>Retired only</SelectItem>
              <SelectItem value='active'>Active only</SelectItem>
              <SelectItem value='retiring_soon'>Retiring soon</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant={showWatchlistOnly ? 'default' : 'outline'}
            size='default'
            onClick={() => setShowWatchlistOnly((prev) => !prev)}
          >
            {showWatchlistOnly ? '\u2605 Watchlist' : '\u2606 Watchlist'}
          </Button>
          <Button
            variant={hideNoRetail ? 'default' : 'outline'}
            size='default'
            onClick={() => setHideNoRetail((prev) => !prev)}
          >
            Has retail price
          </Button>
          <PriceDealFilter onFilterChange={(fn) => setDealFilter(() => fn)} />
        </div>

        {/* Row 2: ML prediction filters */}
        <div className='flex items-center gap-3'>
          <span className='text-muted-foreground text-xs font-medium'>ML</span>
          <Select
            value={growthFilter}
            onValueChange={(val) => setGrowthFilter(val as typeof growthFilter)}
          >
            <SelectTrigger className='w-[155px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All growth</SelectItem>
              <SelectItem value='strong'>Strong Buy (&ge;15%)</SelectItem>
              <SelectItem value='buy'>Buy (&ge;10%)</SelectItem>
              <SelectItem value='hold'>Hold (&ge;5%)</SelectItem>
              <SelectItem value='avoid'>Avoid (&lt;5%)</SelectItem>
              <SelectItem value='no_pred'>No prediction</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={tierFilter}
            onValueChange={(val) => setTierFilter(val as typeof tierFilter)}
          >
            <SelectTrigger className='w-[155px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All tiers</SelectItem>
              <SelectItem value='1'>Tier 1 (Intrinsic)</SelectItem>
              <SelectItem value='2'>Tier 2 (+ Keepa)</SelectItem>
              <SelectItem value='3'>Tier 3 (Extractors)</SelectItem>
              <SelectItem value='4'>Tier 4 (Ensemble)</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={confidenceFilter}
            onValueChange={(val) => setConfidenceFilter(val as typeof confidenceFilter)}
          >
            <SelectTrigger className='w-[155px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All confidence</SelectItem>
              <SelectItem value='high'>High</SelectItem>
              <SelectItem value='moderate'>Moderate</SelectItem>
              <SelectItem value='low'>Low</SelectItem>
            </SelectContent>
          </Select>
          {(growthFilter !== 'all' || tierFilter !== 'all' || confidenceFilter !== 'all') && (
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setGrowthFilter('all');
                setTierFilter('all');
                setConfidenceFilter('all');
              }}
              className='text-muted-foreground text-xs'
            >
              Clear ML filters
            </Button>
          )}
        </div>

        {/* Row 3: Actions + Add Item */}
        <div className='flex items-center gap-2'>
          <ScrapeMissingMetadataButton setNumbers={metadataMissing} />
          <EnrichMissingButton setNumbers={filteredData.map((i) => i.set_number)} />
          <ScrapeMissingMinifigsButton setNumbers={minifigMissing} />
          <EnrichMissingDimensionsButton setNumbers={dimensionsMissing} />
          <SyncRetirementButton />
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
              className='border-input bg-transparent rounded-md border px-3 py-2 text-sm font-mono shadow-xs w-32 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
            />
            <Button onClick={handleAddItem} disabled={adding}>
              {adding ? 'Adding...' : 'Add'}
            </Button>
            {addError && (
              <span className='text-destructive text-sm'>{addError}</span>
            )}
          </div>
        </div>
      </div>
      <DataTable table={table} />
    </div>
  );
}

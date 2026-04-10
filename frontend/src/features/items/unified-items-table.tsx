'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type SortingState,
  type PaginationState,
} from '@tanstack/react-table';
import { DataTable } from '@/components/ui/table/data-table';
import { Button } from '@/components/ui/button';
import { EnrichMissingButton } from './enrich-missing-button';
import { ScrapeMissingMinifigsButton } from './scrape-missing-minifigs-button';
import { EnrichMissingDimensionsButton } from './enrich-missing-dimensions-button';
import { SyncRetirementButton } from './sync-retirement-button';
import { ScrapeMissingMetadataButton } from './scrape-missing-metadata-button';
import { FilterBar } from './filter-bar';
import { applyFilters, type FilterKey } from './filter-utils';
import { QueryBuilder, createEmptyGroup, applyAdvancedQuery, type QueryGroup } from './query-builder';
import type { UnifiedItem } from './types';
import { unifiedColumns } from './unified-columns';

export function UnifiedItemsTable() {
  const [data, setData] = useState<UnifiedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [enriching, setEnriching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set());
  const [dealThreshold, setDealThreshold] = useState(0);
  const [cohortThreshold, setCohortThreshold] = useState(65);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedQuery, setAdvancedQuery] = useState<QueryGroup>(createEmptyGroup);
  const [yearFilter, setYearFilter] = useState<number | null>(null);
  const [newSetNumber, setNewSetNumber] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const handleToggleFilter = useCallback((key: FilterKey) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  const handleClearFilters = useCallback(() => {
    setActiveFilters(new Set());
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  const availableYears = useMemo(() => {
    const years = new Set<number>();
    for (const item of data) {
      if (item.year_released != null) years.add(item.year_released);
    }
    return [...years].sort((a, b) => b - a);
  }, [data]);

  const filteredData = useMemo(() => {
    let result = data;
    if (yearFilter != null) {
      result = result.filter((item) => item.year_released === yearFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.set_number.toLowerCase().includes(q) ||
          (item.title?.toLowerCase().includes(q) ?? false)
      );
    }
    result = applyFilters(result, activeFilters, dealThreshold, cohortThreshold);
    if (showAdvanced) {
      result = applyAdvancedQuery(result, advancedQuery);
    }
    return result;
  }, [data, yearFilter, searchQuery, activeFilters, dealThreshold, cohortThreshold, showAdvanced, advancedQuery]);

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

  const [watchlistLoading, setWatchlistLoading] = useState<Set<string>>(new Set());
  const [cartSetNumbers, setCartSetNumbers] = useState<Set<string>>(new Set());
  const [cartLoading, setCartLoading] = useState<Set<string>>(new Set());

  const toggleWatchlist = useCallback(async (setNumber: string) => {
    setWatchlistLoading((prev) => new Set(prev).add(setNumber));
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
    } finally {
      setWatchlistLoading((prev) => {
        const next = new Set(prev);
        next.delete(setNumber);
        return next;
      });
    }
  }, []);

  const fetchCartEntries = useCallback(async () => {
    try {
      const res = await fetch('/api/cart');
      const json = await res.json();
      if (json.success && Array.isArray(json.data)) {
        setCartSetNumbers(new Set(json.data.map((e: { set_number: string }) => e.set_number)));
      }
    } catch {
      // silent
    }
  }, []);

  const addToCart = useCallback(async (setNumber: string) => {
    setCartLoading((prev) => new Set(prev).add(setNumber));
    try {
      const res = await fetch('/api/cart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_number: setNumber }),
      });
      const json = await res.json();
      if (json.success) {
        setCartSetNumbers((prev) => new Set(prev).add(setNumber));
        setData((prev) =>
          prev.map((item) =>
            item.set_number === setNumber ? { ...item, watchlist: false } : item
          )
        );
      }
    } catch {
      // silent
    } finally {
      setCartLoading((prev) => {
        const next = new Set(prev);
        next.delete(setNumber);
        return next;
      });
    }
  }, []);

  const enrichItems = useCallback(async () => {
    setEnriching(true);
    try {
      const [itemsRes, signalsRes, liqRes, liqCohortRes] = await Promise.all([
        fetch('/api/items').then((r) => r.json()),
        fetch('/api/items/signals').then((r) => r.json()).catch(() => null),
        fetch('/api/items/liquidity').then((r) => r.json()).catch(() => null),
        fetch('/api/items/liquidity/cohorts').then((r) => r.json()).catch(() => null),
      ]);

      if (!itemsRes.success) return;

      const mlMap = new Map<string, {
        growth: number | null;
        confidence: string | null;
        avoid_probability: number | null;
        buy_signal: boolean;
        avoid: boolean;
        kelly_fraction: number | null;
        win_probability: number | null;
        cohorts: Record<string, { composite_score_pct: number | null }> | null;
      }>();
      if (signalsRes?.success && Array.isArray(signalsRes.data)) {
        for (const sig of signalsRes.data) {
          const setNum = (sig.set_number ?? sig.item_id?.replace(/-\d+$/, '')) as string | undefined;
          if (setNum) {
            const hasML = sig.ml_growth_pct != null && !Number.isNaN(sig.ml_growth_pct);
            mlMap.set(setNum, {
              growth: hasML ? sig.ml_growth_pct : null,
              confidence: sig.ml_confidence ?? null,
              avoid_probability: sig.ml_avoid_probability ?? null,
              buy_signal: sig.ml_buy_signal ?? false,
              avoid: sig.ml_avoid ?? false,
              kelly_fraction: sig.ml_kelly_fraction ?? null,
              win_probability: sig.ml_win_probability ?? null,
              cohorts: sig.cohorts ?? null,
            });
          }
        }
      }

      const liqMap: Record<string, number> = liqRes?.success && liqRes.data ? liqRes.data : {};
      const liqCohortMap: Record<string, Record<string, number | null>> =
        liqCohortRes?.success && liqCohortRes.data ? liqCohortRes.data : {};

      const merged = (itemsRes.data as UnifiedItem[]).map((item) => {
        const ml = mlMap.get(item.set_number);
        const c = ml?.cohorts;
        const lc = liqCohortMap[item.set_number];
        return {
          ...item,
          ml_growth_pct: ml?.growth ?? null,
          ml_confidence: ml?.confidence ?? null,
          ml_tier: null,
          ml_avoid_probability: ml?.avoid_probability ?? null,
          ml_buy_signal: ml?.buy_signal ?? false,
          ml_avoid: ml?.avoid ?? false,
          ml_kelly_fraction: ml?.kelly_fraction ?? null,
          ml_win_probability: ml?.win_probability ?? null,
          cohort_half_year: c?.half_year?.composite_score_pct ?? null,
          cohort_year: c?.year?.composite_score_pct ?? null,
          cohort_theme: c?.theme?.composite_score_pct ?? null,
          cohort_year_theme: c?.year_theme?.composite_score_pct ?? null,
          cohort_price_tier: c?.price_tier?.composite_score_pct ?? null,
          cohort_piece_group: c?.piece_group?.composite_score_pct ?? null,
          liquidity_score: liqMap[item.set_number] ?? null,
          liq_cohort_half_year: lc?.half_year ?? null,
          liq_cohort_year: lc?.year ?? null,
          liq_cohort_theme: lc?.theme ?? null,
          liq_cohort_year_theme: lc?.year_theme ?? null,
          liq_cohort_price_tier: lc?.price_tier ?? null,
          liq_cohort_piece_group: lc?.piece_group ?? null,
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
        ml_avoid_probability: null,
        ml_raw_growth_pct: null,
        ml_kelly_fraction: null,
        ml_win_probability: null,
        cohort_half_year: null,
        cohort_year: null,
        cohort_theme: null,
        cohort_year_theme: null,
        cohort_price_tier: null,
        cohort_piece_group: null,
        liquidity_score: null,
        liq_cohort_half_year: null,
        liq_cohort_year: null,
        liq_cohort_theme: null,
        liq_cohort_year_theme: null,
        liq_cohort_price_tier: null,
        liq_cohort_piece_group: null,
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
    fetchCartEntries();
  }, [fetchItems, fetchCartEntries]);

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
    columns: unifiedColumns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    autoResetPageIndex: false,
    initialState: {
      columnVisibility: { rrp_cents: false },
    },
    meta: { toggleWatchlist, watchlistLoading, enriching, addToCart, cartLoading, cartSetNumbers },
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
        {/* Row 1: Search + filter chips */}
        <div className='flex items-center gap-3'>
          <input
            type='text'
            placeholder='Search set number or title...'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className='border-input bg-transparent rounded-md border px-3 py-2 text-sm shadow-xs w-64 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
          />
          <select
            value={yearFilter ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              setYearFilter(val ? Number(val) : null);
              setPagination((prev) => ({ ...prev, pageIndex: 0 }));
            }}
            className='border-input bg-transparent rounded-md border px-3 py-2 text-sm shadow-xs h-9 text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
          >
            <option value=''>All years</option>
            {availableYears.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        {/* Row 2: Filter chips + Advanced toggle */}
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <FilterBar
              activeFilters={activeFilters}
              onToggle={handleToggleFilter}
              onClearAll={handleClearFilters}
              dealThreshold={dealThreshold}
              onDealThresholdChange={setDealThreshold}
              cohortThreshold={cohortThreshold}
              onCohortThresholdChange={setCohortThreshold}
            />
          </div>
          <Button
            variant={showAdvanced ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowAdvanced((prev) => !prev)}
            className="shrink-0 text-xs"
          >
            Advanced
          </Button>
        </div>

        {/* Row 2b: Advanced query builder */}
        {showAdvanced && (
          <QueryBuilder query={advancedQuery} onChange={setAdvancedQuery} />
        )}

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

'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { DataTable } from '@/components/ui/table/data-table';
import { Button } from '@/components/ui/button';
import { unifiedColumns } from '@/features/items/unified-columns';
import type { UnifiedItem } from '@/features/items/types';
import { meetsCartCriteria, type CartSettings } from './cart-criteria';

interface CartEntry {
  set_number: string;
  source: string;
  added_at: string;
}

const DEFAULT_CART_SETTINGS: CartSettings = {
  min_liquidity_score: 50,
  deal_threshold_pct: 5,
  min_confidence: 'high',
  max_avoid_probability: 0.5,
  min_growth_pct: 8,
};

const removeColumn: ColumnDef<UnifiedItem> = {
  id: 'cart_source',
  header: 'Source',
  cell: ({ row, table }) => {
    const meta = table.options.meta as {
      cartEntries?: Map<string, CartEntry>;
      removeFromCart?: (sn: string) => void;
      banFromCart?: (sn: string) => void;
    };
    const entry = meta?.cartEntries?.get(row.original.set_number);
    const source = entry?.source ?? 'auto';
    return (
      <div className='flex items-center gap-2'>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
            source === 'manual'
              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
          }`}
        >
          {source}
        </span>
        <button
          onClick={() => meta?.removeFromCart?.(row.original.set_number)}
          className='flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors'
          title='Remove from cart'
        >
          <svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
            <path d='M3 6h18' /><path d='M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6' /><path d='M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2' /><line x1='10' y1='11' x2='10' y2='17' /><line x1='14' y1='11' x2='14' y2='17' />
          </svg>
        </button>
        <button
          onClick={() => meta?.banFromCart?.(row.original.set_number)}
          className='flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 transition-colors'
          title='Ban from auto-cart (prevents auto-add)'
        >
          <svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
            <circle cx='12' cy='12' r='10' /><line x1='4.93' y1='4.93' x2='19.07' y2='19.07' />
          </svg>
        </button>
      </div>
    );
  },
  size: 130,
  enableSorting: false,
};

const cartColumns: ColumnDef<UnifiedItem>[] = [
  removeColumn,
  ...unifiedColumns.filter((col) => col.id !== 'add_to_cart'),
];

export function CartTable() {
  const [allItems, setAllItems] = useState<UnifiedItem[]>([]);
  const [cartEntries, setCartEntries] = useState<Map<string, CartEntry>>(new Map());
  const [cartSettings, setCartSettings] = useState<CartSettings>(DEFAULT_CART_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [enriching, setEnriching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [newSetNumber, setNewSetNumber] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const syncedRef = useRef(false);

  // Fetch cart entries from backend
  const fetchCart = useCallback(async () => {
    try {
      const res = await fetch('/api/cart');
      const json = await res.json();
      if (json.success && Array.isArray(json.data)) {
        const map = new Map<string, CartEntry>();
        for (const entry of json.data as CartEntry[]) {
          map.set(entry.set_number, entry);
        }
        setCartEntries(map);
      }
    } catch {
      // Cart fetch failed -- will show empty
    }
  }, []);

  // Fetch cart settings
  const fetchCartSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success && json.data?.cart) {
        setCartSettings(json.data.cart);
      }
    } catch {
      // Use defaults
    }
  }, []);

  // Enrich items with prices, signals, liquidity
  const enrichItems = useCallback(async () => {
    setEnriching(true);
    try {
      const [itemsRes, signalsRes, liqRes, liqCohortRes, beSignalsRes] = await Promise.all([
        fetch('/api/items').then((r) => r.json()),
        fetch('/api/items/signals').then((r) => r.json()).catch(() => null),
        fetch('/api/items/liquidity').then((r) => r.json()).catch(() => null),
        fetch('/api/items/liquidity/cohorts').then((r) => r.json()).catch(() => null),
        fetch('/api/items/signals/be').then((r) => r.json()).catch(() => null),
      ]);

      if (!itemsRes.success) return;

      const mlMap = new Map<string, {
        growth: number | null;
        confidence: string | null;
        avoid_probability: number | null;
        great_buy_probability: number | null;
        buy_category: 'GREAT' | 'GOOD' | 'SKIP' | 'WORST' | 'NONE' | null;
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
              great_buy_probability: sig.ml_great_buy_probability ?? null,
              buy_category: sig.ml_buy_category ?? null,
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

      // Build Keepa cohort map from bulk BE signals endpoint
      const beCohortMap = new Map<string, Record<string, { composite_score_pct: number | null }>>();
      if (beSignalsRes?.success && Array.isArray(beSignalsRes.data)) {
        for (const sig of beSignalsRes.data) {
          const setNum = (sig.set_number ?? sig.item_id) as string | undefined;
          if (setNum && sig.cohorts) {
            beCohortMap.set(setNum, sig.cohorts);
          }
        }
      }

      const merged: UnifiedItem[] = (itemsRes.data as UnifiedItem[]).map((item) => {
        const ml = mlMap.get(item.set_number);
        const c = beCohortMap.get(item.set_number);
        const lc = liqCohortMap[item.set_number];
        return {
          ...item,
          ml_growth_pct: ml?.growth ?? null,
          ml_confidence: ml?.confidence ?? null,
          ml_tier: null,
          ml_avoid_probability: ml?.avoid_probability ?? null,
          ml_great_buy_probability: ml?.great_buy_probability ?? null,
          ml_buy_category: ml?.buy_category ?? null,
          ml_raw_growth_pct: null,
          ml_kelly_fraction: ml?.kelly_fraction ?? null,
          ml_win_probability: ml?.win_probability ?? null,
          cohort_half_year: c?.half_year?.composite_score_pct ?? null,
          cohort_theme: c?.theme?.composite_score_pct ?? null,
          cohort_price_tier: c?.price_tier?.composite_score_pct ?? null,
          liquidity_score: liqMap[item.set_number] ?? null,
          liq_cohort_half_year: lc?.half_year ?? null,
          liq_cohort_theme: lc?.theme ?? null,
          liq_cohort_price_tier: lc?.price_tier ?? null,
        };
      });

      setAllItems(merged);
    } catch {
      // Enrichment failed
    } finally {
      setEnriching(false);
    }
  }, []);

  // Initial data load
  const fetchAll = useCallback(async () => {
    try {
      // Fetch lite items first for fast render
      const liteRes = await fetch('/api/items/lite').then((r) => r.json());
      if (!liteRes.success) {
        setError(liteRes.error ?? 'Failed to load items');
        return;
      }
      const liteItems: UnifiedItem[] = (liteRes.data as Record<string, unknown>[]).map((item) => ({
        ...item,
        shopee_price_cents: null, shopee_currency: null, shopee_url: null,
        shopee_shop_name: null, shopee_last_seen: null, shopee_shop_count: 0,
        toysrus_price_cents: null, toysrus_currency: null, toysrus_url: null, toysrus_last_seen: null,
        mightyutan_price_cents: null, mightyutan_currency: null, mightyutan_url: null, mightyutan_last_seen: null,
        bricklink_new_cents: null, bricklink_new_currency: null, bricklink_new_last_seen: null,
        bricklink_used_cents: null, bricklink_used_currency: null, bricklink_used_last_seen: null,
        ml_growth_pct: null, ml_confidence: null, ml_tier: null,
        ml_avoid_probability: null, ml_great_buy_probability: null,
        ml_buy_category: null, ml_raw_growth_pct: null,
        ml_kelly_fraction: null, ml_win_probability: null,
        cohort_half_year: null, cohort_theme: null, cohort_price_tier: null,
        liquidity_score: null,
        liq_cohort_half_year: null, liq_cohort_theme: null, liq_cohort_price_tier: null,
      } as UnifiedItem));

      setAllItems(liteItems);
      setLoading(false);

      // Enrich in background
      enrichItems();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
      setLoading(false);
    }
  }, [enrichItems]);

  useEffect(() => {
    fetchAll();
    fetchCart();
    fetchCartSettings();
  }, [fetchAll, fetchCart, fetchCartSettings]);

  // Reset sync flag when settings change so auto-scan re-runs
  useEffect(() => {
    syncedRef.current = false;
  }, [cartSettings]);

  // Auto-scan: sync cart after enrichment completes
  useEffect(() => {
    if (enriching || allItems.length === 0 || syncedRef.current) return;

    // Only sync if we have enriched data (check for non-null ML/price fields)
    const hasEnrichedData = allItems.some((i) => i.ml_growth_pct != null);
    if (!hasEnrichedData) return;

    syncedRef.current = true;
    const qualifying = allItems
      .filter((item) => meetsCartCriteria(item, cartSettings))
      .map((item) => item.set_number);

    fetch('/api/cart/sync', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ set_numbers: qualifying }),
    })
      .then((r) => r.json())
      .then((json) => {
        if (json.success && Array.isArray(json.data)) {
          const map = new Map<string, CartEntry>();
          for (const entry of json.data as CartEntry[]) {
            map.set(entry.set_number, entry);
          }
          setCartEntries(map);
        }
      })
      .catch(() => {});
  }, [enriching, allItems, cartSettings]);

  // Filter to only cart items
  const cartData = useMemo(() => {
    if (cartEntries.size === 0) return [];
    let result = allItems.filter((item) => cartEntries.has(item.set_number));
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.set_number.toLowerCase().includes(q) ||
          (item.title?.toLowerCase().includes(q) ?? false)
      );
    }
    return result;
  }, [allItems, cartEntries, searchQuery]);

  const removeFromCart = useCallback(async (setNumber: string) => {
    try {
      const res = await fetch(`/api/cart/${setNumber}`, { method: 'DELETE' });
      const json = await res.json();
      if (json.success) {
        setCartEntries((prev) => {
          const next = new Map(prev);
          next.delete(setNumber);
          return next;
        });
      }
    } catch {
      // silent
    }
  }, []);

  const banFromCart = useCallback(async (setNumber: string) => {
    try {
      const res = await fetch(`/api/cart/ban/${setNumber}`, { method: 'POST' });
      const json = await res.json();
      if (json.success) {
        // Update cart entries from returned data
        if (Array.isArray(json.data)) {
          const map = new Map<string, CartEntry>();
          for (const entry of json.data as CartEntry[]) {
            map.set(entry.set_number, entry);
          }
          setCartEntries(map);
        } else {
          // Fallback: just remove from local state
          setCartEntries((prev) => {
            const next = new Map(prev);
            next.delete(setNumber);
            return next;
          });
        }
      }
    } catch {
      // silent
    }
  }, []);

  const SET_NUMBER_PATTERN = /^\d{3,6}(-\d+)?$/;

  const handleAddToCart = async () => {
    const trimmed = newSetNumber.trim();
    setAddError(null);
    if (!trimmed) { setAddError('Set number required'); return; }
    if (!SET_NUMBER_PATTERN.test(trimmed)) { setAddError('Invalid format'); return; }

    setAdding(true);
    try {
      const res = await fetch('/api/cart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_number: trimmed }),
      });
      const json = await res.json();
      if (!res.ok) { setAddError(json.error || 'Failed'); return; }
      if (json.success) {
        setCartEntries((prev) => {
          const next = new Map(prev);
          next.set(json.data.set_number, json.data);
          return next;
        });
        setNewSetNumber('');
      }
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setAdding(false);
    }
  };

  const table = useReactTable({
    data: cartData,
    columns: cartColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    autoResetPageIndex: false,
    initialState: {
      pagination: { pageSize: 10 },
      columnVisibility: { rrp_cents: false },
    },
    meta: { cartEntries, removeFromCart, banFromCart, enriching },
  });

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading cart...</p>
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

  if (!enriching && cartEntries.size === 0 && syncedRef.current) {
    return (
      <div className='flex flex-col items-center justify-center gap-4 py-16'>
        <p className='text-muted-foreground'>
          No items match cart criteria. Adjust thresholds in{' '}
          <Link href='/operations' className='text-primary hover:underline'>
            Settings
          </Link>{' '}
          or add items manually below.
        </p>
        <div className='flex items-center gap-2'>
          <input
            type='text'
            placeholder='Add set #...'
            value={newSetNumber}
            onChange={(e) => { setNewSetNumber(e.target.value); setAddError(null); }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddToCart(); }}
            className='border-input bg-transparent rounded-md border px-3 py-2 text-sm font-mono shadow-xs w-32 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
          />
          <Button onClick={handleAddToCart} disabled={adding}>
            {adding ? 'Adding...' : 'Add to Cart'}
          </Button>
          {addError && (
            <span className='text-destructive text-sm'>{addError}</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className='flex flex-1 flex-col gap-3 overflow-hidden'>
      <div className='flex flex-col gap-2'>
        <div className='flex items-center gap-3'>
          <input
            type='text'
            placeholder='Search set number or title...'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className='border-input bg-transparent rounded-md border px-3 py-2 text-sm shadow-xs w-64 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
          />
          <span className='text-muted-foreground text-sm'>
            {cartData.length} item{cartData.length !== 1 ? 's' : ''} in cart
            {enriching && ' (scanning...)'}
          </span>
          <div className='ml-auto flex items-center gap-2'>
            <input
              type='text'
              placeholder='Add set #...'
              value={newSetNumber}
              onChange={(e) => { setNewSetNumber(e.target.value); setAddError(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter') handleAddToCart(); }}
              className='border-input bg-transparent rounded-md border px-3 py-2 text-sm font-mono shadow-xs w-32 h-9 placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none'
            />
            <Button onClick={handleAddToCart} disabled={adding}>
              {adding ? 'Adding...' : 'Add to Cart'}
            </Button>
            {addError && (
              <span className='text-destructive text-sm'>{addError}</span>
            )}
          </div>
        </div>
        <div className='text-muted-foreground text-xs'>
          Auto-scan: Liquidity {'>='} {cartSettings.min_liquidity_score}, deal within {cartSettings.deal_threshold_pct}%,
          confidence {cartSettings.min_confidence}, growth {'>='} {cartSettings.min_growth_pct}%, Hold or Buy.
          <Link href='/operations' className='text-primary ml-1 hover:underline'>
            Edit in Settings
          </Link>
        </div>
      </div>
      <DataTable table={table} />
    </div>
  );
}

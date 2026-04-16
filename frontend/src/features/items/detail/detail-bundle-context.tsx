'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

/** Shape of the bundle response from /api/items/{sn}/detail-bundle. */
export interface DetailBundle {
  brickeconomy: Record<string, unknown> | null;
  keepa: Record<string, unknown> | null;
  bricklink_prices: Record<string, unknown> | null;
  bricklink_sellers: Record<string, unknown> | null;
  competition: Record<string, unknown> | null;
  minifigures: Record<string, unknown> | null;
  minifig_value_history: Record<string, unknown> | null;
  ml_growth: Record<string, unknown> | null;
  ml_tracking: unknown[] | null;
  signals: Record<string, unknown> | null;
  signals_be: Record<string, unknown> | null;
  liquidity_bricklink: Record<string, unknown> | null;
  liquidity_brickeconomy: Record<string, unknown> | null;
  liquidity_cohorts: Record<string, unknown> | null;
  my_liquidity: Record<string, unknown> | null;
  my_liquidity_cohorts: Record<string, unknown> | null;
  scrape_history: ScrapeHistoryEntry[] | null;
}

export interface ScrapeHistoryEntry {
  source: string;
  scraped_at: string;
  status?: string;
  error?: string | null;
}

interface BundleState {
  bundle: DetailBundle | null;
  loading: boolean;
}

const DetailBundleContext = createContext<BundleState>({
  bundle: null,
  loading: true,
});

export function DetailBundleProvider({
  setNumber,
  children,
}: {
  setNumber: string;
  children: ReactNode;
}) {
  const [state, setState] = useState<BundleState>({ bundle: null, loading: true });

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/items/${setNumber}/detail-bundle`)
      .then((res) => res.json())
      .then((json) => {
        if (!cancelled && json.success && json.data) {
          setState({ bundle: json.data, loading: false });
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          setState((prev) => (prev.loading ? { ...prev, loading: false } : prev));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [setNumber]);

  return (
    <DetailBundleContext.Provider value={state}>
      {children}
    </DetailBundleContext.Provider>
  );
}

/**
 * Access the detail bundle. Returns { bundle, loading }.
 * If bundle is null and loading is false, the fetch failed or returned no data.
 */
export function useDetailBundle() {
  return useContext(DetailBundleContext);
}

'use client';

import { ChevronDownIcon, ExternalLinkIcon, Eye, EyeOff, Loader2, Store } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type SortingState,
} from '@tanstack/react-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DataTable } from '@/components/ui/table/data-table';
import type { BuyRating, ItemDetail, PriceRecord } from '../types';
import { formatPrice, getLatestPriceBySource } from '../types';
import { priceColumns } from './price-columns';
import { DetailBundleProvider } from './detail-bundle-context';
import { InvestmentPanel } from './investment-panel';
import { BrickeconomyPanel } from './brickeconomy-panel';
import { BricklinkPriceChart } from './bricklink-price-chart';
import { BricklinkSellersPanel } from './bricklink-sellers-panel';
import { CohortPanel } from './cohort-panel';
import { LiquidityPanel } from './liquidity-panel';
import { MLPredictionPanel } from './ml-prediction-panel';
import { KeepaPanel } from './keepa-panel';
import { MinifiguresPanel } from './minifigures-panel';
import { ListingPanel } from './listing-panel';
import { CompetitionPanel } from './competition-panel';
import { MinifigureValueChart } from './minifigure-value-chart';
import { CapitalAllocationPanel } from './capital-allocation-panel';

export interface ChartDateRange {
  min: number; // unix ms
  max: number; // unix ms
}

const BUY_RATING_OPTIONS: {
  value: BuyRating;
  label: string;
  color: string;
}[] = [
  { value: 1, label: 'Best Buy', color: 'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/30 dark:text-green-300 dark:border-green-700' },
  { value: 2, label: 'Good Buy', color: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700' },
  { value: 3, label: 'Bad Buy', color: 'bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-700' },
  { value: 4, label: 'Worst Buy', color: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700' },
];

function getBuyRatingOption(rating: BuyRating) {
  return BUY_RATING_OPTIONS.find((o) => o.value === rating) ?? BUY_RATING_OPTIONS[0];
}

const ENRICH_SOURCES = [
  { id: null, label: 'All Sources' },
  { id: 'bricklink', label: 'Bricklink' },
] as const;

export const SOURCE_LABELS: Record<string, string> = {
  shopee: 'Shopee MY',
  bricklink_new: 'Bricklink (New)',
  bricklink_used: 'Bricklink (Used)',
  toysrus: 'Toys R Us MY',
  keepa_amazon: 'Keepa (Amazon)',
  keepa_new: 'Keepa (New)',
  keepa_buy_box: 'Keepa (Buy Box)',
};

function getSourceUrl(source: string, record: PriceRecord, setNumber: string): string | null {
  if (record.url) return record.url;

  if (source === 'bricklink_new' || source === 'bricklink_used') {
    return `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${setNumber}-1#T=P`;
  }

  return null;
}

export const SOURCE_COLORS: Record<string, string> = {
  shopee: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  bricklink_new:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  bricklink_used:
    'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300',
  toysrus:
    'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  keepa_amazon:
    'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  keepa_new:
    'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300',
  keepa_buy_box:
    'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

interface ItemDetailViewProps {
  setNumber: string;
}

type EnrichStatus = 'idle' | 'loading' | 'success' | 'error';

export function ItemDetailView({ setNumber }: ItemDetailViewProps) {
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enrichStatus, setEnrichStatus] = useState<EnrichStatus>('idle');
  const [enrichMessage, setEnrichMessage] = useState<string | null>(null);
  const [mlPredicting, setMlPredicting] = useState(false);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [buyRatingLoading, setBuyRatingLoading] = useState<BuyRating | null>(null);
  const [listingStatus, setListingStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [listingMessage, setListingMessage] = useState<string | null>(null);

  const [priceSorting, setPriceSorting] = useState<SortingState>([{ id: 'date', desc: true }]);

  const priceTable = useReactTable({
    data: item?.prices ?? [],
    columns: priceColumns,
    state: { sorting: priceSorting },
    onSortingChange: setPriceSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });

  // Shared date range across all charts
  const [chartRanges, setChartRanges] = useState<Record<string, ChartDateRange>>({});

  const reportDateRange = (chartId: string, range: ChartDateRange) => {
    setChartRanges((prev) => {
      if (prev[chartId]?.min === range.min && prev[chartId]?.max === range.max) {
        return prev;
      }
      return { ...prev, [chartId]: range };
    });
  };

  const globalDateRange: ChartDateRange | null = (() => {
    const ranges = Object.values(chartRanges);
    if (ranges.length === 0) return null;
    return {
      min: Math.min(...ranges.map((r) => r.min)),
      max: Math.max(...ranges.map((r) => r.max)),
    };
  })();

  const fetchItem = () => {
    fetch(`/api/items/${setNumber}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setItem(json.data);
        } else {
          setError(json.error ?? 'Item not found');
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchItem();
  }, [setNumber]);

  const handleEnrich = async (source: string | null) => {
    setEnrichStatus('loading');
    setEnrichMessage(null);

    const body: { set_number: string; source?: string } = {
      set_number: setNumber,
    };
    if (source) {
      body.source = source;
    }

    try {
      const res = await fetch('/api/enrichment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();

      if (!json.success) {
        setEnrichStatus('error');
        setEnrichMessage(json.error ?? 'Enrichment failed');
        return;
      }

      const label = source ?? 'all sources';
      setEnrichStatus('success');
      setEnrichMessage(
        `Enrichment queued from ${label} (${json.data.job_id})`
      );

      // Auto-refresh item data after a delay to pick up enrichment results
      setTimeout(() => {
        fetchItem();
      }, 5000);
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(
        err instanceof Error ? err.message : 'Failed to start enrichment'
      );
    }
  };

  const handleBrickeconomyScrape = async () => {
    setEnrichStatus('loading');
    setEnrichMessage(null);

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scraperId: 'brickeconomy',
          url: setNumber,
        }),
      });
      const json = await res.json();

      if (!json.success && !json.job_id) {
        setEnrichStatus('error');
        setEnrichMessage(json.error ?? json.detail ?? 'BrickEconomy scrape failed');
        return;
      }

      setEnrichStatus('success');
      setEnrichMessage(
        `BrickEconomy scrape queued (${json.job_id})`
      );
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(
        err instanceof Error ? err.message : 'Failed to start BrickEconomy scrape'
      );
    }
  };

  const handleKeepaScrape = async () => {
    setEnrichStatus('loading');
    setEnrichMessage(null);

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scraperId: 'keepa',
          url: setNumber,
        }),
      });
      const json = await res.json();

      if (!json.success && !json.job_id) {
        setEnrichStatus('error');
        setEnrichMessage(json.error ?? json.detail ?? 'Keepa scrape failed');
        return;
      }

      setEnrichStatus('success');
      setEnrichMessage(
        `Keepa scrape queued (${json.job_id})`
      );
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(
        err instanceof Error ? err.message : 'Failed to start Keepa scrape'
      );
    }
  };

  const handleShopeeSaturation = async () => {
    setEnrichStatus('loading');
    setEnrichMessage(null);

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scraperId: 'shopee_saturation',
          url: setNumber,
        }),
      });
      const json = await res.json();

      if (!json.success && !json.job_id) {
        setEnrichStatus('error');
        setEnrichMessage(json.error ?? json.detail ?? 'Shopee saturation check failed');
        return;
      }

      setEnrichStatus('success');
      setEnrichMessage(
        `Shopee saturation queued (${json.job_id})`
      );
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(
        err instanceof Error ? err.message : 'Failed to start Shopee saturation check'
      );
    }
  };

  const handleShopeeCompetition = async () => {
    setEnrichStatus('loading');
    setEnrichMessage(null);

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scraperId: 'shopee_competition',
          url: setNumber,
        }),
      });
      const json = await res.json();

      if (!json.success && !json.job_id) {
        setEnrichStatus('error');
        setEnrichMessage(json.error ?? json.detail ?? 'Shopee competition scan failed');
        return;
      }

      setEnrichStatus('success');
      setEnrichMessage(
        `Shopee competition scan queued (${json.job_id})`
      );
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(
        err instanceof Error ? err.message : 'Failed to start Shopee competition scan'
      );
    }
  };

  const handleListOn = async (platform: string) => {
    setListingStatus('loading');
    setListingMessage(null);
    try {
      const res = await fetch('/api/listing/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_number: setNumber, platform }),
      });
      const json = await res.json();
      if (!json.success) {
        setListingStatus('error');
        setListingMessage(json.error ?? 'Listing failed');
        return;
      }
      setListingStatus('success');
      setListingMessage(json.message);
    } catch (err) {
      setListingStatus('error');
      setListingMessage(err instanceof Error ? err.message : 'Failed to open seller portal');
    }
  };

  const handleMlPredict = async () => {
    setMlPredicting(true);
    try {
      const res = await fetch(`/api/ml/growth/predict/${setNumber}`, {
        method: 'POST',
      });
      const json = await res.json();
      if (json.error) {
        setEnrichStatus('error');
        setEnrichMessage(json.error);
      } else {
        const { set_number: _sn, ...pred } = json;
        setItem((prev) => prev ? { ...prev, ml_prediction: pred } : prev);
        setEnrichStatus('success');
        setEnrichMessage('ML prediction generated');
      }
    } catch (err) {
      setEnrichStatus('error');
      setEnrichMessage(err instanceof Error ? err.message : 'ML predict failed');
    } finally {
      setMlPredicting(false);
    }
  };

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading...</p>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className='flex h-96 flex-col items-center justify-center gap-2'>
        <p className='text-destructive'>{error ?? 'Item not found'}</p>
        <Link href='/items' className='text-primary text-sm hover:underline'>
          Back to items
        </Link>
      </div>
    );
  }

  // Group prices by source for summary
  const latestBySource = getLatestPriceBySource(item.prices);

  return (
    <DetailBundleProvider setNumber={setNumber}>
    <div className='flex flex-col gap-6'>
      {/* Header */}
      <div className='flex items-start gap-4'>
        <Link
          href='/items'
          className='text-muted-foreground hover:text-foreground mt-1 text-sm'
        >
          &larr; Items
        </Link>
      </div>

      <div className='flex items-start gap-6'>
        {item.image_url && (
          <img
            src={item.image_url}
            alt={item.title ?? ''}
            className='h-32 w-32 cursor-pointer rounded-lg object-cover transition-opacity hover:opacity-80'
            title='Click to open images in Finder'
            onClick={() => {
              fetch(`/api/images/open/${item.set_number}`, { method: 'POST' });
            }}
          />
        )}
        <div>
          <h1 className='text-2xl font-bold'>{item.title ?? setNumber}</h1>
          <div className='text-muted-foreground mt-1 flex items-center gap-3 text-sm'>
            <span className='font-mono'>{item.set_number}</span>
            {item.year_released && <span>{item.year_released}</span>}
            {item.year_retired && (
              <span className='text-orange-600 dark:text-orange-400'>
                Retired {item.year_retired}
              </span>
            )}
            {item.theme && <span>{item.theme}</span>}
            {item.parts_count && <span>{item.parts_count} pcs</span>}
            {item.minifig_count && <span>{item.minifig_count} figs</span>}
            {item.dimensions && <span>{item.dimensions}</span>}
          </div>

          {/* Watchlist + Buy rating */}
          <div className='mt-3 flex items-center gap-2'>
            <button
              disabled={watchlistLoading}
              onClick={async () => {
                setWatchlistLoading(true);
                try {
                  const res = await fetch(`/api/items/${setNumber}/watchlist`, {
                    method: 'PATCH',
                  });
                  const json = await res.json();
                  if (json.success) {
                    setItem((prev) =>
                      prev ? { ...prev, watchlist: json.data.watchlist } : prev
                    );
                  }
                } finally {
                  setWatchlistLoading(false);
                }
              }}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all disabled:opacity-50 ${
                item.watchlist
                  ? 'border-yellow-300 bg-yellow-100 text-yellow-800 dark:border-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                  : 'border-border text-muted-foreground hover:border-foreground/30'
              }`}
            >
              {watchlistLoading ? (
                <Loader2 className='size-3.5 animate-spin' />
              ) : item.watchlist ? (
                <Eye className='size-3.5' />
              ) : (
                <EyeOff className='size-3.5' />
              )}
              {item.watchlist ? 'Watching' : 'Watch'}
            </button>
            <span className='border-border mx-1 h-4 border-l' />
            {BUY_RATING_OPTIONS.map((opt) => {
              const isActive = item.buy_rating === opt.value;
              return (
                <button
                  key={opt.value}
                  disabled={buyRatingLoading !== null}
                  onClick={async () => {
                    const newRating = isActive ? null : opt.value;
                    setBuyRatingLoading(opt.value);
                    try {
                      const res = await fetch(`/api/items/${setNumber}/buy-rating`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ rating: newRating }),
                      });
                      const json = await res.json();
                      if (json.success) {
                        setItem((prev) =>
                          prev ? { ...prev, buy_rating: newRating } : prev
                        );
                      }
                    } finally {
                      setBuyRatingLoading(null);
                    }
                  }}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-all disabled:opacity-50 ${
                    isActive
                      ? opt.color
                      : 'border-border text-muted-foreground hover:border-foreground/30'
                  }`}
                >
                  {buyRatingLoading === opt.value ? (
                    <Loader2 className='size-3 animate-spin' />
                  ) : (
                    opt.label
                  )}
                </button>
              );
            })}
          </div>

          {/* Enrich dropdown */}
          <div className='mt-3 flex items-center gap-3'>
            <DropdownMenu>
              <DropdownMenuTrigger
                disabled={enrichStatus === 'loading'}
                className='inline-flex items-center gap-1.5 rounded-md border border-blue-300 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50'
              >
                {enrichStatus === 'loading' ? 'Enriching...' : 'Enrich Metadata'}
                <ChevronDownIcon className='size-3.5' />
              </DropdownMenuTrigger>
              <DropdownMenuContent align='start'>
                <DropdownMenuItem onClick={() => handleEnrich(null)}>
                  All Sources
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {ENRICH_SOURCES.filter((s) => s.id !== null).map((s) => (
                  <DropdownMenuItem
                    key={s.id}
                    onClick={() => handleEnrich(s.id)}
                  >
                    {s.label}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleBrickeconomyScrape}>
                  BrickEconomy
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleKeepaScrape}>
                  Keepa
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleShopeeSaturation}>
                  Find Shopee Saturation
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleShopeeCompetition}>
                  Scan Shopee Competition
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {enrichMessage && (
              <span
                className={`text-xs ${enrichStatus === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}
              >
                {enrichMessage}
              </span>
            )}

            {/* List on marketplace -- only shown for portfolio items */}
            {item.in_portfolio && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  disabled={listingStatus === 'loading'}
                  className='inline-flex items-center gap-1.5 rounded-md border border-green-300 bg-green-50 px-3 py-1.5 text-sm font-medium text-green-700 transition-colors hover:bg-green-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-green-700 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50'
                >
                  <Store className='size-3.5' />
                  {listingStatus === 'loading' ? 'Opening...' : 'List'}
                  <ChevronDownIcon className='size-3.5' />
                </DropdownMenuTrigger>
                <DropdownMenuContent align='start'>
                  <DropdownMenuItem onClick={() => handleListOn('shopee')}>
                    Shopee MY
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleListOn('carousell')}>
                    Carousell MY
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleListOn('facebook')}>
                    Facebook Marketplace
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {listingMessage && (
              <span
                className={`text-xs ${listingStatus === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}
              >
                {listingMessage}
              </span>
            )}
          </div>

          {/* ML Prediction */}
          {item.ml_prediction ? (
            <div className='mt-3 flex items-center gap-3 text-sm'>
              <span className='font-medium'>ML Growth:</span>
              <span className={`font-mono font-semibold ${
                item.ml_prediction.growth_pct > 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}>
                {item.ml_prediction.growth_pct > 0 ? '+' : ''}{item.ml_prediction.growth_pct}%
              </span>
              <span className='text-muted-foreground'>
                ({item.ml_prediction.confidence}, T{item.ml_prediction.tier})
              </span>
              {item.ml_prediction.avoid_probability != null && (
                <span className='text-muted-foreground'>
                  Avoid: {(item.ml_prediction.avoid_probability * 100).toFixed(0)}%
                </span>
              )}
              {item.ml_prediction.kelly_fraction != null && (
                <span className='text-muted-foreground'>
                  Kelly: {(item.ml_prediction.kelly_fraction * 100).toFixed(1)}%
                </span>
              )}
            </div>
          ) : (
            <div className='mt-3'>
              <button
                onClick={handleMlPredict}
                disabled={mlPredicting}
                className='inline-flex items-center gap-1.5 rounded-md border border-purple-300 bg-purple-50 px-3 py-1.5 text-sm font-medium text-purple-700 transition-colors hover:bg-purple-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-purple-700 dark:bg-purple-900/30 dark:text-purple-300 dark:hover:bg-purple-900/50'
              >
                {mlPredicting ? 'Predicting...' : 'Run ML Predict'}
              </button>
            </div>
          )}

          {/* Latest prices summary */}
          <div className='mt-4 flex flex-wrap gap-3'>
            {Array.from(latestBySource.entries()).map(([source, record]) => {
              const url = getSourceUrl(source, record, setNumber);
              const Card = url ? 'a' : 'div';
              const linkProps = url
                ? { href: url, target: '_blank', rel: 'noopener noreferrer' }
                : {};
              return (
                <Card
                  key={source}
                  {...linkProps}
                  className={`border-border rounded-lg border px-3 py-2 transition-colors ${
                    url
                      ? 'hover:border-foreground/30 hover:bg-muted/50 cursor-pointer'
                      : ''
                  }`}
                >
                  <div className='text-muted-foreground flex items-center gap-1 text-xs'>
                    {SOURCE_LABELS[source] ?? source}
                    {url && (
                      <ExternalLinkIcon className='size-3 opacity-50' />
                    )}
                  </div>
                  <div className='mt-0.5 font-mono text-lg font-semibold'>
                    {formatPrice(record.price_cents, record.currency)}
                  </div>
                  <div className='text-muted-foreground text-xs'>
                    {new Date(record.recorded_at).toLocaleDateString()}
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </div>

      {/* Listing helper */}
      <ListingPanel item={item} />

      {/* Investment analysis: buy signal, returns, discount scenarios */}
      <InvestmentPanel setNumber={setNumber} />

      {/* ML growth prediction */}
      <MLPredictionPanel setNumber={setNumber} />

      {/* Cohort rankings */}
      <CohortPanel setNumber={setNumber} />
      <LiquidityPanel setNumber={setNumber} />

      {/* Minifigures */}
      <MinifiguresPanel setNumber={setNumber} />

      {/* Minifigure value trend chart */}
      <MinifigureValueChart
        setNumber={setNumber}
        globalDateRange={globalDateRange}
        onDateRange={(r) => reportDateRange('minifig', r)}
      />

      {/* Keepa Amazon price history */}
      <KeepaPanel
        setNumber={setNumber}
        globalDateRange={globalDateRange}
        onDateRange={(r) => reportDateRange('keepa', r)}
      />

      {/* BrickEconomy valuation panel */}
      <BrickeconomyPanel
        setNumber={setNumber}
        globalDateRange={globalDateRange}
        onDateRange={(r) => reportDateRange('brickeconomy', r)}
      />

      {/* Shopee competition tracker */}
      <CompetitionPanel
        setNumber={setNumber}
        globalDateRange={globalDateRange}
        onDateRange={(r) => reportDateRange('competition', r)}
      />

      {/* BrickLink price analysis charts */}
      <BricklinkPriceChart
        setNumber={setNumber}
        globalDateRange={globalDateRange}
        onDateRange={(r) => reportDateRange('bricklink', r)}
      />

      {/* BrickLink seller snapshot — Asia stats + global lowest */}
      <BricklinkSellersPanel setNumber={setNumber} />

      {/* Capital allocation (Kelly) */}
      <CapitalAllocationPanel setNumber={setNumber} />

      {/* Price history table */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Price History</h2>
        {item.prices.length === 0 ? (
          <p className='text-muted-foreground text-sm'>
            No price records yet.
          </p>
        ) : (
          <div className='h-[500px]'>
            <DataTable table={priceTable} />
          </div>
        )}
      </div>
    </div>
    </DetailBundleProvider>
  );
}

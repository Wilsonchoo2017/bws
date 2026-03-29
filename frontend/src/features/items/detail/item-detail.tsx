'use client';

import { ChevronDownIcon, ExternalLinkIcon } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { ItemDetail, PriceRecord } from '../types';
import { formatPrice } from '../types';
import { KellyPanel } from '../kelly-panel';
import { SignalsPanel } from '../signals-table';
import { BricklinkPriceChart } from './bricklink-price-chart';

const ENRICH_SOURCES = [
  { id: null, label: 'All Sources' },
  { id: 'bricklink', label: 'Bricklink' },
  { id: 'worldbricks', label: 'WorldBricks' },
  { id: 'brickranker', label: 'BrickRanker' },
] as const;

const SOURCE_LABELS: Record<string, string> = {
  shopee: 'Shopee MY',
  bricklink_new: 'Bricklink (New)',
  bricklink_used: 'Bricklink (Used)',
  toysrus: 'Toys R Us MY',
};

function getSourceUrl(source: string, record: PriceRecord, setNumber: string): string | null {
  if (record.url) return record.url;

  if (source === 'bricklink_new' || source === 'bricklink_used') {
    return `https://www.bricklink.com/v2/catalog/catalogitem.page?S=${setNumber}-1#T=P`;
  }

  return null;
}

const SOURCE_COLORS: Record<string, string> = {
  shopee: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  bricklink_new:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  bricklink_used:
    'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300',
  toysrus:
    'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300'
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
  const latestBySource = new Map<string, PriceRecord>();
  for (const p of item.prices) {
    const existing = latestBySource.get(p.source);
    if (!existing || p.recorded_at > existing.recorded_at) {
      latestBySource.set(p.source, p);
    }
  }

  return (
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
            className='h-32 w-32 rounded-lg object-cover'
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
              </DropdownMenuContent>
            </DropdownMenu>
            {enrichMessage && (
              <span
                className={`text-xs ${enrichStatus === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}
              >
                {enrichMessage}
              </span>
            )}
          </div>

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

      {/* Trading signals */}
      <SignalsPanel setNumber={setNumber} />

      {/* Kelly Criterion position sizing */}
      <KellyPanel setNumber={setNumber} />

      {/* BrickLink price analysis charts */}
      <BricklinkPriceChart setNumber={setNumber} />

      {/* Price history table */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Price History</h2>
        {item.prices.length === 0 ? (
          <p className='text-muted-foreground text-sm'>
            No price records yet.
          </p>
        ) : (
          <div className='max-h-[500px] overflow-auto rounded border'>
            <table className='w-full text-sm'>
              <thead className='bg-muted/50 sticky top-0'>
                <tr>
                  <th className='px-3 py-2 text-left font-medium'>Source</th>
                  <th className='px-3 py-2 text-right font-medium'>Price</th>
                  <th className='px-3 py-2 text-left font-medium'>Listing</th>
                  <th className='px-3 py-2 text-left font-medium'>Seller</th>
                  <th className='px-3 py-2 text-left font-medium'>Date</th>
                </tr>
              </thead>
              <tbody>
                {[...item.prices].reverse().map((record, i) => (
                  <tr key={i} className='border-border border-t'>
                    <td className='px-3 py-2'>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${SOURCE_COLORS[record.source] ?? ''}`}
                      >
                        {SOURCE_LABELS[record.source] ?? record.source}
                      </span>
                    </td>
                    <td className='whitespace-nowrap px-3 py-2 text-right font-mono'>
                      {formatPrice(record.price_cents, record.currency)}
                    </td>
                    <td className='max-w-xs truncate px-3 py-2'>
                      {record.url ? (
                        <a
                          href={record.url}
                          target='_blank'
                          rel='noopener noreferrer'
                          className='text-primary hover:underline'
                        >
                          {record.title ?? 'View'}
                        </a>
                      ) : (
                        <span className='text-muted-foreground'>
                          {record.title ?? '-'}
                        </span>
                      )}
                    </td>
                    <td className='text-muted-foreground px-3 py-2'>
                      {record.shop_name ?? '-'}
                    </td>
                    <td className='text-muted-foreground whitespace-nowrap px-3 py-2 text-xs'>
                      {new Date(record.recorded_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

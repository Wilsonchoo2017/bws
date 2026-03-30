'use client';

import { ExternalLinkIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { SetMinifigureData } from '../types';
import { formatPrice } from '../types';

interface MinifiguresPanelProps {
  setNumber: string;
}

type ScrapeStatus = 'idle' | 'loading' | 'success' | 'error';

export function MinifiguresPanel({ setNumber }: MinifiguresPanelProps) {
  const [data, setData] = useState<SetMinifigureData | null>(null);
  const [loading, setLoading] = useState(true);
  const [scrapeStatus, setScrapeStatus] = useState<ScrapeStatus>('idle');
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);

  const fetchMinifigures = () => {
    fetch(`/api/items/${setNumber}/minifigures`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchMinifigures();
  }, [setNumber]);

  const handleScrape = async () => {
    setScrapeStatus('loading');
    setScrapeMessage(null);

    try {
      const res = await fetch(`/api/items/${setNumber}/minifigures/scrape`, {
        method: 'POST',
      });
      const json = await res.json();

      if (json.success) {
        setScrapeStatus('success');
        setScrapeMessage(
          `Scraped ${json.data.minifigures_scraped} of ${json.data.minifig_count} minifigures`
        );
        fetchMinifigures();
      } else {
        setScrapeStatus('error');
        setScrapeMessage(json.error ?? 'Scrape failed');
      }
    } catch (err) {
      setScrapeStatus('error');
      setScrapeMessage(
        err instanceof Error ? err.message : 'Failed to scrape minifigures'
      );
    }
  };

  if (loading) {
    return null;
  }

  if (!data || data.minifig_count === 0) {
    return (
      <div>
        <div className='flex items-center justify-between mb-3'>
          <h2 className='text-lg font-semibold'>Minifigures</h2>
          <button
            onClick={handleScrape}
            disabled={scrapeStatus === 'loading'}
            className='rounded-md border border-blue-300 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50'
          >
            {scrapeStatus === 'loading' ? 'Scraping...' : 'Scrape Minifigures'}
          </button>
        </div>
        {scrapeMessage && (
          <p className={`text-xs mb-2 ${scrapeStatus === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}>
            {scrapeMessage}
          </p>
        )}
        <p className='text-muted-foreground text-sm'>
          No minifigure data available. Click "Scrape Minifigures" to fetch.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className='flex items-center justify-between mb-3'>
        <div className='flex items-center gap-3'>
          <h2 className='text-lg font-semibold'>
            Minifigures ({data.minifig_count})
          </h2>
          {data.total_value_cents !== null && (
            <span className='text-sm text-muted-foreground'>
              Total value:{' '}
              <span className='font-mono font-semibold text-foreground'>
                {formatPrice(data.total_value_cents, data.total_value_currency)}
              </span>
            </span>
          )}
        </div>
        <button
          onClick={handleScrape}
          disabled={scrapeStatus === 'loading'}
          className='rounded-md border border-blue-300 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-900/50'
        >
          {scrapeStatus === 'loading' ? 'Scraping...' : 'Refresh Prices'}
        </button>
      </div>

      {scrapeMessage && (
        <p className={`text-xs mb-2 ${scrapeStatus === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}>
          {scrapeMessage}
        </p>
      )}

      <div className='overflow-auto rounded border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/50 sticky top-0'>
            <tr>
              <th className='px-3 py-2 text-left font-medium'>Minifig</th>
              <th className='px-3 py-2 text-left font-medium'>Name</th>
              <th className='px-3 py-2 text-center font-medium'>Qty</th>
              <th className='px-3 py-2 text-right font-medium'>New Price</th>
              <th className='px-3 py-2 text-right font-medium'>Used Price</th>
              <th className='px-3 py-2 text-right font-medium'>Subtotal (New)</th>
            </tr>
          </thead>
          <tbody>
            {data.minifigures.map((mf) => {
              const bricklinkUrl = `https://www.bricklink.com/v2/catalog/catalogitem.page?M=${mf.minifig_id}#T=P`;
              const subtotal =
                mf.current_new_avg_cents !== null
                  ? mf.current_new_avg_cents * mf.quantity
                  : null;

              return (
                <tr key={mf.minifig_id} className='border-border border-t'>
                  <td className='px-3 py-2'>
                    <div className='flex items-center gap-2'>
                      {mf.image_url && (
                        <img
                          src={mf.image_url}
                          alt={mf.name ?? mf.minifig_id}
                          className='h-10 w-10 rounded object-cover'
                        />
                      )}
                      <a
                        href={bricklinkUrl}
                        target='_blank'
                        rel='noopener noreferrer'
                        className='text-primary hover:underline flex items-center gap-1 font-mono text-xs'
                      >
                        {mf.minifig_id}
                        <ExternalLinkIcon className='size-3 opacity-50' />
                      </a>
                    </div>
                  </td>
                  <td className='px-3 py-2'>{mf.name ?? '-'}</td>
                  <td className='px-3 py-2 text-center'>{mf.quantity}</td>
                  <td className='whitespace-nowrap px-3 py-2 text-right font-mono'>
                    {formatPrice(mf.current_new_avg_cents, mf.currency)}
                  </td>
                  <td className='whitespace-nowrap px-3 py-2 text-right font-mono'>
                    {formatPrice(mf.current_used_avg_cents, mf.currency)}
                  </td>
                  <td className='whitespace-nowrap px-3 py-2 text-right font-mono font-semibold'>
                    {formatPrice(subtotal, mf.currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { ScraperConfig, ScrapeTarget, ScrapeItem } from './types';

interface ScraperDashboardProps {
  scraper: ScraperConfig;
}

export function ScraperDashboard({ scraper }: ScraperDashboardProps) {
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ScrapeItem[]>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [customUrl, setCustomUrl] = useState('');

  async function runScrape(target: ScrapeTarget) {
    setRunning(target.id);
    setErrors((prev) => ({ ...prev, [target.id]: '' }));

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scraperId: scraper.id,
          url: target.url
        })
      });

      const data = await res.json();

      if (data.success) {
        setResults((prev) => ({ ...prev, [target.id]: data.items }));
      } else {
        setErrors((prev) => ({
          ...prev,
          [target.id]: data.error || 'Scrape failed'
        }));
      }
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [target.id]: err instanceof Error ? err.message : 'Network error'
      }));
    } finally {
      setRunning(null);
    }
  }

  async function runCustomScrape() {
    if (!customUrl.trim()) return;

    const customTarget: ScrapeTarget = {
      id: 'custom',
      label: 'Custom URL',
      url: customUrl.trim(),
      description: ''
    };

    await runScrape(customTarget);
  }

  return (
    <div className='flex flex-col gap-6'>
      {/* Predefined targets */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Targets</h2>
        <div className='flex flex-col gap-3'>
          {scraper.targets.map((target) => (
            <div
              key={target.id}
              className='border-border rounded-lg border p-4'
            >
              <div className='flex items-start justify-between gap-4'>
                <div className='min-w-0 flex-1'>
                  <h3 className='font-medium'>{target.label}</h3>
                  <p className='text-muted-foreground mt-0.5 text-sm'>
                    {target.description}
                  </p>
                  <code className='text-muted-foreground mt-1 block truncate text-xs'>
                    {target.url}
                  </code>
                </div>
                <Button
                  onClick={() => runScrape(target)}
                  disabled={running !== null}
                  size='sm'
                >
                  {running === target.id ? 'Scraping...' : 'Run'}
                </Button>
              </div>

              {errors[target.id] && (
                <div className='mt-3 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300'>
                  {errors[target.id]}
                </div>
              )}

              {results[target.id] && (
                <ResultsTable items={results[target.id]} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Custom URL */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Custom URL</h2>
        <div className='border-border rounded-lg border p-4'>
          <div className='flex gap-2'>
            <input
              type='url'
              placeholder='https://shopee.com.my/...'
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              className='border-border bg-background flex-1 rounded-md border px-3 py-2 text-sm'
            />
            <Button
              onClick={runCustomScrape}
              disabled={running !== null || !customUrl.trim()}
              size='sm'
            >
              {running === 'custom' ? 'Scraping...' : 'Scrape'}
            </Button>
          </div>

          {errors['custom'] && (
            <div className='mt-3 rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300'>
              {errors['custom']}
            </div>
          )}

          {results['custom'] && <ResultsTable items={results['custom']} />}
        </div>
      </div>
    </div>
  );
}

function ResultsTable({ items }: { items: ScrapeItem[] }) {
  if (items.length === 0) {
    return (
      <p className='text-muted-foreground mt-3 text-sm'>No items found.</p>
    );
  }

  return (
    <div className='mt-3'>
      <p className='text-muted-foreground mb-2 text-sm'>
        {items.length} items found
      </p>
      <div className='max-h-96 overflow-auto rounded border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/50 sticky top-0'>
            <tr>
              <th className='px-3 py-2 text-left font-medium'>Image</th>
              <th className='px-3 py-2 text-left font-medium'>Title</th>
              <th className='px-3 py-2 text-right font-medium'>Price</th>
              <th className='px-3 py-2 text-right font-medium'>Sold</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className='border-border border-t'>
                <td className='px-3 py-2'>
                  {item.image_url && (
                    <img
                      src={item.image_url}
                      alt=''
                      className='h-10 w-10 rounded object-cover'
                    />
                  )}
                </td>
                <td className='max-w-xs truncate px-3 py-2'>
                  {item.product_url ? (
                    <a
                      href={item.product_url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-primary hover:underline'
                    >
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </td>
                <td className='whitespace-nowrap px-3 py-2 text-right font-mono'>
                  {item.price_display}
                </td>
                <td className='text-muted-foreground whitespace-nowrap px-3 py-2 text-right'>
                  {item.sold_count || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

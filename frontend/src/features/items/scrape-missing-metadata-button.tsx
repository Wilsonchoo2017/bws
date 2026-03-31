'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface ScrapeMissingMetadataButtonProps {
  setNumbers: string[];
}

export function ScrapeMissingMetadataButton({ setNumbers }: ScrapeMissingMetadataButtonProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const handleClick = async () => {
    if (setNumbers.length === 0) return;

    setStatus('loading');
    setMessage(null);

    try {
      const res = await fetch('/api/enrichment/enrich-missing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_numbers: setNumbers }),
      });
      const json = await res.json();

      if (!json.success) {
        setStatus('error');
        setMessage(json.error ?? 'Failed');
        return;
      }

      const { queued, set_numbers: queued_numbers } = json.data;
      if (queued === 0) {
        setStatus('success');
        setMessage('All items already have metadata');
      } else {
        setStatus('success');
        setMessage(`Queued ${queued}: ${queued_numbers.slice(0, 5).join(', ')}${queued > 5 ? '...' : ''}`);
      }
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Network error');
    }
  };

  if (setNumbers.length === 0) return null;

  return (
    <div className='flex items-center gap-3'>
      {message && (
        <span
          className={`text-xs ${status === 'error' ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}
        >
          {message}
        </span>
      )}
      <Button
        variant='outline'
        size='sm'
        onClick={handleClick}
        disabled={status === 'loading'}
      >
        {status === 'loading' ? 'Scraping...' : `Scrape Metadata (${setNumbers.length})`}
      </Button>
    </div>
  );
}

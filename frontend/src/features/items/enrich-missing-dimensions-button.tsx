'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface EnrichMissingDimensionsButtonProps {
  setNumbers?: string[];
}

export function EnrichMissingDimensionsButton({ setNumbers }: EnrichMissingDimensionsButtonProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const handleClick = async () => {
    setStatus('loading');
    setMessage(null);

    try {
      const hasFilter = setNumbers && setNumbers.length > 0;
      const res = await fetch('/api/enrichment/enrich-missing-dimensions', {
        method: 'POST',
        ...(hasFilter
          ? {
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ set_numbers: setNumbers }),
            }
          : {}),
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
        setMessage('All items already have dimensions');
      } else {
        setStatus('success');
        setMessage(`Queued ${queued}: ${queued_numbers.slice(0, 5).join(', ')}${queued > 5 ? '...' : ''}`);
      }
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Network error');
    }
  };

  const count = setNumbers?.length;
  const label = count ? `Enrich Dims (${count})` : 'Enrich Dims';

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
        disabled={status === 'loading' || count === 0}
      >
        {status === 'loading' ? 'Enriching...' : label}
      </Button>
    </div>
  );
}

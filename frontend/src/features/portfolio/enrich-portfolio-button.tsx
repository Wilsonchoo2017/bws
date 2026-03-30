'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

type Status = 'idle' | 'loading' | 'success' | 'error';

export function EnrichPortfolioButton() {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const handleClick = async () => {
    setStatus('loading');
    setMessage(null);

    try {
      const res = await fetch('/api/portfolio/enrich', { method: 'POST' });
      const json = await res.json();

      if (!json.success) {
        setStatus('error');
        setMessage(json.error ?? 'Failed');
        return;
      }

      const { queued, set_numbers } = json.data;
      setStatus('success');
      if (queued === 0) {
        setMessage('No portfolio sets found');
      } else {
        setMessage(
          `Queued ${queued}: ${set_numbers.slice(0, 5).join(', ')}${queued > 5 ? '...' : ''}`
        );
      }
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Network error');
    }
  };

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
        {status === 'loading' ? 'Enriching...' : 'Enrich All'}
      </Button>
    </div>
  );
}

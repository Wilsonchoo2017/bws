'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

type Status = 'idle' | 'loading' | 'success' | 'error';

export function SyncRetirementButton() {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const handleClick = async () => {
    setStatus('loading');
    setMessage(null);

    try {
      const res = await fetch('/api/enrichment/sync-retirement', {
        method: 'POST',
      });
      const json = await res.json();

      if (!json.success) {
        setStatus('error');
        setMessage(json.error ?? 'Failed');
        return;
      }

      const { synced, cleared, set_numbers } = json.data;
      if (synced === 0 && cleared === 0) {
        setStatus('success');
        setMessage('Retirement status already in sync');
      } else {
        const parts: string[] = [];
        if (synced > 0) {
          parts.push(`${synced} marked retiring: ${set_numbers.slice(0, 5).join(', ')}${synced > 5 ? '...' : ''}`);
        }
        if (cleared > 0) {
          parts.push(`${cleared} cleared`);
        }
        setStatus('success');
        setMessage(parts.join(' | '));
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
        {status === 'loading' ? 'Syncing...' : 'Sync Retirement'}
      </Button>
    </div>
  );
}

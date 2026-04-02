'use client';

import { Button } from '@/components/ui/button';
import { useAsyncAction } from '@/lib/hooks/use-async-action';

export function SyncRetirementButton() {
  const { status, message, execute } = useAsyncAction({
    endpoint: '/api/enrichment/sync-retirement',
    onSuccess: (data) => {
      const synced = data.synced as number;
      const cleared = data.cleared as number;
      const setNumbers = data.set_numbers as string[];

      if (synced === 0 && cleared === 0) return 'Retirement status already in sync';

      const parts: string[] = [];
      if (synced > 0) {
        parts.push(`${synced} marked retiring: ${setNumbers.slice(0, 5).join(', ')}${synced > 5 ? '...' : ''}`);
      }
      if (cleared > 0) {
        parts.push(`${cleared} cleared`);
      }
      return parts.join(' | ');
    },
  });

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
        onClick={execute}
        disabled={status === 'loading'}
      >
        {status === 'loading' ? 'Syncing...' : 'Sync Retirement'}
      </Button>
    </div>
  );
}

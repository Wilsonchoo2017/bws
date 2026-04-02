'use client';

import { Button } from '@/components/ui/button';
import { useAsyncAction, formatQueuedMessage } from '@/lib/hooks/use-async-action';

export function EnrichPortfolioButton() {
  const { status, message, execute } = useAsyncAction({
    endpoint: '/api/portfolio/enrich',
    onSuccess: (data) =>
      formatQueuedMessage(data, 'No portfolio sets found'),
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
        {status === 'loading' ? 'Enriching...' : 'Enrich All'}
      </Button>
    </div>
  );
}

'use client';

import { Button } from '@/components/ui/button';
import { useAsyncAction, formatQueuedMessage } from '@/lib/hooks/use-async-action';

interface ScrapeMissingMetadataButtonProps {
  setNumbers: string[];
}

export function ScrapeMissingMetadataButton({ setNumbers }: ScrapeMissingMetadataButtonProps) {
  const { status, message, execute } = useAsyncAction({
    endpoint: '/api/enrichment/enrich-missing',
    buildBody: () => ({ set_numbers: setNumbers }),
    onSuccess: (data) =>
      formatQueuedMessage(data, 'All items already have metadata'),
  });

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
        onClick={execute}
        disabled={status === 'loading'}
      >
        {status === 'loading' ? 'Scraping...' : `Scrape Metadata (${setNumbers.length})`}
      </Button>
    </div>
  );
}

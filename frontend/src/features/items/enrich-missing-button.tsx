'use client';

import { Button } from '@/components/ui/button';
import { useAsyncAction, formatQueuedMessage } from '@/lib/hooks/use-async-action';

interface EnrichMissingButtonProps {
  setNumbers?: string[];
}

export function EnrichMissingButton({ setNumbers }: EnrichMissingButtonProps) {
  const { status, message, execute } = useAsyncAction({
    endpoint: '/api/enrichment/enrich-missing',
    buildBody: () => {
      const hasFilter = setNumbers && setNumbers.length > 0;
      return hasFilter ? { set_numbers: setNumbers } : undefined;
    },
    onSuccess: (data) =>
      formatQueuedMessage(data, 'All items already have metadata'),
  });

  const count = setNumbers?.length;
  const label = count ? `Enrich Filtered (${count})` : 'Enrich Missing';

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
        {status === 'loading' ? 'Enriching...' : label}
      </Button>
    </div>
  );
}

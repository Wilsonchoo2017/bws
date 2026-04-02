'use client';

import { useState } from 'react';

export type AsyncActionStatus = 'idle' | 'loading' | 'success' | 'error';

interface UseAsyncActionOptions {
  endpoint: string;
  buildBody?: () => Record<string, unknown> | undefined;
  onSuccess: (data: Record<string, unknown>) => string;
}

export function useAsyncAction({ endpoint, buildBody, onSuccess }: UseAsyncActionOptions) {
  const [status, setStatus] = useState<AsyncActionStatus>('idle');
  const [message, setMessage] = useState<string | null>(null);

  const execute = async () => {
    setStatus('loading');
    setMessage(null);

    try {
      const body = buildBody?.();
      const res = await fetch(endpoint, {
        method: 'POST',
        ...(body
          ? {
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            }
          : {}),
      });
      const json = await res.json();

      if (!json.success) {
        setStatus('error');
        setMessage(json.error ?? 'Failed');
        return;
      }

      setStatus('success');
      setMessage(onSuccess(json.data));
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Network error');
    }
  };

  return { status, message, execute } as const;
}

export function formatQueuedMessage(
  data: Record<string, unknown>,
  emptyMessage: string
): string {
  const queued = data.queued as number;
  const setNumbers = data.set_numbers as string[];
  if (queued === 0) return emptyMessage;
  return `Queued ${queued}: ${setNumbers.slice(0, 5).join(', ')}${queued > 5 ? '...' : ''}`;
}

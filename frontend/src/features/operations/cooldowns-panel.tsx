'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

interface CooldownSource {
  source: string;
  source_name: string;
  is_blocked: boolean;
  cooldown_remaining_s: number;
  escalation_level: number;
  consecutive_failures: number;
  max_per_hour: number | null;
  requests_this_hour: number | null;
}

function formatCooldownTime(seconds: number): string {
  if (seconds <= 0) return '';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function CooldownsPanel() {
  const [sources, setSources] = useState<readonly CooldownSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<string | null>(null);

  const fetchCooldowns = useCallback(async () => {
    try {
      const res = await fetch('/api/stats/cooldowns');
      const json = await res.json();
      if (json.success) {
        setSources(json.data);
        setError(null);
      } else {
        setError(json.error ?? 'Failed to load');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCooldowns();
    const interval = setInterval(fetchCooldowns, 5000);
    return () => clearInterval(interval);
  }, [fetchCooldowns]);

  const resetCooldown = useCallback(
    async (source: string) => {
      setResetting(source);
      try {
        const res = await fetch(`/api/stats/cooldowns/${source}/reset`, {
          method: 'POST',
        });
        const json = await res.json();
        if (json.success) {
          await fetchCooldowns();
        }
      } catch {
        // refresh to show current state
        await fetchCooldowns();
      } finally {
        setResetting(null);
      }
    },
    [fetchCooldowns]
  );

  if (loading) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-muted-foreground'>Loading cooldowns...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-destructive'>{error}</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className='text-muted-foreground py-8 text-center text-sm'>
        No rate limiters registered.
      </div>
    );
  }

  return (
    <div className='grid gap-3 sm:grid-cols-2'>
      {sources.map((src) => (
        <CooldownCard
          key={src.source}
          source={src}
          onReset={() => resetCooldown(src.source)}
          isResetting={resetting === src.source}
        />
      ))}
    </div>
  );
}

function CooldownCard({
  source,
  onReset,
  isResetting,
}: {
  readonly source: CooldownSource;
  readonly onReset: () => void;
  readonly isResetting: boolean;
}) {
  const blocked = source.is_blocked;
  const remaining = formatCooldownTime(source.cooldown_remaining_s);

  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        blocked
          ? 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/20'
          : 'border-border'
      }`}
    >
      <div className='flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              blocked
                ? 'bg-red-500'
                : 'bg-green-500'
            }`}
          />
          <span className='text-sm font-medium'>{source.source_name}</span>
        </div>
        {blocked && (
          <Button
            variant='outline'
            size='sm'
            onClick={onReset}
            disabled={isResetting}
            className='h-7 px-2 text-xs'
          >
            {isResetting ? 'Resetting...' : 'Reset'}
          </Button>
        )}
      </div>

      <div className='mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs'>
        {/* Status */}
        <div>
          <span className='text-muted-foreground'>Status: </span>
          {blocked ? (
            <span className='font-medium text-red-600 dark:text-red-400'>
              Blocked {remaining && `(${remaining})`}
            </span>
          ) : (
            <span className='font-medium text-green-600 dark:text-green-400'>
              Active
            </span>
          )}
        </div>

        {/* Rate */}
        {source.max_per_hour != null && source.requests_this_hour != null && (
          <div>
            <span className='text-muted-foreground'>Rate: </span>
            <span className='font-mono'>
              {source.requests_this_hour}/{source.max_per_hour}
            </span>
            <span className='text-muted-foreground'>/hr</span>
          </div>
        )}

        {/* Escalation */}
        {source.escalation_level > 0 && (
          <div>
            <span className='text-muted-foreground'>Escalation: </span>
            <span className='font-mono text-yellow-600 dark:text-yellow-400'>
              L{source.escalation_level}
            </span>
          </div>
        )}

        {/* Failures */}
        {source.consecutive_failures > 0 && (
          <div>
            <span className='text-muted-foreground'>Failures: </span>
            <span className='font-mono text-red-600 dark:text-red-400'>
              {source.consecutive_failures}
            </span>
          </div>
        )}
      </div>

      {/* Cooldown progress bar */}
      {blocked && source.cooldown_remaining_s > 0 && (
        <div className='mt-2'>
          <div className='h-1.5 overflow-hidden rounded-full bg-red-200 dark:bg-red-900'>
            <div
              className='h-full rounded-full bg-red-500 transition-all'
              style={{
                width: `${Math.min(100, (source.cooldown_remaining_s / maxCooldownForLevel(source.escalation_level)) * 100)}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function maxCooldownForLevel(level: number): number {
  // Matches HourlyRateLimiter escalation: base 3600 * 2^level, max 28800
  const base = 3600;
  return Math.min(base * 2 ** Math.max(0, level - 1), 28800);
}

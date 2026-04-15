'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { WorkersPanel } from './workers-panel';
import { CoveragePanel } from './coverage-panel';
import { CooldownsPanel } from './cooldowns-panel';
import { SettingsPanel } from './settings-panel';
import { MLPanel } from './ml-panel';
import { ShopeeCaptchaPanel } from './shopee-captcha-panel';
import type { QueueStats, WorkerJob } from './types';

type Tab =
  | 'workers'
  | 'cooldowns'
  | 'coverage'
  | 'settings'
  | 'ml'
  | 'shopee';

const TABS: ReadonlyArray<{ readonly id: Tab; readonly label: string }> = [
  { id: 'workers', label: 'Workers' },
  { id: 'shopee', label: 'Shopee' },
  { id: 'cooldowns', label: 'Cooldowns' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'ml', label: 'ML' },
  { id: 'settings', label: 'Settings' },
];

export function OperationsDashboard() {
  const [tab, setTab] = useState<Tab>('workers');
  const [jobs, setJobs] = useState<WorkerJob[]>([]);
  const [serverStats, setServerStats] = useState<QueueStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [captchaPending, setCaptchaPending] = useState(0);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch('/api/workers');
      const json = await res.json();
      if (json.success) {
        setJobs(json.data);
        setServerStats(json.stats ?? null);
        setError(null);
      } else {
        setError(json.error ?? 'Failed to load jobs');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Poll captcha event count for badge on the Shopee tab
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch('/api/scrape/shopee/captcha-events?limit=1');
        if (!res.ok) return;
        const json = await res.json();
        if (!cancelled) setCaptchaPending(json.pending_count ?? 0);
      } catch {
        /* ignore */
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (autoRefresh && tab === 'workers') {
      pollRef.current = setInterval(fetchJobs, 3000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [autoRefresh, tab, fetchJobs]);

  const clearJobs = useCallback(async () => {
    try {
      const res = await fetch('/api/workers', { method: 'DELETE' });
      const json = await res.json();
      if (json.success) {
        await fetchJobs();
      }
    } catch {
      await fetchJobs();
    }
  }, [fetchJobs]);

  const hasActive = jobs.some(
    (j) => j.status === 'queued' || j.status === 'running'
  );

  const hasFinished = jobs.some(
    (j) => j.status === 'completed' || j.status === 'failed'
  );

  const stats: QueueStats = serverStats ?? {
    total: jobs.length,
    queued: jobs.filter((j) => j.status === 'queued').length,
    running: jobs.filter((j) => j.status === 'running').length,
    completed: jobs.filter((j) => j.status === 'completed').length,
    failed: jobs.filter((j) => j.status === 'failed').length,
  };

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading...</p>
      </div>
    );
  }

  if (error && jobs.length === 0) {
    return (
      <div className='flex h-96 flex-col items-center justify-center gap-2'>
        <p className='text-destructive'>{error}</p>
        <Button variant='outline' size='sm' onClick={fetchJobs}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className='flex flex-col gap-6'>
      {/* Header */}
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-2xl font-bold'>Operations</h1>
          <p className='text-muted-foreground text-sm'>
            Workers, job queue, and data coverage
          </p>
        </div>
        <div className='flex items-center gap-3'>
          {hasActive && (
            <span className='flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400'>
              <span className='inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500' />
              Processing
            </span>
          )}
          {tab === 'workers' && (
            <label className='flex items-center gap-2 text-sm'>
              <input
                type='checkbox'
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className='rounded'
              />
              <span className='text-muted-foreground'>Auto-refresh</span>
            </label>
          )}
          <Button variant='outline' size='sm' onClick={fetchJobs}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className='border-border flex gap-0 border-b'>
        {TABS.map((t) => (
          <button
            key={t.id}
            type='button'
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? 'border-primary text-foreground -mb-px border-b-2'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
            {t.id === 'workers' && stats.running > 0 && (
              <span className='ml-2 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-blue-100 px-1.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'>
                {stats.running}
              </span>
            )}
            {t.id === 'shopee' && captchaPending > 0 && (
              <span className='ml-2 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-orange-100 px-1.5 text-xs font-medium text-orange-700 dark:bg-orange-900/30 dark:text-orange-300'>
                {captchaPending}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'workers' && (
        <WorkersPanel
          jobs={jobs}
          stats={stats}
          onClear={clearJobs}
          hasFinished={hasFinished}
        />
      )}
      {tab === 'shopee' && <ShopeeCaptchaPanel />}
      {tab === 'cooldowns' && <CooldownsPanel />}
      {tab === 'coverage' && <CoveragePanel />}
      {tab === 'ml' && <MLPanel />}
      {tab === 'settings' && <SettingsPanel />}
    </div>
  );
}

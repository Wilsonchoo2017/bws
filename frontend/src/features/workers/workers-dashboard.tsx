'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { JobStatus, WorkerJob } from './types';
import { formatDuration, formatRelativeTime } from './types';

const SCRAPER_LABELS: Record<string, string> = {
  shopee: 'Shopee',
  toysrus: 'ToysRUs',
  enrichment: 'Enrichment',
};

const STATUS_STYLES: Record<JobStatus, string> = {
  queued:
    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  running:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  completed:
    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

type FilterStatus = 'all' | JobStatus;

export function WorkersDashboard() {
  const [jobs, setJobs] = useState<WorkerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterStatus>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch('/api/workers?limit=100');
      const json = await res.json();
      if (json.success) {
        setJobs(json.data);
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

  useEffect(() => {
    if (autoRefresh) {
      pollRef.current = setInterval(fetchJobs, 3000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [autoRefresh, fetchJobs]);

  const clearJobs = useCallback(async () => {
    try {
      const res = await fetch('/api/workers', { method: 'DELETE' });
      const json = await res.json();
      if (json.success) {
        await fetchJobs();
      }
    } catch {
      // refresh anyway to show current state
      await fetchJobs();
    }
  }, [fetchJobs]);

  const hasActive = jobs.some(
    (j) => j.status === 'queued' || j.status === 'running'
  );

  const hasFinished = jobs.some(
    (j) => j.status === 'completed' || j.status === 'failed'
  );

  const filtered =
    filter === 'all' ? jobs : jobs.filter((j) => j.status === filter);

  // Stats
  const stats = {
    total: jobs.length,
    queued: jobs.filter((j) => j.status === 'queued').length,
    running: jobs.filter((j) => j.status === 'running').length,
    completed: jobs.filter((j) => j.status === 'completed').length,
    failed: jobs.filter((j) => j.status === 'failed').length,
  };

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading jobs...</p>
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
          <h1 className='text-2xl font-bold'>Workers</h1>
          <p className='text-muted-foreground text-sm'>
            Job queue, progress, and history
          </p>
        </div>
        <div className='flex items-center gap-3'>
          {hasActive && (
            <span className='flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400'>
              <span className='inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500' />
              Processing
            </span>
          )}
          <label className='flex items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className='rounded'
            />
            <span className='text-muted-foreground'>Auto-refresh</span>
          </label>
          {hasFinished && (
            <Button variant='outline' size='sm' onClick={clearJobs}>
              Clear
            </Button>
          )}
          <Button variant='outline' size='sm' onClick={fetchJobs}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className='grid grid-cols-5 gap-3'>
        <StatCard label='Total' value={stats.total} />
        <StatCard
          label='Queued'
          value={stats.queued}
          active={filter === 'queued'}
          onClick={() => setFilter(filter === 'queued' ? 'all' : 'queued')}
          color='yellow'
        />
        <StatCard
          label='Running'
          value={stats.running}
          active={filter === 'running'}
          onClick={() => setFilter(filter === 'running' ? 'all' : 'running')}
          color='blue'
        />
        <StatCard
          label='Completed'
          value={stats.completed}
          active={filter === 'completed'}
          onClick={() =>
            setFilter(filter === 'completed' ? 'all' : 'completed')
          }
          color='green'
        />
        <StatCard
          label='Failed'
          value={stats.failed}
          active={filter === 'failed'}
          onClick={() => setFilter(filter === 'failed' ? 'all' : 'failed')}
          color='red'
        />
      </div>

      {/* Jobs table */}
      {filtered.length === 0 ? (
        <div className='text-muted-foreground py-12 text-center text-sm'>
          {filter === 'all'
            ? 'No jobs yet. Jobs will appear here when scrapers or enrichment run.'
            : `No ${filter} jobs.`}
        </div>
      ) : (
        <div className='max-h-[600px] overflow-auto rounded border'>
          <table className='w-full text-sm'>
            <thead className='bg-muted/50 sticky top-0'>
              <tr>
                <th className='px-3 py-2 text-left font-medium'>Status</th>
                <th className='px-3 py-2 text-left font-medium'>Type</th>
                <th className='px-3 py-2 text-left font-medium'>Target</th>
                <th className='px-3 py-2 text-right font-medium'>Items</th>
                <th className='px-3 py-2 text-right font-medium'>Duration</th>
                <th className='px-3 py-2 text-left font-medium'>Created</th>
                <th className='px-3 py-2 text-left font-medium'>Error</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((job) => (
                <JobRow key={job.job_id} job={job} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
  active,
  onClick,
}: {
  label: string;
  value: number;
  color?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const base = 'border-border rounded-lg border px-4 py-3 text-center';
  const interactive = onClick
    ? 'cursor-pointer transition-colors hover:bg-muted/50'
    : '';
  const ring = active ? 'ring-primary ring-2' : '';

  return (
    <button
      type='button'
      className={`${base} ${interactive} ${ring}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <div className='text-muted-foreground text-xs'>{label}</div>
      <div
        className={`mt-1 text-2xl font-bold ${
          color === 'yellow'
            ? 'text-yellow-600 dark:text-yellow-400'
            : color === 'blue'
              ? 'text-blue-600 dark:text-blue-400'
              : color === 'green'
                ? 'text-green-600 dark:text-green-400'
                : color === 'red'
                  ? 'text-red-600 dark:text-red-400'
                  : ''
        }`}
      >
        {value}
      </div>
    </button>
  );
}

function JobRow({ job }: { job: WorkerJob }) {
  // Parse enrichment target from URL: "75192" or "75192:bricklink"
  const target =
    job.scraper_id === 'enrichment' ? job.url : truncateUrl(job.url);

  return (
    <tr className='border-border border-t'>
      <td className='px-3 py-2'>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}
        >
          {job.status}
        </span>
      </td>
      <td className='px-3 py-2'>
        <span className='text-muted-foreground text-xs font-medium uppercase'>
          {SCRAPER_LABELS[job.scraper_id] ?? job.scraper_id}
        </span>
      </td>
      <td className='max-w-xs truncate px-3 py-2 font-mono text-xs'>
        {target}
      </td>
      <td className='px-3 py-2 text-right font-mono'>{job.items_found}</td>
      <td className='text-muted-foreground px-3 py-2 text-right text-xs'>
        {formatDuration(job.started_at, job.completed_at)}
      </td>
      <td className='text-muted-foreground px-3 py-2 text-xs'>
        {formatRelativeTime(job.created_at)}
      </td>
      <td className='max-w-xs truncate px-3 py-2 text-xs text-red-600 dark:text-red-400'>
        {job.error ?? ''}
      </td>
    </tr>
  );
}

function truncateUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname.slice(0, 40) + (u.pathname.length > 40 ? '...' : '');
  } catch {
    return url.slice(0, 40);
  }
}

'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { JobAttempt, JobSnapshot, WorkerJobDetail } from './types';
import { formatDurationMs, formatRelativeTime } from './types';

interface JobDetailDrawerProps {
  readonly jobId: string | null;
  readonly onClose: () => void;
}

const STATUS_STYLES: Record<string, string> = {
  queued:
    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  running:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  completed:
    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

const SCRAPER_LABELS: Record<string, string> = {
  'scrape:bricklink_metadata': 'BrickLink',
  'scrape:brickeconomy': 'BrickEconomy',
  'scrape:keepa': 'Keepa',
  'scrape:minifigures': 'Minifigures',
  'scrape:google_trends': 'Google Trends',
  'scrape:google_trends_theme': 'Google Trends (Theme)',
};

export function JobDetailDrawer({ jobId, onClose }: JobDetailDrawerProps) {
  const [detail, setDetail] = useState<WorkerJobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/scrape/jobs/${id}`);
      if (!res.ok) {
        setError(`Failed to load detail (${res.status})`);
        return;
      }
      const json = await res.json();
      if (json.success && json.data) {
        setDetail(json.data);
      } else if (json.success === false) {
        setError(json.error ?? 'Failed to load detail');
      } else {
        // Fallback: response is the data itself
        setDetail(json);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (jobId) {
      fetchDetail(jobId);
    } else {
      setDetail(null);
    }
  }, [jobId, fetchDetail]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  if (!jobId) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className='fixed inset-0 z-40 bg-black/30'
        onClick={onClose}
      />

      {/* Drawer */}
      <div className='bg-background fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l shadow-xl'>
        {/* Header */}
        <div className='border-border flex items-center justify-between border-b px-5 py-4'>
          <div className='min-w-0'>
            <h2 className='truncate text-lg font-semibold'>
              Job Detail
            </h2>
            {detail && (
              <p className='text-muted-foreground truncate text-sm'>
                {SCRAPER_LABELS[detail.scraper_id] ?? detail.scraper_id}
                {' -- '}
                {detail.url}
              </p>
            )}
          </div>
          <Button variant='ghost' size='sm' onClick={onClose} className='ml-2 shrink-0'>
            Close
          </Button>
        </div>

        {/* Content */}
        <div className='flex-1 overflow-y-auto px-5 py-4'>
          {loading && (
            <div className='text-muted-foreground py-12 text-center text-sm'>
              Loading...
            </div>
          )}

          {error && (
            <div className='py-12 text-center text-sm text-red-600'>
              {error}
            </div>
          )}

          {detail && !loading && (
            <div className='flex flex-col gap-6'>
              {/* Status overview */}
              <StatusSection detail={detail} />

              {/* Attempt history */}
              <AttemptsSection attempts={detail.attempts} />

              {/* Snapshots collected */}
              <SnapshotsSection snapshots={detail.snapshots} />

              {/* Error detail */}
              {detail.error && <ErrorSection error={detail.error} />}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function StatusSection({ detail }: { readonly detail: WorkerJobDetail }) {
  const label = SCRAPER_LABELS[detail.scraper_id] ?? detail.scraper_id;

  return (
    <div className='space-y-3'>
      <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
        Overview
      </h3>
      <div className='grid grid-cols-2 gap-3'>
        <InfoCell label='Status'>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[detail.status] ?? ''}`}
          >
            {detail.status}
          </span>
        </InfoCell>
        <InfoCell label='Type'>
          <span className='text-sm'>{label}</span>
        </InfoCell>
        <InfoCell label='Target'>
          <span className='font-mono text-sm'>{detail.url}</span>
        </InfoCell>
        <InfoCell label='Outcome'>
          <span className='text-sm'>{detail.outcome ?? '-'}</span>
        </InfoCell>
        <InfoCell label='Attempts'>
          <span className='text-sm'>
            {detail.attempt_count ?? 0} / {detail.max_attempts ?? 3}
          </span>
        </InfoCell>
        <InfoCell label='Duration'>
          <span className='text-sm'>
            {detail.duration_ms != null
              ? formatDurationMs(detail.duration_ms)
              : '-'}
          </span>
        </InfoCell>
        <InfoCell label='Reason'>
          <span className='text-sm'>{detail.reason ?? '-'}</span>
        </InfoCell>
        <InfoCell label='Source'>
          <span className='text-sm'>{detail.source ?? '-'}</span>
        </InfoCell>
        {detail.depends_on && (
          <InfoCell label='Depends on'>
            <span className='text-sm'>{detail.depends_on}</span>
          </InfoCell>
        )}
        {detail.locked_by && (
          <InfoCell label='Locked by'>
            <span className='font-mono text-sm'>{detail.locked_by}</span>
          </InfoCell>
        )}
        <InfoCell label='Created'>
          <span className='text-sm'>
            {formatRelativeTime(detail.created_at)}
          </span>
        </InfoCell>
        {detail.started_at && (
          <InfoCell label='Started'>
            <span className='text-sm'>
              {formatRelativeTime(detail.started_at)}
            </span>
          </InfoCell>
        )}
        {detail.completed_at && (
          <InfoCell label='Completed'>
            <span className='text-sm'>
              {formatRelativeTime(detail.completed_at)}
            </span>
          </InfoCell>
        )}
      </div>
    </div>
  );
}

function AttemptsSection({
  attempts,
}: {
  readonly attempts: readonly JobAttempt[];
}) {
  if (attempts.length === 0) {
    return (
      <div className='space-y-2'>
        <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
          Attempt History
        </h3>
        <p className='text-muted-foreground text-sm'>No attempts recorded yet.</p>
      </div>
    );
  }

  return (
    <div className='space-y-2'>
      <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
        Attempt History
      </h3>
      <div className='space-y-2'>
        {attempts.map((a, i) => (
          <AttemptRow key={i} attempt={a} />
        ))}
      </div>
    </div>
  );
}

function AttemptRow({ attempt }: { readonly attempt: JobAttempt }) {
  const isSuccess = !attempt.error_category && !attempt.error_message;
  const borderColor = isSuccess
    ? 'border-green-200 dark:border-green-800'
    : 'border-red-200 dark:border-red-800';
  const bgColor = isSuccess
    ? 'bg-green-50 dark:bg-green-950/20'
    : 'bg-red-50 dark:bg-red-950/20';

  return (
    <div className={`rounded-lg border ${borderColor} ${bgColor} px-3 py-2`}>
      <div className='flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <span className='text-xs font-medium'>
            Attempt #{attempt.attempt_number}
          </span>
          {isSuccess ? (
            <span className='text-xs text-green-600 dark:text-green-400'>
              Success
            </span>
          ) : (
            <span className='text-xs text-red-600 dark:text-red-400'>
              {attempt.error_category ?? 'Failed'}
            </span>
          )}
        </div>
        <div className='flex items-center gap-3 text-xs text-muted-foreground'>
          {attempt.duration_seconds != null && (
            <span>{formatDurationMs(attempt.duration_seconds * 1000)}</span>
          )}
          {attempt.created_at && (
            <span>{formatRelativeTime(attempt.created_at)}</span>
          )}
        </div>
      </div>
      {attempt.error_message && (
        <p className='mt-1 text-xs text-red-600 dark:text-red-400'>
          {attempt.error_message}
        </p>
      )}
    </div>
  );
}

function SnapshotsSection({
  snapshots,
}: {
  readonly snapshots: readonly JobSnapshot[];
}) {
  if (snapshots.length === 0) {
    return (
      <div className='space-y-2'>
        <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
          Data Collected
        </h3>
        <p className='text-muted-foreground text-sm'>
          No snapshots collected yet.
        </p>
      </div>
    );
  }

  return (
    <div className='space-y-2'>
      <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
        Data Collected
      </h3>
      <div className='space-y-2'>
        {snapshots.map((s, i) => (
          <div
            key={i}
            className='rounded-lg border border-border bg-muted/30 px-3 py-2'
          >
            <div className='flex items-center justify-between'>
              <span className='text-sm font-medium'>{s.source}</span>
              {s.scraped_at && (
                <span className='text-xs text-muted-foreground'>
                  {formatRelativeTime(s.scraped_at)}
                </span>
              )}
            </div>
            {s.summary && (
              <p className='mt-0.5 text-xs text-muted-foreground'>
                {s.summary}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ErrorSection({ error }: { readonly error: string }) {
  return (
    <div className='space-y-2'>
      <h3 className='text-sm font-semibold uppercase tracking-wider text-muted-foreground'>
        Error
      </h3>
      <div className='rounded-lg border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-950/20'>
        <p className='text-sm text-red-700 dark:text-red-300'>{error}</p>
      </div>
    </div>
  );
}

function InfoCell({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div>
      <div className='text-xs text-muted-foreground'>{label}</div>
      <div className='mt-0.5'>{children}</div>
    </div>
  );
}

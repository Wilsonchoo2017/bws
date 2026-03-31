'use client';

import { useCallback, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import type { ScraperConfig, ScrapeTarget, ScrapeItem } from './types';

type JobStatus = 'queued' | 'running' | 'completed' | 'failed';

interface JobState {
  jobId: string;
  status: JobStatus;
  items: ScrapeItem[];
  itemsFound: number;
  error?: string;
  progress?: string;
}

interface ScraperDashboardProps {
  scraper: ScraperConfig;
}

export function ScraperDashboard({ scraper }: ScraperDashboardProps) {
  const [jobs, setJobs] = useState<Record<string, JobState>>({});
  const [customUrl, setCustomUrl] = useState('');
  const pollRefs = useRef<Record<string, NodeJS.Timeout>>({});

  const pollJob = useCallback((targetId: string, jobId: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`/api/scrape/jobs/${jobId}`);
        const data = await res.json();

        setJobs((prev) => ({
          ...prev,
          [targetId]: {
            jobId,
            status: data.status,
            items: data.items || [],
            itemsFound: data.items_found || 0,
            error: data.error,
            progress: data.progress
          }
        }));

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollRefs.current[targetId]);
          delete pollRefs.current[targetId];
        }
      } catch {
        // Keep polling on network errors
      }
    };

    // Poll every 2 seconds
    poll();
    pollRefs.current[targetId] = setInterval(poll, 2000);
  }, []);

  async function runScrape(targetId: string, url: string) {
    // Clear previous poll if any
    if (pollRefs.current[targetId]) {
      clearInterval(pollRefs.current[targetId]);
    }

    setJobs((prev) => ({
      ...prev,
      [targetId]: {
        jobId: '',
        status: 'queued',
        items: [],
        itemsFound: 0
      }
    }));

    try {
      const res = await fetch('/api/scrape/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scraperId: scraper.id, url })
      });

      const data = await res.json();

      if (data.job_id) {
        setJobs((prev) => ({
          ...prev,
          [targetId]: {
            jobId: data.job_id,
            status: data.status || 'queued',
            items: [],
            itemsFound: 0
          }
        }));
        pollJob(targetId, data.job_id);
      } else {
        setJobs((prev) => ({
          ...prev,
          [targetId]: {
            jobId: '',
            status: 'failed',
            items: [],
            itemsFound: 0,
            error: data.error || 'Failed to start scrape'
          }
        }));
      }
    } catch (err) {
      setJobs((prev) => ({
        ...prev,
        [targetId]: {
          jobId: '',
          status: 'failed',
          items: [],
          itemsFound: 0,
          error: err instanceof Error ? err.message : 'Network error'
        }
      }));
    }
  }

  const isRunning = Object.values(jobs).some(
    (j) => j.status === 'queued' || j.status === 'running'
  );

  return (
    <div className='flex flex-col gap-6'>
      {/* Predefined targets */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Targets</h2>
        <div className='flex flex-col gap-3'>
          {scraper.targets.map((target) => (
            <TargetCard
              key={target.id}
              target={target}
              job={jobs[target.id]}
              disabled={isRunning}
              onRun={() => runScrape(target.id, target.url)}
            />
          ))}
        </div>
      </div>

      {/* Custom URL */}
      <div>
        <h2 className='mb-3 text-lg font-semibold'>Custom URL</h2>
        <div className='border-border rounded-lg border p-4'>
          <div className='flex gap-2'>
            <input
              type='url'
              placeholder='https://shopee.com.my/...'
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              className='border-border bg-background flex-1 rounded-md border px-3 py-2 text-sm'
            />
            <Button
              onClick={() => runScrape('custom', customUrl.trim())}
              disabled={isRunning || !customUrl.trim()}
              size='sm'
            >
              Scrape
            </Button>
          </div>

          {jobs['custom'] && <JobResults job={jobs['custom']} />}
        </div>
      </div>
    </div>
  );
}

function TargetCard({
  target,
  job,
  disabled,
  onRun
}: {
  target: ScrapeTarget;
  job?: JobState;
  disabled: boolean;
  onRun: () => void;
}) {
  return (
    <div className='border-border rounded-lg border p-4'>
      <div className='flex items-start justify-between gap-4'>
        <div className='min-w-0 flex-1'>
          <h3 className='font-medium'>{target.label}</h3>
          <p className='text-muted-foreground mt-0.5 text-sm'>
            {target.description}
          </p>
          <code className='text-muted-foreground mt-1 block truncate text-xs'>
            {target.url}
          </code>
        </div>
        <Button onClick={onRun} disabled={disabled} size='sm'>
          {job?.status === 'queued'
            ? 'Queued...'
            : job?.status === 'running'
              ? 'Running...'
              : 'Run'}
        </Button>
      </div>

      {job && <JobResults job={job} />}
    </div>
  );
}

function JobResults({ job }: { job: JobState }) {
  return (
    <div className='mt-3'>
      {/* Status indicator */}
      <div className='mb-2 flex items-center gap-2'>
        <StatusBadge status={job.status} />
        {(job.status === 'queued' || job.status === 'running') && (
          <span className='text-muted-foreground animate-pulse text-sm'>
            {job.status === 'queued'
              ? 'Waiting for worker...'
              : job.progress || 'Scraping in progress...'}
          </span>
        )}
        {job.status === 'completed' && (
          <span className='text-muted-foreground text-sm'>
            {job.itemsFound} items found
          </span>
        )}
      </div>

      {job.error && (
        <div className='rounded bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300'>
          {job.error}
        </div>
      )}

      {job.items.length > 0 && <ResultsTable items={job.items} />}
    </div>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  const styles: Record<JobStatus, string> = {
    queued: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    completed:
      'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
  };

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {status}
    </span>
  );
}

function ResultsTable({ items }: { items: ScrapeItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className='max-h-96 overflow-auto rounded border'>
      <table className='w-full text-sm'>
        <thead className='bg-muted/50 sticky top-0'>
          <tr>
            <th className='px-3 py-2 text-left font-medium'>Image</th>
            <th className='px-3 py-2 text-left font-medium'>Title</th>
            <th className='px-3 py-2 text-right font-medium'>Price</th>
            <th className='px-3 py-2 text-right font-medium'>Sold</th>
            <th className='px-3 py-2 text-right font-medium'>Rating</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={i} className='border-border border-t'>
              <td className='px-3 py-2'>
                {item.image_url && (
                  <img
                    src={item.image_url}
                    alt=''
                    className='h-10 w-10 rounded object-cover'
                  />
                )}
              </td>
              <td className='max-w-xs truncate px-3 py-2'>
                {item.product_url ? (
                  <a
                    href={item.product_url}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-primary hover:underline'
                  >
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </td>
              <td className='whitespace-nowrap px-3 py-2 text-right font-mono'>
                {item.price_display}
              </td>
              <td className='text-muted-foreground whitespace-nowrap px-3 py-2 text-right'>
                {item.sold_count || '-'}
              </td>
              <td className='text-muted-foreground whitespace-nowrap px-3 py-2 text-right'>
                {item.rating || '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

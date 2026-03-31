'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

interface ImageStats {
  by_type: Record<
    string,
    { pending: number; downloaded: number; failed: number; total: number }
  >;
  totals: {
    pending: number;
    downloaded: number;
    failed: number;
    total: number;
    total_bytes: number;
  };
}

export function ImageDownloadCard() {
  const [stats, setStats] = useState<ImageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/images/stats');
      const json = await res.json();
      if (json.success) {
        setStats(json.data);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10_000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  const triggerDownload = useCallback(async () => {
    setDownloading(true);
    try {
      await fetch('/api/images/download', { method: 'POST' });
      // Refresh stats after triggering
      setTimeout(fetchStats, 2000);
    } catch {
      // silent
    } finally {
      setDownloading(false);
    }
  }, [fetchStats]);

  if (loading) {
    return (
      <div className='border-border rounded-lg border px-4 py-3'>
        <div className='text-muted-foreground text-sm'>
          Loading image stats...
        </div>
      </div>
    );
  }

  const totals = stats?.totals ?? {
    pending: 0,
    downloaded: 0,
    failed: 0,
    total: 0,
    total_bytes: 0,
  };
  const pct =
    totals.total > 0
      ? Math.round((totals.downloaded / totals.total) * 100)
      : 0;
  const sizeMb = (totals.total_bytes / (1024 * 1024)).toFixed(1);

  return (
    <div className='border-border rounded-lg border px-4 py-4'>
      <div className='flex items-center justify-between'>
        <div>
          <h3 className='text-sm font-medium'>Image Assets</h3>
          <p className='text-muted-foreground text-xs'>
            BrickLink images stored locally
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={triggerDownload}
          disabled={downloading || totals.pending === 0}
        >
          {downloading ? 'Starting...' : 'Download'}
        </Button>
      </div>

      {/* Progress bar */}
      <div className='mt-3'>
        <div className='bg-muted h-2 overflow-hidden rounded-full'>
          <div
            className='h-full rounded-full bg-green-500 transition-all'
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className='text-muted-foreground mt-1 flex justify-between text-xs'>
          <span>
            {totals.downloaded}/{totals.total} downloaded ({pct}%)
          </span>
          <span>{sizeMb} MB</span>
        </div>
      </div>

      {/* Breakdown by type */}
      {stats?.by_type && Object.keys(stats.by_type).length > 0 && (
        <div className='mt-3 flex gap-4 text-xs'>
          {Object.entries(stats.by_type).map(([type, counts]) => (
            <div key={type} className='flex items-center gap-1.5'>
              <span className='text-muted-foreground capitalize'>{type}s:</span>
              <span className='font-mono'>
                {counts.downloaded}/{counts.total}
              </span>
              {counts.pending > 0 && (
                <span className='text-yellow-600 dark:text-yellow-400'>
                  ({counts.pending} pending)
                </span>
              )}
              {counts.failed > 0 && (
                <span className='text-red-600 dark:text-red-400'>
                  ({counts.failed} failed)
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

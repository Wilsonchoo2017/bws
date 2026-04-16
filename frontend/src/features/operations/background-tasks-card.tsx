'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

type TaskState = 'running' | 'crashed' | 'cancelled' | 'finished';

interface BackgroundTask {
  readonly name: string;
  readonly label: string;
  readonly state: TaskState;
  readonly error: string | null;
}

const STATUS_STYLES: Record<TaskState, string> = {
  running:
    'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  crashed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  cancelled:
    'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  finished:
    'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
};

const POLL_INTERVAL_MS = 10_000;

export function BackgroundTasksCard() {
  const [tasks, setTasks] = useState<readonly BackgroundTask[]>([]);
  const [restarting, setRestarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/operations/tasks');
      if (!res.ok) return;
      const json = await res.json();
      if (json.success) {
        setTasks(json.data);
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch tasks');
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const id = setInterval(fetchTasks, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchTasks]);

  const restart = useCallback(
    async (name: string) => {
      setRestarting(name);
      try {
        const res = await fetch(
          `/api/operations/tasks/${encodeURIComponent(name)}/restart`,
          { method: 'POST' }
        );
        if (!res.ok) {
          const json = await res.json().catch(() => null);
          setError(json?.error ?? `Restart failed (${res.status})`);
        } else {
          setError(null);
        }
        await fetchTasks();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Restart failed');
      } finally {
        setRestarting(null);
      }
    },
    [fetchTasks]
  );

  const stopped = tasks.filter(
    (t) => t.state === 'crashed' || t.state === 'cancelled'
  );

  if (stopped.length === 0) return null;

  return (
    <div className='rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-800 dark:bg-red-950/20'>
      <div className='mb-2 flex items-center justify-between'>
        <span className='text-sm font-medium text-red-800 dark:text-red-200'>
          {stopped.length} background task{stopped.length > 1 ? 's' : ''} stopped
        </span>
        <Button variant='outline' size='sm' onClick={fetchTasks} className='h-6 text-xs'>
          Refresh
        </Button>
      </div>
      {error && (
        <div className='mb-2 text-xs text-red-600 dark:text-red-400'>{error}</div>
      )}
      <div className='flex flex-col gap-2'>
        {stopped.map((task) => (
          <div
            key={task.name}
            className='flex items-center justify-between gap-3 rounded border border-red-100 bg-white px-3 py-2 dark:border-red-900 dark:bg-red-950/30'
          >
            <div className='min-w-0 flex-1'>
              <div className='flex items-center gap-2'>
                <span className='text-sm font-medium'>{task.label}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[task.state]}`}
                >
                  {task.state}
                </span>
              </div>
              {task.error && (
                <div className='mt-0.5 truncate text-xs text-red-600 dark:text-red-400' title={task.error}>
                  {task.error}
                </div>
              )}
            </div>
            <Button
              variant='default'
              size='sm'
              className='h-7 shrink-0 text-xs'
              disabled={restarting === task.name}
              onClick={() => restart(task.name)}
            >
              {restarting === task.name ? 'Restarting...' : 'Restart'}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

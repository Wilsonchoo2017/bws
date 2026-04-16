'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';

interface SchedulerRow {
  readonly name: string;
  readonly label: string;
  readonly description: string;
  readonly category: string;
  readonly interval_seconds: number;
  readonly enabled: boolean;
  readonly last_run_at: string | null;
  readonly last_finished_at: string | null;
  readonly last_status: string | null;
  readonly last_items_queued: number;
  readonly last_error: string | null;
  readonly last_ok_at: string | null;
  readonly errors_24h: number;
}

interface DuplicateRow {
  readonly set_number: string;
  readonly task_type: string;
  readonly enqueue_count: number;
  readonly completed: number;
  readonly failed: number;
  readonly in_flight: number;
  readonly last_created_at: string | null;
  readonly last_error: string | null;
}

type StatusFilter = 'all' | 'active' | 'disabled' | 'errors';

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function formatAgo(iso: string | null): string {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'never';
  const delta = Math.max(0, (Date.now() - then) / 1000);
  if (delta < 60) return `${Math.round(delta)}s ago`;
  if (delta < 3600) return `${Math.round(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.round(delta / 3600)}h ago`;
  return `${Math.round(delta / 86400)}d ago`;
}

function statusTone(row: SchedulerRow): {
  readonly label: string;
  readonly className: string;
} {
  if (!row.enabled) {
    return {
      label: 'Disabled',
      className:
        'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    };
  }
  if (row.errors_24h > 0 || row.last_status === 'error') {
    return {
      label: `Error${row.errors_24h > 1 ? ` x${row.errors_24h}` : ''}`,
      className:
        'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300',
    };
  }
  if (row.last_status === 'running') {
    return {
      label: 'Running',
      className:
        'bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300',
    };
  }
  if (row.last_status === 'ok') {
    return {
      label: 'Healthy',
      className:
        'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300',
    };
  }
  return {
    label: 'Idle',
    className:
      'bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-400',
  };
}

export function SchedulersPanel() {
  const [rows, setRows] = useState<readonly SchedulerRow[]>([]);
  const [duplicates, setDuplicates] = useState<readonly DuplicateRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [dupDays, setDupDays] = useState(3);
  const [toggling, setToggling] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [schedRes, dupRes] = await Promise.all([
        fetch('/api/operations/schedulers'),
        fetch(`/api/operations/schedulers/duplicates?days=${dupDays}`),
      ]);
      const schedJson = await schedRes.json();
      const dupJson = await dupRes.json();
      if (!schedJson.success) {
        setError(schedJson.error ?? 'Failed to load schedulers');
        return;
      }
      setRows(schedJson.data);
      setDuplicates(dupJson.success ? dupJson.data : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, [dupDays]);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 10000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const toggle = useCallback(
    async (name: string, enabled: boolean) => {
      setToggling(name);
      try {
        const res = await fetch(
          `/api/operations/schedulers/${name}/toggle?enabled=${enabled}`,
          { method: 'POST' }
        );
        const json = await res.json();
        if (json.success) {
          await fetchAll();
        } else {
          setError(json.detail ?? 'Toggle failed');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Network error');
      } finally {
        setToggling(null);
      }
    },
    [fetchAll]
  );

  const filtered = useMemo(() => {
    switch (filter) {
      case 'active':
        return rows.filter((r) => r.enabled);
      case 'disabled':
        return rows.filter((r) => !r.enabled);
      case 'errors':
        return rows.filter(
          (r) => r.errors_24h > 0 || r.last_status === 'error'
        );
      default:
        return rows;
    }
  }, [rows, filter]);

  const counts = useMemo(
    () => ({
      total: rows.length,
      active: rows.filter((r) => r.enabled).length,
      disabled: rows.filter((r) => !r.enabled).length,
      errors: rows.filter((r) => r.errors_24h > 0 || r.last_status === 'error')
        .length,
    }),
    [rows]
  );

  if (loading && rows.length === 0) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-muted-foreground'>Loading schedulers...</p>
      </div>
    );
  }

  return (
    <div className='flex flex-col gap-6'>
      {error && (
        <div className='border-destructive/40 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm'>
          {error}
        </div>
      )}

      {/* Filter bar */}
      <div className='flex flex-wrap items-center gap-2'>
        <FilterChip
          active={filter === 'all'}
          onClick={() => setFilter('all')}
          label={`All (${counts.total})`}
        />
        <FilterChip
          active={filter === 'active'}
          onClick={() => setFilter('active')}
          label={`Active (${counts.active})`}
        />
        <FilterChip
          active={filter === 'disabled'}
          onClick={() => setFilter('disabled')}
          label={`Disabled (${counts.disabled})`}
        />
        <FilterChip
          active={filter === 'errors'}
          onClick={() => setFilter('errors')}
          label={`Errors (${counts.errors})`}
        />
        <div className='ml-auto'>
          <Button variant='outline' size='sm' onClick={fetchAll}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Scheduler table */}
      <div className='border-border overflow-x-auto rounded-lg border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/40 text-muted-foreground text-xs uppercase tracking-wider'>
            <tr>
              <th className='px-3 py-2 text-left font-medium'>Scheduler</th>
              <th className='px-3 py-2 text-left font-medium'>Status</th>
              <th className='px-3 py-2 text-left font-medium'>Interval</th>
              <th className='px-3 py-2 text-left font-medium'>Last run</th>
              <th className='px-3 py-2 text-right font-medium'>Queued</th>
              <th className='px-3 py-2 text-right font-medium'>Errors 24h</th>
              <th className='px-3 py-2 text-right font-medium'>Toggle</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => {
              const tone = statusTone(row);
              return (
                <tr
                  key={row.name}
                  className='border-border hover:bg-muted/20 border-t'
                >
                  <td className='px-3 py-2'>
                    <div className='font-medium'>{row.label}</div>
                    <div className='text-muted-foreground text-xs'>
                      {row.description}
                    </div>
                    {row.last_error && (
                      <div
                        className='mt-1 truncate text-xs text-red-600 dark:text-red-400'
                        title={row.last_error}
                      >
                        {row.last_error}
                      </div>
                    )}
                  </td>
                  <td className='px-3 py-2'>
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tone.className}`}
                    >
                      {tone.label}
                    </span>
                    <div className='text-muted-foreground mt-1 text-xs'>
                      {row.category}
                    </div>
                  </td>
                  <td className='text-muted-foreground px-3 py-2 font-mono text-xs'>
                    {formatInterval(row.interval_seconds)}
                  </td>
                  <td className='px-3 py-2 text-xs'>
                    <div>{formatAgo(row.last_run_at)}</div>
                    <div className='text-muted-foreground'>
                      last ok {formatAgo(row.last_ok_at)}
                    </div>
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs'>
                    {row.last_items_queued}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs'>
                    {row.errors_24h > 0 ? (
                      <span className='text-red-600 dark:text-red-400'>
                        {row.errors_24h}
                      </span>
                    ) : (
                      <span className='text-muted-foreground'>0</span>
                    )}
                  </td>
                  <td className='px-3 py-2 text-right'>
                    <ToggleSwitch
                      enabled={row.enabled}
                      disabled={toggling === row.name}
                      onChange={(next) => toggle(row.name, next)}
                    />
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className='text-muted-foreground px-3 py-6 text-center text-sm'
                >
                  No schedulers match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Duplicates section */}
      <div className='border-border rounded-lg border'>
        <div className='border-border flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2'>
          <div>
            <div className='text-sm font-medium'>
              Repeated scrape enqueues
            </div>
            <div className='text-muted-foreground text-xs'>
              Sets enqueued more than once in the window. Dedup should prevent
              this — if you see counts here it usually means a set is failing
              and re-entering the 7d retry window, or a tier rotation is
              double-firing.
            </div>
          </div>
          <div className='flex items-center gap-2 text-xs'>
            <span className='text-muted-foreground'>Window:</span>
            {[1, 3, 7, 14].map((d) => (
              <button
                key={d}
                type='button'
                onClick={() => setDupDays(d)}
                className={`rounded-md px-2 py-1 ${
                  dupDays === d
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        <div className='max-h-96 overflow-y-auto'>
          <table className='w-full text-sm'>
            <thead className='bg-muted/20 text-muted-foreground sticky top-0 text-xs uppercase tracking-wider'>
              <tr>
                <th className='px-3 py-2 text-left font-medium'>Set</th>
                <th className='px-3 py-2 text-left font-medium'>Task type</th>
                <th className='px-3 py-2 text-right font-medium'>Count</th>
                <th className='px-3 py-2 text-right font-medium'>OK</th>
                <th className='px-3 py-2 text-right font-medium'>Failed</th>
                <th className='px-3 py-2 text-right font-medium'>In flight</th>
                <th className='px-3 py-2 text-left font-medium'>Last</th>
              </tr>
            </thead>
            <tbody>
              {duplicates.map((d) => (
                <tr
                  key={`${d.set_number}-${d.task_type}`}
                  className='border-border border-t'
                >
                  <td className='px-3 py-2 font-mono text-xs'>
                    {d.set_number}
                  </td>
                  <td className='px-3 py-2 font-mono text-xs'>
                    {d.task_type}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs font-semibold'>
                    {d.enqueue_count}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs text-green-600 dark:text-green-400'>
                    {d.completed}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs text-red-600 dark:text-red-400'>
                    {d.failed}
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs'>
                    {d.in_flight}
                  </td>
                  <td
                    className='text-muted-foreground px-3 py-2 text-xs'
                    title={d.last_error ?? undefined}
                  >
                    {formatAgo(d.last_created_at)}
                    {d.last_error && (
                      <div className='max-w-[240px] truncate text-red-600 dark:text-red-400'>
                        {d.last_error}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {duplicates.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className='text-muted-foreground px-3 py-6 text-center text-sm'
                  >
                    No duplicated enqueues in the last {dupDays}d.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
}: {
  readonly active: boolean;
  readonly onClick: () => void;
  readonly label: string;
}) {
  return (
    <button
      type='button'
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground hover:text-foreground'
      }`}
    >
      {label}
    </button>
  );
}

function ToggleSwitch({
  enabled,
  disabled,
  onChange,
}: {
  readonly enabled: boolean;
  readonly disabled: boolean;
  readonly onChange: (next: boolean) => void;
}) {
  return (
    <button
      type='button'
      role='switch'
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        enabled ? 'bg-green-500' : 'bg-slate-300 dark:bg-slate-700'
      } ${disabled ? 'opacity-50' : ''}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          enabled ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  );
}

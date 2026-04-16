'use client';

import { useEffect, useRef, useState } from 'react';

type Freshness = 'fresh' | 'ok' | 'stale' | 'loading';

interface MlStatus {
  freshness: Freshness;
  model: {
    active_experiment: string;
    version: string;
    trained_at: string | null;
    trained_age_hours: number | null;
    artifact_mtime: number | null;
  };
  snapshot: {
    latest_date: string | null;
    is_today: boolean;
    count: number;
    model_version: string | null;
  };
  cache: {
    predictions_in_memory: number;
    models_loaded: boolean;
  };
  metrics: {
    classifier_auc?: number;
    classifier_recall?: number;
    great_buy_auc?: number;
    great_buy_recall?: number;
    n_train?: number;
  };
}

const FAST_INTERVAL = 3_000;
const SLOW_INTERVAL = 30_000;

const FRESHNESS_STYLE: Record<
  Freshness,
  { dot: string; pill: string; label: string }
> = {
  fresh: {
    dot: 'bg-emerald-500',
    pill: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 ring-emerald-500/20',
    label: 'Fresh',
  },
  ok: {
    dot: 'bg-amber-500',
    pill: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-amber-500/20',
    label: 'OK',
  },
  stale: {
    dot: 'bg-red-500',
    pill: 'bg-red-500/10 text-red-700 dark:text-red-300 ring-red-500/20',
    label: 'Stale',
  },
  loading: {
    dot: 'bg-slate-400 animate-pulse',
    pill: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 ring-slate-500/20',
    label: 'Loading',
  },
};

function formatAge(hours: number | null): string {
  if (hours == null) return 'unknown';
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 48) return `${Math.round(hours)}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatTrainedAt(iso: string | null): string {
  if (!iso) return 'unknown';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function MlStatusBadge() {
  const [status, setStatus] = useState<MlStatus | null>(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [reloading, setReloading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const res = await fetch('/api/ml/status');
        if (!res.ok) throw new Error('fetch failed');
        const data: MlStatus = await res.json();
        if (!mounted) return;
        setStatus(data);
        setError(false);

        const isFresh = data.freshness === 'fresh';
        const nextInterval = isFresh ? SLOW_INTERVAL : FAST_INTERVAL;
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = setInterval(poll, nextInterval);
      } catch {
        if (mounted) setError(true);
      }
    }

    poll();
    intervalRef.current = setInterval(poll, FAST_INTERVAL);
    return () => {
      mounted = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Close popover on outside click
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  async function handleReload() {
    setReloading(true);
    try {
      await fetch('/api/ml/growth/reload', { method: 'POST' });
    } finally {
      setReloading(false);
    }
  }

  async function handleRetrain() {
    if (!confirm('Retrain models? This takes ~1-2 minutes.')) return;
    setRetraining(true);
    try {
      await fetch('/api/ml/growth/retrain', { method: 'POST' });
    } finally {
      setRetraining(false);
    }
  }

  if (error) {
    return (
      <span className='text-destructive bg-destructive/10 rounded px-2 py-0.5 text-xs font-medium'>
        API offline
      </span>
    );
  }

  if (!status) {
    return (
      <span className='text-muted-foreground bg-muted rounded px-2 py-0.5 text-xs font-medium'>
        ...
      </span>
    );
  }

  const style = FRESHNESS_STYLE[status.freshness];
  const ageLabel = formatAge(status.model.trained_age_hours);

  return (
    <div ref={rootRef} className='relative'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors ${style.pill}`}
        title='Click for model details'
      >
        <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
        <span>Model: {style.label.toLowerCase()}</span>
        <span className='text-muted-foreground/80'>·</span>
        <span>{ageLabel}</span>
      </button>

      {open && (
        <div className='bg-popover text-popover-foreground ring-border absolute right-0 z-50 mt-2 w-80 rounded-lg p-4 text-xs shadow-lg ring-1'>
          <div className='mb-3 flex items-center justify-between'>
            <div className='text-sm font-semibold'>Model lineage</div>
            <span className={`h-2 w-2 rounded-full ${style.dot}`} />
          </div>

          <dl className='space-y-2'>
            <Row label='Experiment'>
              <code className='rounded bg-slate-500/10 px-1.5 py-0.5 font-mono text-[11px]'>
                {status.model.active_experiment}
              </code>
            </Row>
            <Row label='Version'>
              <code className='rounded bg-slate-500/10 px-1.5 py-0.5 font-mono text-[11px]'>
                {status.model.version}
              </code>
            </Row>
            <Row label='Trained'>
              <div>
                <div>{formatTrainedAt(status.model.trained_at)}</div>
                <div className='text-muted-foreground'>{ageLabel}</div>
              </div>
            </Row>
            {status.metrics.classifier_auc != null && (
              <Row label='Classifier'>
                <div>
                  AUC {status.metrics.classifier_auc}
                  {status.metrics.classifier_recall != null && (
                    <span className='text-muted-foreground'>
                      {' '}
                      · recall {status.metrics.classifier_recall}
                    </span>
                  )}
                </div>
              </Row>
            )}
            {status.metrics.great_buy_auc != null && (
              <Row label='Great-buy'>
                <div>
                  AUC {status.metrics.great_buy_auc}
                  {status.metrics.great_buy_recall != null && (
                    <span className='text-muted-foreground'>
                      {' '}
                      · recall {status.metrics.great_buy_recall}
                    </span>
                  )}
                </div>
              </Row>
            )}
            {status.metrics.n_train != null && (
              <Row label='Train set'>{status.metrics.n_train} rows</Row>
            )}
          </dl>

          <div className='border-border my-3 border-t' />

          <dl className='space-y-2'>
            <Row label='Snapshot'>
              {status.snapshot.latest_date ? (
                <div>
                  <div>
                    {status.snapshot.latest_date}{' '}
                    {status.snapshot.is_today && (
                      <span className='text-emerald-600 dark:text-emerald-400'>
                        (today)
                      </span>
                    )}
                  </div>
                  <div className='text-muted-foreground'>
                    {status.snapshot.count.toLocaleString()} sets persisted
                  </div>
                </div>
              ) : (
                <span className='text-muted-foreground'>none yet</span>
              )}
            </Row>
            <Row label='In memory'>
              {status.cache.predictions_in_memory.toLocaleString()} predictions
            </Row>
          </dl>

          <div className='mt-4 flex gap-2'>
            <button
              type='button'
              disabled={reloading || retraining}
              onClick={handleReload}
              className='border-border hover:bg-muted flex-1 rounded border px-2 py-1 text-xs disabled:opacity-50'
            >
              {reloading ? 'Reloading...' : 'Reload'}
            </button>
            <button
              type='button'
              disabled={reloading || retraining}
              onClick={handleRetrain}
              className='border-border hover:bg-muted flex-1 rounded border px-2 py-1 text-xs disabled:opacity-50'
            >
              {retraining ? 'Retraining...' : 'Retrain'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className='flex items-start justify-between gap-3'>
      <dt className='text-muted-foreground'>{label}</dt>
      <dd className='text-right'>{children}</dd>
    </div>
  );
}

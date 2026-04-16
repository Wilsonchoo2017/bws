'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { formatCountdown, useShopeeClearance } from './use-shopee-clearance';

interface CaptchaEvent {
  id: number;
  job_id: string | null;
  source_url: string;
  snapshot_dir: string;
  detection_reason: string;
  detection_signals: Record<string, unknown> | null;
  detected_at: string;
}

interface CaptchaEventsResponse {
  events: CaptchaEvent[];
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(iso).toLocaleString();
}

export function ShopeeCaptchaPanel() {
  const { clearance, solveStatus, solving, countdown, handleSolve } =
    useShopeeClearance({ pollIntervalMs: 10_000 });

  const [events, setEvents] = useState<CaptchaEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch('/api/scrape/shopee/captcha-events?limit=3');
      const json: CaptchaEventsResponse & { error?: string } = await res.json();
      if (!res.ok) {
        setError(json.error ?? 'Failed to load captcha events');
        return;
      }
      setEvents(json.events);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    pollRef.current = setInterval(fetchEvents, 10_000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchEvents]);

  if (loading) {
    return (
      <div className='rounded-md border border-border p-4 text-sm text-muted-foreground'>
        Loading captcha status...
      </div>
    );
  }

  const isValid = clearance?.valid ?? false;

  return (
    <div className='flex flex-col gap-3'>
      {/* Clearance status banner */}
      {isValid ? (
        <div className='rounded-md border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-700 dark:bg-emerald-950/20'>
          <div className='flex items-center justify-between'>
            <div>
              <h3 className='text-sm font-semibold text-emerald-900 dark:text-emerald-200'>
                Clearance active
              </h3>
              <p className='text-xs text-emerald-800 dark:text-emerald-300'>
                Shopee jobs can run. Expires in {formatCountdown(countdown)}
              </p>
            </div>
            <button
              onClick={handleSolve}
              disabled={solving}
              className='rounded border border-emerald-300 px-3 py-1 text-xs text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-600 dark:text-emerald-300 dark:hover:bg-emerald-900'
            >
              Renew
            </button>
          </div>
        </div>
      ) : (
        <div className='rounded-md border border-red-300 bg-red-50 p-4 dark:border-red-700 dark:bg-red-950/20'>
          <div className='flex items-center justify-between'>
            <div>
              <h3 className='text-sm font-semibold text-red-900 dark:text-red-200'>
                No captcha clearance
              </h3>
              <p className='text-xs text-red-800 dark:text-red-300'>
                All Shopee jobs are blocked until you solve a captcha.
              </p>
            </div>
            <button
              onClick={handleSolve}
              disabled={solving}
              className='rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50'
            >
              Solve Captcha
            </button>
          </div>
        </div>
      )}

      {/* Solve progress */}
      {solving && solveStatus && (
        <div className='rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-950/20'>
          <div className='flex items-center gap-2'>
            <div className='h-2 w-2 animate-pulse rounded-full bg-amber-500' />
            <p className='text-sm text-amber-800 dark:text-amber-200'>
              {solveStatus.status === 'launching' && 'Launching browser...'}
              {solveStatus.status === 'waiting_for_user' &&
                'Solve the captcha in the browser window'}
              {solveStatus.status === 'verifying' && 'Verifying...'}
            </p>
          </div>
        </div>
      )}

      {/* Solve error */}
      {!solving && solveStatus?.status === 'failed' && (
        <div className='rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950/20 dark:text-red-300'>
          Solve failed: {solveStatus.error?.slice(0, 200)}
        </div>
      )}

      {error && (
        <div className='rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950/20 dark:text-red-300'>
          {error}
        </div>
      )}

      {/* Recent captcha events */}
      {events.length > 0 && (
        <div className='flex flex-col gap-3'>
          <h4 className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
            Recent Captchas ({events.length})
          </h4>
          {events.map((ev) => (
            <CaptchaEventRow key={ev.id} event={ev} />
          ))}
        </div>
      )}
    </div>
  );
}

interface EventRowProps {
  readonly event: CaptchaEvent;
}

function CaptchaEventRow({ event }: EventRowProps) {
  const [imgError, setImgError] = useState(false);
  const thumbSrc = `/api/scrape/shopee/captcha-events/${event.id}/snapshot/screenshot.png`;

  return (
    <div className='flex gap-3 rounded-md border border-border bg-card p-3'>
      {!imgError && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={thumbSrc}
          alt={`Snapshot for event ${event.id}`}
          className='h-20 w-32 flex-shrink-0 rounded border border-border object-cover'
          onError={() => setImgError(true)}
        />
      )}
      <div className='flex min-w-0 flex-1 flex-col gap-1'>
        <div className='flex items-center gap-2'>
          <span className='text-xs text-muted-foreground'>
            Event #{event.id} · {formatRelative(event.detected_at)}
          </span>
        </div>
        <p className='truncate text-sm font-medium' title={event.source_url}>
          {event.source_url}
        </p>
        <p className='text-xs text-muted-foreground'>
          Detection: {event.detection_reason}
          {event.job_id ? ` · Job: ${event.job_id}` : ''}
        </p>
      </div>
      <div className='flex flex-col items-end justify-between gap-2'>
        <a
          href={`/api/scrape/shopee/captcha-events/${event.id}/snapshot/page.html`}
          target='_blank'
          rel='noopener noreferrer'
          className='text-[10px] text-muted-foreground underline hover:text-foreground'
        >
          view HTML
        </a>
      </div>
    </div>
  );
}

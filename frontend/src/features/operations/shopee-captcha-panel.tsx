'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

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

const CAPTCHA_GATE_HOURS = 2;
const GATE_DURATION_MS = CAPTCHA_GATE_HOURS * 3_600_000;

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(iso).toLocaleString();
}

function formatCountdown(ms: number): string {
  if (ms <= 0) return '0s';
  const totalSeconds = Math.ceil(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function ShopeeCaptchaPanel() {
  const [events, setEvents] = useState<CaptchaEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch('/api/scrape/shopee/captcha-events?limit=5');
      const json: CaptchaEventsResponse & { error?: string } = await res.json();
      if (!res.ok) {
        setError(json.error ?? 'Failed to load captcha events');
        return;
      }
      setEvents(json.events);
      setError(null);

      // Set countdown from the most recent event
      if (json.events.length > 0) {
        const lastEvent = json.events[0];
        const detectedTime = new Date(lastEvent.detected_at).getTime();
        const now = Date.now();
        const elapsedMs = now - detectedTime;
        const remainingMs = Math.max(0, GATE_DURATION_MS - elapsedMs);
        setCountdown(remainingMs);
      } else {
        setCountdown(0);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    pollRef.current = setInterval(fetchEvents, 10_000); // Poll every 10 seconds
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchEvents]);

  // Countdown tick
  useEffect(() => {
    if (countdown <= 0) return;
    countdownRef.current = setTimeout(() => setCountdown((c) => Math.max(0, c - 1000)), 1000);
    return () => {
      if (countdownRef.current) clearTimeout(countdownRef.current);
    };
  }, [countdown]);

  if (loading) {
    return (
      <div className='rounded-md border border-border p-4 text-sm text-muted-foreground'>
        Loading captcha events...
      </div>
    );
  }

  const lastEvent = events.length > 0 ? events[0] : null;
  const isBlocked = countdown > 0;

  return (
    <div className='flex flex-col gap-3'>
      {/* Status banner */}
      {isBlocked && lastEvent ? (
        <div className='rounded-md border border-orange-300 bg-orange-50 p-4 dark:border-orange-700 dark:bg-orange-950/20'>
          <div>
            <h3 className='text-sm font-semibold text-orange-900 dark:text-orange-200'>
              Captcha detected – jobs blocked
            </h3>
            <p className='text-xs text-orange-800 dark:text-orange-300'>
              Jobs will resume in {formatCountdown(countdown)}
            </p>
          </div>
        </div>
      ) : (
        <div className='rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground'>
          No recent Shopee captcha events.
        </div>
      )}

      {error && (
        <div className='rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950/20 dark:text-red-300'>
          {error}
        </div>
      )}

      {/* Recent events */}
      {events.length > 0 && (
        <div className='flex flex-col gap-3'>
          <h4 className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
            Recent Captchas ({events.length})
          </h4>
          {events.slice(0, 3).map((ev) => (
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
  const thumbSrc = `/api/scrape/shopee/captcha-events/${event.id}/snapshot/screenshot.png`;

  return (
    <div className='flex gap-3 rounded-md border border-border bg-card p-3'>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={thumbSrc}
        alt={`Snapshot for event ${event.id}`}
        className='h-20 w-32 flex-shrink-0 rounded border border-border object-cover'
        onError={(e) => {
          (e.target as HTMLImageElement).style.visibility = 'hidden';
        }}
      />
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

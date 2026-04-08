'use client';

import { useEffect, useRef, useState } from 'react';

interface MlHealth {
  status: 'ready' | 'not_loaded' | 'no_predictions';
  models_loaded: boolean;
  predictions: number;
  stage?: 'idle' | 'loading_models' | 'scoring' | 'ready' | 'failed';
}

const STAGE_LABELS: Record<string, string> = {
  idle: 'Waiting to start',
  loading_models: 'Loading models',
  scoring: 'Computing predictions',
  ready: 'Ready',
  failed: 'Warmup failed',
};

const FAST_INTERVAL = 3_000;
const SLOW_INTERVAL = 30_000;

export function MlStatusBadge() {
  const [health, setHealth] = useState<MlHealth | null>(null);
  const [error, setError] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const res = await fetch('/api/ml/health');
        if (!res.ok) throw new Error('fetch failed');
        const data: MlHealth = await res.json();
        if (mounted) {
          setHealth(data);
          setError(false);

          // Switch to slow polling once ready
          const isReady = data.status === 'ready';
          const nextInterval = isReady ? SLOW_INTERVAL : FAST_INTERVAL;
          if (intervalRef.current) clearInterval(intervalRef.current);
          intervalRef.current = setInterval(poll, nextInterval);
        }
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

  if (error) {
    return (
      <span className="text-destructive bg-destructive/10 rounded px-2 py-0.5 text-xs font-medium">
        ML offline
      </span>
    );
  }

  if (!health) {
    return (
      <span className="text-muted-foreground bg-muted rounded px-2 py-0.5 text-xs font-medium">
        ML ...
      </span>
    );
  }

  if (health.status === 'ready') {
    return (
      <span
        className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400"
        title={`${health.predictions} predictions cached`}
      >
        ML ready
      </span>
    );
  }

  // Warming / not loaded — show stage detail
  const stageLabel = STAGE_LABELS[health.stage ?? 'idle'] ?? health.stage;

  if (health.stage === 'failed') {
    return (
      <span
        className="text-destructive bg-destructive/10 rounded px-2 py-0.5 text-xs font-medium"
        title={stageLabel}
      >
        ML failed
      </span>
    );
  }

  return (
    <span
      className="rounded bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400 animate-pulse"
      title={stageLabel}
    >
      ML: {stageLabel.toLowerCase()}
    </span>
  );
}

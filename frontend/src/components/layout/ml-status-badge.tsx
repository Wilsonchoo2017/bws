'use client';

import { useEffect, useRef, useState } from 'react';

interface CacheStatus {
  signals: boolean;
  signals_be: boolean;
  liquidity_bl: boolean;
  liquidity_be: boolean;
}

interface MlHealth {
  status: 'ready' | 'not_loaded' | 'no_predictions' | 'warming';
  models_loaded: boolean;
  predictions: number;
  stage?: 'idle' | 'loading_models' | 'scoring' | 'ready' | 'failed';
  caches?: CacheStatus;
  all_warm?: boolean;
}

const STAGE_LABELS: Record<string, string> = {
  idle: 'Waiting to start',
  loading_models: 'Loading models',
  scoring: 'Computing predictions',
  ready: 'Ready',
  failed: 'Warmup failed',
};

const CACHE_LABELS: Record<string, string> = {
  signals: 'Signals',
  signals_be: 'BE Signals',
  liquidity_bl: 'BL Liquidity',
  liquidity_be: 'BE Liquidity',
};

const FAST_INTERVAL = 3_000;
const SLOW_INTERVAL = 30_000;

function buildCacheTooltip(caches: CacheStatus): string {
  return Object.entries(caches)
    .map(([key, warm]) => `${CACHE_LABELS[key] ?? key}: ${warm ? 'warm' : 'cold'}`)
    .join('\n');
}

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

          // Switch to slow polling once fully warm
          const isReady = data.all_warm === true;
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
        API offline
      </span>
    );
  }

  if (!health) {
    return (
      <span className="text-muted-foreground bg-muted rounded px-2 py-0.5 text-xs font-medium">
        ...
      </span>
    );
  }

  const cacheTooltip = health.caches ? buildCacheTooltip(health.caches) : '';
  const coldCaches = health.caches
    ? Object.entries(health.caches).filter(([, warm]) => !warm).map(([k]) => CACHE_LABELS[k] ?? k)
    : [];

  // Fully warm
  if (health.all_warm) {
    return (
      <span
        className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400"
        title={`${health.predictions} predictions\n${cacheTooltip}`}
      >
        Ready
      </span>
    );
  }

  // ML failed
  if (health.stage === 'failed') {
    return (
      <span
        className="text-destructive bg-destructive/10 rounded px-2 py-0.5 text-xs font-medium"
        title={`ML warmup failed\n${cacheTooltip}`}
      >
        ML failed
      </span>
    );
  }

  // ML not loaded yet
  if (!health.models_loaded) {
    const stageLabel = STAGE_LABELS[health.stage ?? 'idle'] ?? health.stage;
    return (
      <span
        className="animate-pulse rounded bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400"
        title={stageLabel}
      >
        ML: {stageLabel.toLowerCase()}
      </span>
    );
  }

  // ML ready but caches still warming
  const warmCount = health.caches ? Object.values(health.caches).filter(Boolean).length : 0;
  const totalCaches = health.caches ? Object.keys(health.caches).length : 0;

  return (
    <span
      className="animate-pulse rounded bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400"
      title={`Warming caches (${warmCount}/${totalCaches})\n${cacheTooltip}\n\nCold: ${coldCaches.join(', ')}`}
    >
      Warming {warmCount}/{totalCaches}
    </span>
  );
}

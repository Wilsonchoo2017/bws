export function scoreColor(score: number | null): string {
  if (score === null) return 'text-muted-foreground';
  if (score >= 80) return 'text-emerald-400';
  if (score >= 65) return 'text-emerald-600 dark:text-emerald-500';
  if (score >= 50) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= 35) return 'text-orange-500';
  return 'text-red-500';
}

export function scoreBg(score: number | null): string {
  if (score === null) return '';
  if (score >= 80) return 'bg-emerald-500/10';
  if (score >= 65) return 'bg-emerald-500/5';
  if (score >= 50) return 'bg-yellow-500/5';
  if (score >= 35) return 'bg-orange-500/5';
  return 'bg-red-500/10';
}

export function rankToPercentile(rank: number | null, size: number): number | null {
  if (rank === null || size <= 0) return null;
  return Math.round(((size - rank) / size) * 100);
}

export function formatMetricValue(key: string, value: number): string {
  if (key === 'consistency') return `${(value * 100).toFixed(0)}%`;
  if (key === 'trend') return `${value >= 1 ? '+' : ''}${((value - 1) * 100).toFixed(0)}%`;
  if (key === 'listing_ratio') return `${value.toFixed(1)}x`;
  return value?.toFixed(1) ?? '--';
}

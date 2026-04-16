export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'blocked_verify';

export interface QueueStats {
  total: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
}

export interface WorkerJob {
  job_id: string;
  status: JobStatus;
  scraper_id: string;
  url: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  items_found: number;
  error: string | null;
  progress: string | null;
  worker_no: number | null;
  reason: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  outcome: string | null;
  duration_ms: number | null;
  source: string | null;
}

export interface JobAttempt {
  attempt_number: number;
  error_category: string | null;
  error_message: string | null;
  duration_seconds: number | null;
  created_at: string | null;
}

export interface JobSnapshot {
  source: string;
  scraped_at: string | null;
  summary: string | null;
}

export interface WorkerJobDetail extends WorkerJob {
  attempts: JobAttempt[];
  snapshots: JobSnapshot[];
  set_number: string | null;
  task_type: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  depends_on: string | null;
  locked_by: string | null;
}

export interface SourceCoverage {
  source: string;
  total_rows: number;
  distinct_sets: number;
  missing_sets: number;
  coverage_pct: number;
  latest_scraped: string | null;
}

export interface CoverageData {
  total_sets: number;
  sources: SourceCoverage[];
}

export interface SetSourceStatus {
  covered: boolean;
  latest: string | null;
}

export interface SetCoverageRow {
  set_number: string;
  title: string;
  sources: Record<string, SetSourceStatus>;
  covered_count: number;
  total_sources: number;
}

export interface SetCoverageData {
  sets: SetCoverageRow[];
  total_count: number;
  page: number;
  page_size: number;
  source_labels: string[];
  total_sources: number;
  distribution: Record<number, number>;
}

// Marketplace saturation coverage (Shopee / Carousell competition sweeps).
// Mirrors GET /api/stats/marketplace-coverage.

export type MarketplaceTier =
  | 'cart'
  | 'watchlist'
  | 'holdings'
  | 'retiring_soon';

export interface MarketplaceCellData {
  last_checked: string | null;
  listings_count: number | null;
  saturation_score: number | null;
  saturation_level: string | null;
  scraped: boolean;
  fresh: boolean;
  empty: boolean;
}

export interface MarketplaceCoverageRow {
  set_number: string;
  title: string;
  tier: MarketplaceTier | string;
  tier_priority: number;
  stale_days: number;
  shopee: MarketplaceCellData;
  carousell: MarketplaceCellData;
}

export interface MarketplaceAggregate {
  total: number;
  scraped: number;
  fresh: number;
  stale: number;
  empty: number;
  latest: string | null;
}

export interface MarketplaceCoverageData {
  total_targets: number;
  tier_counts: Record<string, number>;
  marketplaces: {
    shopee: MarketplaceAggregate;
    carousell: MarketplaceAggregate;
  };
  rows: MarketplaceCoverageRow[];
}

export function formatDuration(
  start: string | null,
  end: string | null
): string {
  if (!start) return '-';
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const ms = e - s;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const time = d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  if (isToday) return time;
  const date = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  return `${date} ${time}`;
}

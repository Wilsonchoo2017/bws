export type JobStatus = 'queued' | 'running' | 'completed' | 'failed';

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
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '-';
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const ms = e - s;
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

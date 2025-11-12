/**
 * Queue Statistics Banner Component
 * Displays global sync status and queue statistics
 */

import { formatRelativeTime } from "../../utils/sync-helpers.ts";

interface QueueStatsData {
  counts: {
    waiting: number;
    active: number;
    completed: number;
    failed: number;
    delayed: number;
  };
  lastCompleted?: {
    finishedOn?: number;
  };
}

interface QueueStatsBannerProps {
  stats: QueueStatsData | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export default function QueueStatsBanner(
  { stats, isLoading, onRefresh }: QueueStatsBannerProps,
) {
  if (!stats && !isLoading) {
    return (
      <div class="alert alert-warning shadow-lg mb-6">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="stroke-current shrink-0 h-6 w-6"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div>
          <div class="font-bold">Queue service unavailable</div>
          <div class="text-sm">
            Make sure Redis is running to enable background scraping
          </div>
        </div>
      </div>
    );
  }

  const hasActive = stats && stats.counts.active > 0;
  const hasQueued = stats && stats.counts.waiting > 0;
  const hasFailed = stats && stats.counts.failed > 0;
  const lastCompletedTime = stats?.lastCompleted?.finishedOn
    ? formatRelativeTime(new Date(stats.lastCompleted.finishedOn))
    : "Never";

  return (
    <div class="stats shadow bg-base-200 mb-6 w-full">
      <div class="stat">
        <div class="stat-figure text-info">
          {hasActive && (
            <span class="loading loading-spinner loading-lg">
            </span>
          )}
          {!hasActive && (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              class="inline-block w-8 h-8 stroke-current"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          )}
        </div>
        <div class="stat-title">Active Jobs</div>
        <div class="stat-value text-info">
          {isLoading ? "..." : stats?.counts.active || 0}
        </div>
        <div class="stat-desc">
          {hasActive ? "Scraping now" : "No active scraping"}
        </div>
      </div>

      <div class="stat">
        <div class="stat-figure text-secondary">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            class="inline-block w-8 h-8 stroke-current"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
            />
          </svg>
        </div>
        <div class="stat-title">Queued</div>
        <div class="stat-value text-secondary">
          {isLoading ? "..." : stats?.counts.waiting || 0}
        </div>
        <div class="stat-desc">
          {hasQueued ? "Waiting to scrape" : "Queue empty"}
        </div>
      </div>

      <div class="stat">
        <div class="stat-figure text-success">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            class="inline-block w-8 h-8 stroke-current"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div class="stat-title">Completed</div>
        <div class="stat-value text-success">
          {isLoading ? "..." : stats?.counts.completed || 0}
        </div>
        <div class="stat-desc">Last: {lastCompletedTime}</div>
      </div>

      <div class="stat">
        <div class="stat-figure">
          {hasFailed && (
            <div class="badge badge-error badge-lg">
              {stats?.counts.failed}
            </div>
          )}
          {!hasFailed && (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              class="inline-block w-8 h-8 stroke-current text-error opacity-30"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          )}
        </div>
        <div class="stat-title">Failed</div>
        <div class="stat-value text-error">
          {isLoading ? "..." : stats?.counts.failed || 0}
        </div>
        <div class="stat-desc">
          {hasFailed ? <span class="text-error">Needs attention</span> : (
            "All good"
          )}
        </div>
      </div>

      <div class="stat">
        <div class="stat-actions">
          <button
            class="btn btn-sm btn-outline"
            onClick={onRefresh}
            disabled={isLoading}
          >
            {isLoading && <span class="loading loading-spinner loading-xs" />}
            {!isLoading && (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            )}
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}

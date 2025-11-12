/**
 * Queue Health Banner Component
 * Simplified health indicator for products page with link to detailed dashboard
 */

import { formatRelativeTime } from "../../utils/sync-helpers.ts";
import {
  assessQueueHealth,
  getHealthBadgeClass,
  getHealthIcon,
  getHealthLabel,
  type QueueHealthStatus,
} from "../../utils/queue-health.ts";

interface JobInfo {
  id: string;
  processedOn?: number;
  finishedOn?: number;
  attemptsMade?: number;
  failedReason?: string;
}

interface QueueStatsData {
  queue: {
    counts: {
      waiting: number;
      active: number;
      completed: number;
      failed: number;
      delayed: number;
    };
  };
  jobs: {
    waiting: JobInfo[];
    active: JobInfo[];
    completed: JobInfo[];
    failed: JobInfo[];
  };
  workerStatus?: {
    isAlive: boolean;
    isPaused: boolean;
    isRunning: boolean;
  };
}

interface QueueHealthBannerProps {
  stats: QueueStatsData | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export default function QueueHealthBanner(
  { stats, isLoading, onRefresh }: QueueHealthBannerProps,
) {
  // Assess queue health
  const healthAssessment = assessQueueHealth(stats);
  const { status, issues, summary } = healthAssessment;

  // Get top 3 issues to display
  const topIssues = issues.slice(0, 3);

  // Format last completion time
  const lastCompletedTime = stats?.jobs.completed[0]?.finishedOn
    ? formatRelativeTime(new Date(stats.jobs.completed[0].finishedOn))
    : "Never";

  const hasActive = stats && stats.queue.counts.active > 0;
  const hasQueued = stats && stats.queue.counts.waiting > 0;
  const hasFailed = stats && stats.queue.counts.failed > 0;

  return (
    <div class="mb-6">
      {/* Health Status Header */}
      <div class={`alert shadow-lg mb-4 ${getAlertClass(status)}`}>
        <div class="flex-1">
          <div class="flex items-center gap-3">
            <span class={`badge badge-lg ${getHealthBadgeClass(status)}`}>
              {getHealthIcon(status)} {getHealthLabel(status)}
            </span>
            <div>
              <div class="font-bold">{summary}</div>
              {topIssues.length > 0 && (
                <div class="text-sm mt-1">
                  {topIssues.map((issue, idx) => (
                    <div key={idx} class="flex items-start gap-1 mt-1">
                      <span class="opacity-70">
                        {issue.severity === "error" ? "●" : "○"}
                      </span>
                      <span>{issue.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        <div class="flex-none">
          <a
            href="/queue"
            class="btn btn-sm btn-ghost"
          >
            View Details →
          </a>
        </div>
      </div>

      {/* Quick Stats */}
      {stats && (
        <div class="stats stats-vertical lg:stats-horizontal shadow bg-base-200 w-full">
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
              {isLoading ? "..." : stats.queue.counts.active}
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
              {isLoading ? "..." : stats.queue.counts.waiting}
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
              {isLoading ? "..." : stats.queue.counts.completed}
            </div>
            <div class="stat-desc">Last: {lastCompletedTime}</div>
          </div>

          <div class="stat">
            <div class="stat-figure">
              {hasFailed && (
                <div class="badge badge-error badge-lg">
                  {stats.queue.counts.failed}
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
              {isLoading ? "..." : stats.queue.counts.failed}
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
      )}
    </div>
  );
}

/**
 * Get alert class based on health status
 */
function getAlertClass(status: QueueHealthStatus): string {
  switch (status) {
    case "healthy":
      return "alert-success";
    case "warning":
      return "alert-warning";
    case "error":
      return "alert-error";
    case "unavailable":
      return "alert-info";
  }
}

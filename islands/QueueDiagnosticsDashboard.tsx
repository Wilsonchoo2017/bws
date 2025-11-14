/**
 * Queue Diagnostics Dashboard
 * Comprehensive monitoring and diagnostics for the scraping queue
 */

import { useEffect, useState } from "preact/hooks";
import { formatRelativeTime } from "../utils/sync-helpers.ts";
import {
  assessQueueHealth,
  getHealthBadgeClass,
  getHealthIcon,
  getHealthLabel,
  type QueueHealthAssessment,
} from "../utils/queue-health.ts";
import QueueHealthBanner from "./components/QueueHealthBanner.tsx";
import QueueDashboardSkeleton from "../components/skeletons/QueueDashboardSkeleton.tsx";

interface JobInfo {
  id: string;
  name?: string;
  data?: {
    url?: string;
    itemId?: string;
    itemType?: string;
    setNumber?: string;
  };
  processedOn?: number;
  finishedOn?: number;
  timestamp?: number;
  attemptsMade?: number;
  failedReason?: string;
  progress?: number | object;
  returnvalue?: unknown;
}

interface QueueStatsData {
  queue: {
    name: string;
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

export default function QueueDiagnosticsDashboard() {
  const [stats, setStats] = useState<QueueStatsData | null>(null);
  const [health, setHealth] = useState<QueueHealthAssessment | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetSuccess, setResetSuccess] = useState<string | null>(null);

  // Fetch queue status
  const fetchQueueStats = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/scrape-queue-status");
      if (response.ok) {
        const data = await response.json();
        setStats(data);

        // Assess health
        const healthAssessment = assessQueueHealth(data);
        setHealth(healthAssessment);
      } else {
        setStats(null);
        const healthAssessment = assessQueueHealth(null);
        setHealth(healthAssessment);
      }
    } catch (err) {
      console.error("Queue stats fetch error:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch stats");
      setStats(null);
      const healthAssessment = assessQueueHealth(null);
      setHealth(healthAssessment);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset queue handler
  const handleResetQueue = async () => {
    setIsResetting(true);
    setError(null);
    setResetSuccess(null);
    setShowResetConfirm(false);

    try {
      const response = await fetch("/api/queue-reset", {
        method: "POST",
      });

      if (response.ok) {
        const result = await response.json();
        setResetSuccess(
          `Queue reset complete! Cleared ${result.cleared.total} jobs, added ${result.repopulated.total} new jobs.`,
        );
        // Refresh stats after reset
        await fetchQueueStats();
      } else {
        const errorData = await response.json();
        setError(errorData.message || "Failed to reset queue");
      }
    } catch (err) {
      console.error("Queue reset error:", err);
      setError(err instanceof Error ? err.message : "Failed to reset queue");
    } finally {
      setIsResetting(false);
    }
  };

  // Auto-refresh every 30 seconds
  useEffect(() => {
    fetchQueueStats();
    const interval = setInterval(fetchQueueStats, 30000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading && !stats) {
    return <QueueDashboardSkeleton />;
  }

  return (
    <div class="space-y-6">
      {/* Queue Health Banner */}
      <QueueHealthBanner
        stats={stats}
        isLoading={isLoading}
        onRefresh={fetchQueueStats}
      />

      {/* Health Status Card */}
      {health && (
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div class="flex items-center gap-4">
                <span
                  class={`badge badge-lg ${getHealthBadgeClass(health.status)}`}
                >
                  {getHealthIcon(health.status)} {getHealthLabel(health.status)}
                </span>
                <div>
                  <h2 class="text-2xl font-bold">{health.summary}</h2>
                  {stats && (
                    <p class="text-sm text-base-content/70 mt-1">
                      Queue: {stats.queue.name}
                    </p>
                  )}
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  class="btn btn-outline"
                  onClick={fetchQueueStats}
                  disabled={isLoading || isResetting}
                >
                  {isLoading && <span class="loading loading-spinner" />}
                  {!isLoading && (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      class="h-5 w-5"
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
                <button
                  class="btn btn-error btn-outline"
                  onClick={() => setShowResetConfirm(true)}
                  disabled={isLoading || isResetting}
                >
                  {isResetting && <span class="loading loading-spinner" />}
                  {!isResetting && (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      class="h-5 w-5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  )}
                  Reset Queue
                </button>
              </div>
            </div>

            {/* Issues List */}
            {health.issues.length > 0 && (
              <div class="mt-4 space-y-2">
                <h3 class="font-semibold text-lg">Issues & Warnings</h3>
                <div class="space-y-2">
                  {health.issues.map((issue, idx) => (
                    <div
                      key={idx}
                      class={`alert ${
                        issue.severity === "error"
                          ? "alert-error"
                          : "alert-warning"
                      }`}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        class="stroke-current shrink-0 h-6 w-6"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        {issue.severity === "error"
                          ? (
                            <path
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              stroke-width="2"
                              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          )
                          : (
                            <path
                              stroke-linecap="round"
                              stroke-linejoin="round"
                              stroke-width="2"
                              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                            />
                          )}
                      </svg>
                      <span>{issue.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Metrics Grid */}
      {stats && (
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Active Jobs"
            value={stats.queue.counts.active}
            color="info"
            icon="⚡"
          />
          <MetricCard
            title="Waiting"
            value={stats.queue.counts.waiting}
            color="warning"
            icon="⏳"
          />
          <MetricCard
            title="Completed"
            value={stats.queue.counts.completed}
            color="success"
            icon="✓"
          />
          <MetricCard
            title="Failed"
            value={stats.queue.counts.failed}
            color="error"
            icon="✕"
          />
        </div>
      )}

      {/* Worker Status */}
      {stats?.workerStatus && (
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body">
            <h2 class="card-title">Worker Status</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
              <StatusIndicator
                label="Worker Alive"
                value={stats.workerStatus.isAlive}
              />
              <StatusIndicator
                label="Worker Paused"
                value={stats.workerStatus.isPaused}
                invert
              />
              <StatusIndicator
                label="Worker Running"
                value={stats.workerStatus.isRunning}
              />
            </div>
          </div>
        </div>
      )}

      {/* Active Jobs Panel */}
      {stats && stats.jobs.active.length > 0 && (
        <JobsPanel
          title="Active Jobs"
          jobs={stats.jobs.active}
          type="active"
        />
      )}

      {/* Failed Jobs Panel */}
      {stats && stats.jobs.failed.length > 0 && (
        <JobsPanel
          title="Failed Jobs"
          jobs={stats.jobs.failed}
          type="failed"
        />
      )}

      {/* Waiting Jobs Panel */}
      {stats && stats.jobs.waiting.length > 0 && (
        <JobsPanel
          title="Waiting Jobs"
          jobs={stats.jobs.waiting}
          type="waiting"
        />
      )}

      {/* Completed Jobs Panel */}
      {stats && stats.jobs.completed.length > 0 && (
        <JobsPanel
          title="Recently Completed Jobs"
          jobs={stats.jobs.completed}
          type="completed"
        />
      )}

      {/* Success Message */}
      {resetSuccess && (
        <div class="alert alert-success">
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
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>{resetSuccess}</span>
          <button
            class="btn btn-sm btn-ghost"
            onClick={() => setResetSuccess(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div class="alert alert-error">
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
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Error: {error}</span>
        </div>
      )}

      {/* Reset Confirmation Dialog */}
      {showResetConfirm && (
        <dialog class="modal modal-open">
          <div class="modal-box">
            <h3 class="font-bold text-lg">Reset Queue?</h3>
            <p class="py-4">
              This will immediately obliterate all jobs including active ones.
              Running job code may continue in the background but won't affect
              queue state or retry.
            </p>
            <div class="modal-action">
              <button
                class="btn btn-ghost"
                onClick={() => setShowResetConfirm(false)}
                disabled={isResetting}
              >
                Cancel
              </button>
              <button
                class="btn btn-error"
                onClick={handleResetQueue}
                disabled={isResetting}
              >
                {isResetting && <span class="loading loading-spinner" />}
                Reset Queue
              </button>
            </div>
          </div>
          <div
            class="modal-backdrop"
            onClick={() => !isResetting && setShowResetConfirm(false)}
          />
        </dialog>
      )}
    </div>
  );
}

// Metric Card Component
function MetricCard({
  title,
  value,
  color,
  icon,
}: {
  title: string;
  value: number;
  color: "info" | "warning" | "success" | "error";
  icon: string;
}) {
  return (
    <div class="stat bg-base-100 shadow rounded-box">
      <div class={`stat-figure text-${color}`}>
        <span class="text-3xl">{icon}</span>
      </div>
      <div class="stat-title">{title}</div>
      <div class={`stat-value text-${color}`}>{value}</div>
    </div>
  );
}

// Status Indicator Component
function StatusIndicator({
  label,
  value,
  invert = false,
}: {
  label: string;
  value: boolean;
  invert?: boolean;
}) {
  const isGood = invert ? !value : value;
  return (
    <div class="flex items-center gap-3">
      <div
        class={`w-3 h-3 rounded-full ${isGood ? "bg-success" : "bg-error"}`}
      >
      </div>
      <div>
        <div class="text-sm text-base-content/70">{label}</div>
        <div class="font-semibold">
          {value ? "Yes" : "No"}
        </div>
      </div>
    </div>
  );
}

// Jobs Panel Component
function JobsPanel({
  title,
  jobs,
  type,
}: {
  title: string;
  jobs: JobInfo[];
  type: "active" | "waiting" | "completed" | "failed";
}) {
  const now = Date.now();

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        <h2 class="card-title">{title}</h2>
        <div class="overflow-x-auto">
          <table class="table table-zebra w-full">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Type</th>
                <th>Item</th>
                {type === "active" && <th>Processing Time</th>}
                {type === "active" && <th>Attempts</th>}
                {type === "failed" && <th>Reason</th>}
                {type === "failed" && <th>Attempts</th>}
                {type === "completed" && <th>Completed</th>}
                {type === "waiting" && <th>Queued</th>}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td class="font-mono text-xs">
                    {job.id?.toString()}
                  </td>
                  <td>
                    <span class="badge badge-sm">
                      {job.name || "Unknown"}
                    </span>
                  </td>
                  <td class="max-w-xs truncate">
                    {job.data?.itemId || job.data?.setNumber ||
                      job.data?.url?.substring(0, 50) || "N/A"}
                  </td>
                  {type === "active" && (
                    <td>
                      {job.processedOn
                        ? (
                          <>
                            {formatRelativeTime(new Date(job.processedOn))}
                            {now - job.processedOn > 10 * 60 * 1000 && (
                              <span class="badge badge-warning badge-sm ml-2">
                                Stuck?
                              </span>
                            )}
                          </>
                        )
                        : "N/A"}
                    </td>
                  )}
                  {(type === "active" || type === "failed") && (
                    <td>
                      <span
                        class={`badge ${
                          (job.attemptsMade ?? 0) >= 3
                            ? "badge-error"
                            : "badge-warning"
                        }`}
                      >
                        {job.attemptsMade ?? 0}/3
                      </span>
                    </td>
                  )}
                  {type === "failed" && (
                    <td class="max-w-xs">
                      <div class="text-sm text-error truncate">
                        {job.failedReason || "Unknown error"}
                      </div>
                    </td>
                  )}
                  {type === "completed" && (
                    <td>
                      {job.finishedOn
                        ? formatRelativeTime(new Date(job.finishedOn))
                        : "N/A"}
                    </td>
                  )}
                  {type === "waiting" && (
                    <td>
                      {job.timestamp
                        ? formatRelativeTime(new Date(job.timestamp))
                        : "N/A"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

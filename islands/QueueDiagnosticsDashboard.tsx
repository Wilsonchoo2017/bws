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
  const [isTriggeringRescrape, setIsTriggeringRescrape] = useState(false);
  const [showRescrapeConfirm, setShowRescrapeConfirm] = useState(false);
  const [rescrapeSuccess, setRescrapeSuccess] = useState<string | null>(null);
  const [isTriggeringMissingData, setIsTriggeringMissingData] = useState(false);
  const [showMissingDataConfirm, setShowMissingDataConfirm] = useState(false);
  const [missingDataSuccess, setMissingDataSuccess] = useState<string | null>(
    null,
  );
  const [isTriggeringForceScrape, setIsTriggeringForceScrape] = useState(false);
  const [showForceScrapeConfirm, setShowForceScrapeConfirm] = useState(false);
  const [forceScrapeSuccess, setForceScrapeSuccess] = useState<string | null>(
    null,
  );
  const [forceScrapeItemIds, setForceScrapeItemIds] = useState("");

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

  // Trigger rescrape handler
  const handleTriggerRescrape = async () => {
    setIsTriggeringRescrape(true);
    setError(null);
    setRescrapeSuccess(null);
    setShowRescrapeConfirm(false);

    try {
      const response = await fetch("/api/scrape-scheduler", {
        method: "POST",
      });

      if (response.ok) {
        const result = await response.json();
        const total = result.jobsQueued || 0;
        const priorityCounts = result.priorityCounts || {};

        let message = `Successfully queued ${total} scrape jobs!`;
        if (Object.keys(priorityCounts).length > 0) {
          const breakdown = Object.entries(priorityCounts)
            .map(([priority, count]) => `${priority}: ${count}`)
            .join(", ");
          message += ` (${breakdown})`;
        }

        setRescrapeSuccess(message);

        // Refresh stats after triggering
        setTimeout(() => fetchQueueStats(), 1000);
      } else {
        const errorData = await response.json();
        setError(errorData.message || "Failed to trigger rescrape");
      }
    } catch (err) {
      console.error("Rescrape trigger error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to trigger rescrape",
      );
    } finally {
      setIsTriggeringRescrape(false);
    }
  };

  // Trigger missing data detection handler
  const handleTriggerMissingData = async () => {
    setIsTriggeringMissingData(true);
    setError(null);
    setMissingDataSuccess(null);
    setShowMissingDataConfirm(false);

    try {
      const response = await fetch("/api/detect-missing-data", {
        method: "POST",
      });

      if (response.ok) {
        const result = await response.json();
        const jobsEnqueued = result.result?.jobsEnqueued || 0;
        const missingBricklink = result.result?.missingBricklinkData || 0;
        const missingWorldBricks = result.result?.missingWorldBricksData || 0;
        const missingVolume = result.result?.missingVolumeData || 0;

        let message = `Found ${missingBricklink} missing BrickLink items`;
        if (missingWorldBricks > 0) {
          message += `, ${missingWorldBricks} missing WorldBricks data`;
        }
        if (missingVolume > 0) {
          message += `, and ${missingVolume} items with missing volume data`;
        }
        message += `. Queued ${jobsEnqueued} jobs!`;

        setMissingDataSuccess(message);

        // Refresh stats after triggering
        setTimeout(() => fetchQueueStats(), 1000);
      } else {
        const errorData = await response.json();
        setError(errorData.message || "Failed to detect missing data");
      }
    } catch (err) {
      console.error("Missing data detection error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to detect missing data",
      );
    } finally {
      setIsTriggeringMissingData(false);
    }
  };

  // Trigger force scrape handler
  const handleForceScrape = async () => {
    setIsTriggeringForceScrape(true);
    setError(null);
    setForceScrapeSuccess(null);
    setShowForceScrapeConfirm(false);

    try {
      // Parse item IDs from input (comma or newline separated)
      const itemIds = forceScrapeItemIds
        .split(/[,\n]/)
        .map((id) => id.trim())
        .filter((id) => id.length > 0);

      if (itemIds.length === 0) {
        setError("Please enter at least one item ID");
        return;
      }

      const response = await fetch("/api/force-scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ itemIds }),
      });

      if (response.ok) {
        const result = await response.json();
        const jobsEnqueued = result.result?.jobsEnqueued || 0;

        setForceScrapeSuccess(
          `Successfully force-enqueued ${jobsEnqueued} jobs for ${itemIds.length} items!`,
        );
        setForceScrapeItemIds(""); // Clear input

        // Refresh stats after triggering
        setTimeout(() => fetchQueueStats(), 1000);
      } else {
        const errorData = await response.json();
        setError(errorData.error || "Failed to force scrape");
      }
    } catch (err) {
      console.error("Force scrape error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to force scrape",
      );
    } finally {
      setIsTriggeringForceScrape(false);
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
                  disabled={isLoading || isResetting || isTriggeringRescrape}
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
                  class="btn btn-success btn-outline"
                  onClick={() => setShowRescrapeConfirm(true)}
                  disabled={isLoading || isResetting || isTriggeringRescrape}
                >
                  {isTriggeringRescrape && (
                    <span class="loading loading-spinner" />
                  )}
                  {!isTriggeringRescrape && (
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
                  Trigger Scrape All
                </button>
                <button
                  class="btn btn-info btn-outline"
                  onClick={() => setShowMissingDataConfirm(true)}
                  disabled={isLoading || isResetting || isTriggeringMissingData}
                >
                  {isTriggeringMissingData && (
                    <span class="loading loading-spinner" />
                  )}
                  {!isTriggeringMissingData && (
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
                        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                      />
                    </svg>
                  )}
                  Detect Missing Data
                </button>
                <button
                  class="btn btn-warning btn-outline"
                  onClick={() => setShowForceScrapeConfirm(true)}
                  disabled={isLoading || isTriggeringForceScrape}
                >
                  {isTriggeringForceScrape && (
                    <span class="loading loading-spinner" />
                  )}
                  {!isTriggeringForceScrape && (
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
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                  )}
                  Force Scrape
                </button>
                <button
                  class="btn btn-error btn-outline"
                  onClick={() => setShowResetConfirm(true)}
                  disabled={isLoading || isResetting || isTriggeringRescrape}
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

      {/* Success Message - Queue Reset */}
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

      {/* Success Message - Rescrape Triggered */}
      {rescrapeSuccess && (
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
          <span>{rescrapeSuccess}</span>
          <button
            class="btn btn-sm btn-ghost"
            onClick={() => setRescrapeSuccess(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Success Message - Missing Data Detection */}
      {missingDataSuccess && (
        <div class="alert alert-info">
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
          <span>{missingDataSuccess}</span>
          <button
            class="btn btn-sm btn-ghost"
            onClick={() => setMissingDataSuccess(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Success Message - Force Scrape */}
      {forceScrapeSuccess && (
        <div class="alert alert-warning">
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
          <span>{forceScrapeSuccess}</span>
          <button
            class="btn btn-sm btn-ghost"
            onClick={() => setForceScrapeSuccess(null)}
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

      {/* Rescrape Confirmation Dialog */}
      {showRescrapeConfirm && (
        <dialog class="modal modal-open">
          <div class="modal-box">
            <h3 class="font-bold text-lg">Trigger Scrape All?</h3>
            <p class="py-4">
              This will queue scrape jobs for all products that need updates
              from Bricklink. The scheduler will intelligently prioritize:
            </p>
            <ul class="list-disc list-inside py-2 space-y-1">
              <li>
                <strong>HIGH priority:</strong> Products missing Bricklink data
              </li>
              <li>
                <strong>MEDIUM priority:</strong> Products with incomplete data
              </li>
              <li>
                <strong>NORMAL priority:</strong> Products needing refresh
              </li>
            </ul>
            <p class="pt-2 text-sm text-base-content/70">
              Jobs will be processed by the queue worker. This is safe to run
              and won't reset existing jobs.
            </p>
            <div class="modal-action">
              <button
                class="btn btn-ghost"
                onClick={() => setShowRescrapeConfirm(false)}
                disabled={isTriggeringRescrape}
              >
                Cancel
              </button>
              <button
                class="btn btn-success"
                onClick={handleTriggerRescrape}
                disabled={isTriggeringRescrape}
              >
                {isTriggeringRescrape && (
                  <span class="loading loading-spinner" />
                )}
                Trigger Scrape All
              </button>
            </div>
          </div>
          <div
            class="modal-backdrop"
            onClick={() =>
              !isTriggeringRescrape && setShowRescrapeConfirm(false)}
          />
        </dialog>
      )}

      {/* Confirmation Modal - Missing Data Detection */}
      {showMissingDataConfirm && (
        <dialog class="modal modal-open">
          <div class="modal-box">
            <h3 class="font-bold text-lg">Detect Missing Data?</h3>
            <p class="py-4">
              This will scan all products to find missing data and queue jobs to
              fill the gaps:
            </p>
            <ul class="list-disc list-inside py-2 space-y-1">
              <li>
                <strong>Missing BrickLink items:</strong>{" "}
                Products with LEGO set numbers but no BrickLink data
              </li>
              <li>
                <strong>Missing WorldBricks data:</strong>{" "}
                Products with LEGO set numbers but no WorldBricks data
              </li>
              <li>
                <strong>Missing volume data:</strong>{" "}
                Items with pricing boxes but no quantity information
              </li>
            </ul>
            <p class="pt-2 text-sm text-info">
              💡 Monthly data checks will automatically downgrade priority if
              data already exists!
            </p>
            <div class="modal-action">
              <button
                class="btn btn-ghost"
                onClick={() => setShowMissingDataConfirm(false)}
                disabled={isTriggeringMissingData}
              >
                Cancel
              </button>
              <button
                class="btn btn-info"
                onClick={handleTriggerMissingData}
                disabled={isTriggeringMissingData}
              >
                {isTriggeringMissingData && (
                  <span class="loading loading-spinner" />
                )}
                Detect Missing Data
              </button>
            </div>
          </div>
          <div
            class="modal-backdrop"
            onClick={() =>
              !isTriggeringMissingData && setShowMissingDataConfirm(false)}
          />
        </dialog>
      )}

      {/* Confirmation Modal - Force Scrape */}
      {showForceScrapeConfirm && (
        <dialog class="modal modal-open">
          <div class="modal-box">
            <h3 class="font-bold text-lg text-warning">
              ⚠️ Force Scrape Items
            </h3>
            <p class="py-4">
              This will force immediate scraping of specific items,{" "}
              <strong>bypassing all validation checks</strong>:
            </p>
            <ul class="list-disc list-inside py-2 space-y-1 text-sm">
              <li>Skips recent scrape check</li>
              <li>Ignores monthly data availability</li>
              <li>Forces HIGH priority regardless of state</li>
            </ul>
            <div class="form-control py-4">
              <label class="label">
                <span class="label-text">
                  Item IDs (comma or newline separated):
                </span>
              </label>
              <textarea
                class="textarea textarea-bordered h-24"
                placeholder="e.g., 10294-1, 75192-1, 21330-1"
                value={forceScrapeItemIds}
                onInput={(e) =>
                  setForceScrapeItemIds(
                    (e.target as HTMLTextAreaElement).value,
                  )}
              />
            </div>
            <p class="text-sm text-warning">
              ⚠️ Use this only for testing or manual intervention!
            </p>
            <div class="modal-action">
              <button
                class="btn btn-ghost"
                onClick={() => {
                  setShowForceScrapeConfirm(false);
                  setForceScrapeItemIds("");
                }}
                disabled={isTriggeringForceScrape}
              >
                Cancel
              </button>
              <button
                class="btn btn-warning"
                onClick={handleForceScrape}
                disabled={isTriggeringForceScrape || !forceScrapeItemIds.trim()}
              >
                {isTriggeringForceScrape && (
                  <span class="loading loading-spinner" />
                )}
                Force Scrape
              </button>
            </div>
          </div>
          <div
            class="modal-backdrop"
            onClick={() => {
              if (!isTriggeringForceScrape) {
                setShowForceScrapeConfirm(false);
                setForceScrapeItemIds("");
              }
            }}
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

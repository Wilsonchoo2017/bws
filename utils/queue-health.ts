/**
 * Queue Health Assessment Utility
 *
 * Provides comprehensive health monitoring for the BullMQ scraping queue.
 * Implements balanced thresholds for warnings and errors.
 */

export type QueueHealthStatus = "healthy" | "warning" | "error" | "unavailable";

export interface QueueHealthMetrics {
  isQueueAvailable: boolean;
  isWorkerResponsive: boolean;
  hasStuckJobs: boolean;
  hasRepeatedFailures: boolean;
  hasDelayedJobs: boolean;
  hasWaitingJobsNotProcessing: boolean;
  timeSinceLastCompletion: number | null; // milliseconds
  failureRate: number; // percentage 0-100
  activeJobAges: number[]; // ages in milliseconds
  oldestActiveJobAge: number | null; // milliseconds
  totalJobsProcessed: number;
}

export interface QueueHealthIssue {
  severity: "warning" | "error";
  message: string;
  timestamp?: number;
}

export interface QueueHealthAssessment {
  status: QueueHealthStatus;
  issues: QueueHealthIssue[];
  metrics: QueueHealthMetrics;
  summary: string;
}

interface JobInfo {
  id: string;
  processedOn?: number;
  finishedOn?: number;
  attemptsMade?: number;
  failedReason?: string;
}

interface QueueStats {
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
    lastActivity?: number;
  };
}

// Thresholds (milliseconds)
const THRESHOLDS = {
  STUCK_JOB_WARNING: 10 * 60 * 1000, // 10 minutes
  STUCK_JOB_ERROR: 15 * 60 * 1000, // 15 minutes
  STALE_COMPLETION_WARNING: 60 * 60 * 1000, // 1 hour
  WAITING_NOT_PROCESSING: 5 * 60 * 1000, // 5 minutes
  HIGH_FAILURE_RATE: 50, // 50%
  MAX_RETRY_ATTEMPTS: 3,
} as const;

/**
 * Assess the overall health of the queue system
 */
export function assessQueueHealth(
  stats: QueueStats | null,
): QueueHealthAssessment {
  // Queue unavailable
  if (!stats) {
    return {
      status: "unavailable",
      issues: [{
        severity: "error",
        message:
          "Queue service is unavailable. Please ensure Redis is running and the queue service has initialized properly.",
      }],
      metrics: createEmptyMetrics(),
      summary: "Queue service is not available",
    };
  }

  const issues: QueueHealthIssue[] = [];
  const metrics = calculateMetrics(stats);

  // Check for critical errors
  const hasErrors = checkForErrors(stats, metrics, issues);

  // Check for warnings
  const hasWarnings = checkForWarnings(stats, metrics, issues);

  // Determine overall status
  let status: QueueHealthStatus;
  if (hasErrors) {
    status = "error";
  } else if (hasWarnings) {
    status = "warning";
  } else {
    status = "healthy";
  }

  // Generate summary
  const summary = generateSummary(status, stats, metrics);

  return {
    status,
    issues,
    metrics,
    summary,
  };
}

/**
 * Calculate health metrics from queue stats
 */
function calculateMetrics(stats: QueueStats): QueueHealthMetrics {
  const now = Date.now();
  const counts = stats.queue.counts;

  // Check if queue is available
  const isQueueAvailable = true; // If we got stats, queue is available

  // Check worker responsiveness
  const isWorkerResponsive = stats.workerStatus?.isAlive ?? true;

  // Calculate active job ages
  const activeJobAges = stats.jobs.active
    .filter((job) => job.processedOn)
    .map((job) => now - job.processedOn!);

  const oldestActiveJobAge = activeJobAges.length > 0
    ? Math.max(...activeJobAges)
    : null;

  // Check for stuck jobs
  const hasStuckJobs = activeJobAges.some((age) =>
    age > THRESHOLDS.STUCK_JOB_WARNING
  );

  // Check for repeated failures (jobs that exhausted retries)
  const hasRepeatedFailures = stats.jobs.failed.some((job) =>
    (job.attemptsMade ?? 0) >= THRESHOLDS.MAX_RETRY_ATTEMPTS
  );

  // Check for delayed jobs
  const hasDelayedJobs = counts.delayed > 0;

  // Calculate time since last completion
  const lastCompletion = stats.jobs.completed[0];
  const timeSinceLastCompletion = lastCompletion?.finishedOn
    ? now - lastCompletion.finishedOn
    : null;

  // Calculate failure rate
  const totalJobsProcessed = counts.completed + counts.failed;
  const failureRate = totalJobsProcessed > 0
    ? (counts.failed / totalJobsProcessed) * 100
    : 0;

  // Check if waiting jobs are not being processed
  const hasWaitingJobsNotProcessing = counts.waiting > 0 &&
    counts.active === 0 &&
    timeSinceLastCompletion !== null &&
    timeSinceLastCompletion > THRESHOLDS.WAITING_NOT_PROCESSING;

  return {
    isQueueAvailable,
    isWorkerResponsive,
    hasStuckJobs,
    hasRepeatedFailures,
    hasDelayedJobs,
    hasWaitingJobsNotProcessing,
    timeSinceLastCompletion,
    failureRate,
    activeJobAges,
    oldestActiveJobAge,
    totalJobsProcessed,
  };
}

/**
 * Check for error-level issues
 * Returns true if any errors found
 */
function checkForErrors(
  stats: QueueStats,
  metrics: QueueHealthMetrics,
  issues: QueueHealthIssue[],
): boolean {
  let hasErrors = false;
  const counts = stats.queue.counts;

  // Worker not responding
  if (!metrics.isWorkerResponsive) {
    hasErrors = true;
    issues.push({
      severity: "error",
      message:
        "Worker is not responding. Jobs will not be processed until the worker is restarted.",
    });
  }

  // Multiple jobs stuck for too long
  const criticallyStuckJobs = metrics.activeJobAges.filter((age) =>
    age > THRESHOLDS.STUCK_JOB_ERROR
  );
  if (criticallyStuckJobs.length > 0) {
    hasErrors = true;
    issues.push({
      severity: "error",
      message:
        `${criticallyStuckJobs.length} job(s) have been active for more than 15 minutes. This may indicate a critical failure.`,
    });
  }

  // High failure rate
  if (
    metrics.failureRate > THRESHOLDS.HIGH_FAILURE_RATE &&
    metrics.totalJobsProcessed >= 10
  ) {
    hasErrors = true;
    issues.push({
      severity: "error",
      message: `High failure rate: ${
        metrics.failureRate.toFixed(1)
      }% of recent jobs have failed. This indicates a systemic problem.`,
    });
  }

  // Waiting jobs not being processed (worker may be dead)
  if (metrics.hasWaitingJobsNotProcessing) {
    hasErrors = true;
    issues.push({
      severity: "error",
      message:
        `${counts.waiting} job(s) waiting to be processed, but worker has not picked them up for over 5 minutes.`,
    });
  }

  return hasErrors;
}

/**
 * Check for warning-level issues
 * Returns true if any warnings found
 */
function checkForWarnings(
  stats: QueueStats,
  metrics: QueueHealthMetrics,
  issues: QueueHealthIssue[],
): boolean {
  let hasWarnings = false;
  const counts = stats.queue.counts;

  // Stuck jobs (warning level)
  const stuckJobs = metrics.activeJobAges.filter(
    (age) =>
      age > THRESHOLDS.STUCK_JOB_WARNING &&
      age <= THRESHOLDS.STUCK_JOB_ERROR,
  );
  if (stuckJobs.length > 0) {
    hasWarnings = true;
    const oldestMinutes = Math.floor(
      (metrics.oldestActiveJobAge ?? 0) / 60000,
    );
    issues.push({
      severity: "warning",
      message:
        `${stuckJobs.length} job(s) have been active for more than 10 minutes (oldest: ${oldestMinutes}min). They may be stuck.`,
    });
  }

  // Failed jobs present
  if (counts.failed > 0) {
    hasWarnings = true;
    const exhaustedRetries = stats.jobs.failed.filter((job) =>
      (job.attemptsMade ?? 0) >= THRESHOLDS.MAX_RETRY_ATTEMPTS
    ).length;

    if (exhaustedRetries > 0) {
      issues.push({
        severity: "warning",
        message:
          `${counts.failed} job(s) have failed. ${exhaustedRetries} have exhausted all retry attempts and need attention.`,
      });
    } else {
      issues.push({
        severity: "warning",
        message:
          `${counts.failed} job(s) have failed but may retry automatically.`,
      });
    }
  }

  // Stale completions (no recent activity)
  if (
    metrics.timeSinceLastCompletion !== null &&
    metrics.timeSinceLastCompletion > THRESHOLDS.STALE_COMPLETION_WARNING
  ) {
    const hoursSince = Math.floor(
      metrics.timeSinceLastCompletion / (60 * 60 * 1000),
    );

    // Only warn if there's actually work to be done
    if (counts.waiting > 0 || counts.active > 0) {
      hasWarnings = true;
      issues.push({
        severity: "warning",
        message:
          `No jobs have completed in the last ${hoursSince} hour(s), but there are jobs pending.`,
      });
    } else if (hoursSince > 24) {
      // Warn even if no pending work if it's been more than a day
      hasWarnings = true;
      issues.push({
        severity: "warning",
        message:
          `No scraping activity in the last ${hoursSince} hour(s). Consider running scheduled scrapes.`,
      });
    }
  }

  // Delayed jobs
  if (metrics.hasDelayedJobs) {
    hasWarnings = true;
    issues.push({
      severity: "warning",
      message:
        `${counts.delayed} job(s) are delayed due to rate limiting or backoff. This is normal behavior.`,
    });
  }

  // Queue backlog
  if (counts.waiting > 10) {
    hasWarnings = true;
    issues.push({
      severity: "warning",
      message:
        `Large queue backlog: ${counts.waiting} job(s) waiting to be processed. This may take some time due to rate limiting.`,
    });
  }

  return hasWarnings;
}

/**
 * Generate a human-readable summary
 */
function generateSummary(
  status: QueueHealthStatus,
  stats: QueueStats,
  _metrics: QueueHealthMetrics,
): string {
  const counts = stats.queue.counts;

  switch (status) {
    case "unavailable":
      return "Queue service is not available";

    case "error":
      return "Critical issues detected - immediate attention required";

    case "warning":
      if (counts.active > 0) {
        return `Processing ${counts.active} job(s) with warning(s)`;
      } else if (counts.waiting > 0) {
        return `${counts.waiting} job(s) queued with warning(s)`;
      } else {
        return "Queue operational with warning(s)";
      }

    case "healthy":
      if (counts.active > 0) {
        return `Processing ${counts.active} job(s) - all systems healthy`;
      } else if (counts.waiting > 0) {
        return `${counts.waiting} job(s) queued - ready to process`;
      } else {
        return "Queue idle - all systems healthy";
      }
  }
}

/**
 * Create empty metrics for unavailable state
 */
function createEmptyMetrics(): QueueHealthMetrics {
  return {
    isQueueAvailable: false,
    isWorkerResponsive: false,
    hasStuckJobs: false,
    hasRepeatedFailures: false,
    hasDelayedJobs: false,
    hasWaitingJobsNotProcessing: false,
    timeSinceLastCompletion: null,
    failureRate: 0,
    activeJobAges: [],
    oldestActiveJobAge: null,
    totalJobsProcessed: 0,
  };
}

/**
 * Get a badge class for the health status (DaisyUI)
 */
export function getHealthBadgeClass(status: QueueHealthStatus): string {
  switch (status) {
    case "healthy":
      return "badge-success";
    case "warning":
      return "badge-warning";
    case "error":
      return "badge-error";
    case "unavailable":
      return "badge-ghost";
  }
}

/**
 * Get an icon for the health status
 */
export function getHealthIcon(status: QueueHealthStatus): string {
  switch (status) {
    case "healthy":
      return "✓";
    case "warning":
      return "⚠";
    case "error":
      return "✕";
    case "unavailable":
      return "○";
  }
}

/**
 * Get a label for the health status
 */
export function getHealthLabel(status: QueueHealthStatus): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "warning":
      return "Warning";
    case "error":
      return "Error";
    case "unavailable":
      return "Unavailable";
  }
}

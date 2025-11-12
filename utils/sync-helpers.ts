/**
 * Utility functions for sync status management
 */

export type SyncStatus =
  | "scraping"
  | "queued"
  | "failed"
  | "up_to_date"
  | "due_soon"
  | "overdue"
  | "paused";

interface BricklinkItem {
  itemId: string;
  itemType: string;
  watchStatus: "active" | "paused" | "stopped" | "archived";
  lastScrapedAt: Date | string | null;
  nextScrapeAt: Date | string | null;
  scrapeIntervalDays: number;
}

interface QueueJob {
  id: string;
  data: {
    itemId?: string;
    url?: string;
  };
  state?: string;
  failedReason?: string;
}

/**
 * Build Bricklink catalog URL from item type and ID
 */
export function buildBricklinkUrl(itemType: string, itemId: string): string {
  return `https://www.bricklink.com/v2/catalog/catalogitem.page?${itemType}=${itemId}`;
}

/**
 * Format timestamp as relative time (e.g., "2 hours ago", "in 3 days")
 */
export function formatRelativeTime(date: Date | string | null): string {
  if (!date) return "Never";

  const now = new Date();
  const targetDate = typeof date === "string" ? new Date(date) : date;
  const diffMs = targetDate.getTime() - now.getTime();
  const diffSeconds = Math.floor(Math.abs(diffMs) / 1000);
  const isPast = diffMs < 0;

  // Less than a minute
  if (diffSeconds < 60) {
    return isPast ? "Just now" : "In a moment";
  }

  // Less than an hour
  if (diffSeconds < 3600) {
    const minutes = Math.floor(diffSeconds / 60);
    return isPast
      ? `${minutes} minute${minutes > 1 ? "s" : ""} ago`
      : `in ${minutes} minute${minutes > 1 ? "s" : ""}`;
  }

  // Less than a day
  if (diffSeconds < 86400) {
    const hours = Math.floor(diffSeconds / 3600);
    return isPast
      ? `${hours} hour${hours > 1 ? "s" : ""} ago`
      : `in ${hours} hour${hours > 1 ? "s" : ""}`;
  }

  // Less than a month
  if (diffSeconds < 2592000) {
    const days = Math.floor(diffSeconds / 86400);
    return isPast
      ? `${days} day${days > 1 ? "s" : ""} ago`
      : `in ${days} day${days > 1 ? "s" : ""}`;
  }

  // More than a month
  const months = Math.floor(diffSeconds / 2592000);
  return isPast
    ? `${months} month${months > 1 ? "s" : ""} ago`
    : `in ${months} month${months > 1 ? "s" : ""}`;
}

/**
 * Get countdown until next scrape
 */
export function getNextScrapeCountdown(nextScrapeAt: Date | string | null): {
  text: string;
  isOverdue: boolean;
  isDueSoon: boolean;
} {
  if (!nextScrapeAt) {
    return {
      text: "Not scheduled",
      isOverdue: false,
      isDueSoon: false,
    };
  }

  const now = new Date();
  const targetDate = typeof nextScrapeAt === "string"
    ? new Date(nextScrapeAt)
    : nextScrapeAt;
  const diffMs = targetDate.getTime() - now.getTime();
  const isOverdue = diffMs < 0;
  const isDueSoon = diffMs > 0 && diffMs < 86400000; // 24 hours

  return {
    text: formatRelativeTime(nextScrapeAt),
    isOverdue,
    isDueSoon,
  };
}

/**
 * Determine sync status for an item based on current state and queue jobs
 */
export function determineSyncStatus(
  item: BricklinkItem,
  queueJobs: {
    active: QueueJob[];
    waiting: QueueJob[];
    failed: QueueJob[];
  },
): SyncStatus {
  // Check if watch status is not active
  if (item.watchStatus !== "active") {
    return "paused";
  }

  // Check if item is currently being scraped
  const isActive = queueJobs.active.some((job) =>
    job.data.itemId === item.itemId ||
    job.data.url?.includes(`${item.itemType}=${item.itemId}`)
  );
  if (isActive) {
    return "scraping";
  }

  // Check if item is in queue
  const isQueued = queueJobs.waiting.some((job) =>
    job.data.itemId === item.itemId ||
    job.data.url?.includes(`${item.itemType}=${item.itemId}`)
  );
  if (isQueued) {
    return "queued";
  }

  // Check if item has failed recently (in last 24 hours)
  const hasFailed = queueJobs.failed.some((job) => {
    const matches = job.data.itemId === item.itemId ||
      job.data.url?.includes(`${item.itemType}=${item.itemId}`);
    return matches;
  });
  if (hasFailed) {
    return "failed";
  }

  // Check scrape schedule
  const { isOverdue, isDueSoon } = getNextScrapeCountdown(item.nextScrapeAt);

  if (isOverdue) {
    return "overdue";
  }

  if (isDueSoon) {
    return "due_soon";
  }

  // Default: up to date
  return "up_to_date";
}

/**
 * Get sync status display info (color, label, icon)
 */
export function getSyncStatusInfo(status: SyncStatus): {
  color: string;
  label: string;
  badgeClass: string;
  icon: string;
} {
  switch (status) {
    case "scraping":
      return {
        color: "info",
        label: "Scraping",
        badgeClass: "badge-info",
        icon: "loading loading-spinner loading-xs",
      };
    case "queued":
      return {
        color: "info",
        label: "Queued",
        badgeClass: "badge-info badge-outline",
        icon: "⏳",
      };
    case "failed":
      return {
        color: "error",
        label: "Failed",
        badgeClass: "badge-error",
        icon: "❌",
      };
    case "up_to_date":
      return {
        color: "success",
        label: "Up to date",
        badgeClass: "badge-success",
        icon: "✓",
      };
    case "due_soon":
      return {
        color: "warning",
        label: "Due soon",
        badgeClass: "badge-warning",
        icon: "⚠",
      };
    case "overdue":
      return {
        color: "error",
        label: "Overdue",
        badgeClass: "badge-error badge-outline",
        icon: "⏰",
      };
    case "paused":
      return {
        color: "neutral",
        label: "Paused",
        badgeClass: "badge-ghost",
        icon: "⏸",
      };
  }
}

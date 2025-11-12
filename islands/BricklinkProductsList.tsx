/**
 * Bricklink Products List Island
 * Displays Bricklink items with comprehensive sync status and manual sync capabilities
 */

import { useEffect, useState } from "preact/hooks";
import { useSignal } from "@preact/signals";
import SyncStatusBadge from "./components/SyncStatusBadge.tsx";
import QueueStatsBanner from "./components/QueueStatsBanner.tsx";
import {
  buildBricklinkUrl,
  determineSyncStatus,
  formatRelativeTime,
  getNextScrapeCountdown,
  type SyncStatus,
} from "../utils/sync-helpers.ts";

interface PricingBox {
  times_sold?: number;
  total_lots?: number;
  total_qty?: number;
  min_price?: { currency: string; amount: number };
  avg_price?: { currency: string; amount: number };
  qty_avg_price?: { currency: string; amount: number };
  max_price?: { currency: string; amount: number };
}

interface BricklinkItem {
  id: number;
  itemId: string;
  itemType: string;
  title: string | null;
  weight: string | null;
  sixMonthNew: PricingBox | null;
  sixMonthUsed: PricingBox | null;
  currentNew: PricingBox | null;
  currentUsed: PricingBox | null;
  watchStatus: "active" | "paused" | "stopped" | "archived";
  scrapeIntervalDays: number;
  lastScrapedAt: string | null;
  nextScrapeAt: string | null;
  createdAt: string;
  updatedAt: string;
}

interface QueueJob {
  id: string;
  name: string;
  data: {
    itemId?: string;
    url?: string;
  };
  state?: string;
  failedReason?: string;
  finishedOn?: number;
}

interface QueueStats {
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
    waiting: QueueJob[];
    active: QueueJob[];
    completed: QueueJob[];
    failed: QueueJob[];
  };
}

export default function BricklinkProductsList() {
  const [items, setItems] = useState<BricklinkItem[]>([]);
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
  const [isLoadingItems, setIsLoadingItems] = useState(true);
  const [isLoadingQueue, setIsLoadingQueue] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters and search
  const searchQuery = useSignal("");
  const watchStatusFilter = useSignal<string>("all");
  const syncStatusFilter = useSignal<string>("all");
  const sortBy = useSignal<string>("updatedAt");
  const sortOrder = useSignal<"asc" | "desc">("desc");
  const page = useSignal(1);
  const limit = 50;

  // Sync actions
  const [syncingItems, setSyncingItems] = useState<Set<string>>(new Set());
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Fetch Bricklink items
  const fetchItems = async () => {
    setIsLoadingItems(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (watchStatusFilter.value !== "all") {
        params.append("watch_status", watchStatusFilter.value);
      }

      const response = await fetch(`/api/bricklink-items?${params}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch items: ${response.statusText}`);
      }

      const data = await response.json();
      const itemsArray = Array.isArray(data) ? data : [data];
      setItems(itemsArray);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setItems([]);
    } finally {
      setIsLoadingItems(false);
    }
  };

  // Fetch queue status
  const fetchQueueStats = async () => {
    setIsLoadingQueue(true);

    try {
      const response = await fetch("/api/scrape-queue-status");
      if (response.ok) {
        const data = await response.json();
        setQueueStats(data);
      } else {
        setQueueStats(null);
      }
    } catch (err) {
      console.error("Queue stats fetch error:", err);
      setQueueStats(null);
    } finally {
      setIsLoadingQueue(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchItems();
    fetchQueueStats();

    // Auto-refresh queue stats every 30 seconds
    const interval = setInterval(fetchQueueStats, 30000);
    return () => clearInterval(interval);
  }, []);

  // Refetch when filters change
  useEffect(() => {
    fetchItems();
  }, [watchStatusFilter.value]);

  // Manual sync action
  const handleSyncNow = async (item: BricklinkItem) => {
    const itemKey = item.itemId;
    setSyncingItems((prev) => new Set(prev).add(itemKey));

    try {
      const url = buildBricklinkUrl(item.itemType, item.itemId);
      const response = await fetch(
        `/api/scrape-bricklink?url=${encodeURIComponent(url)}&save=true`,
        { method: "POST" },
      );

      if (!response.ok) {
        throw new Error(`Failed to enqueue job: ${response.statusText}`);
      }

      const result = await response.json();
      setToastMessage(
        `✓ Scraping job enqueued for ${item.itemId} (Job ID: ${result.job.id})`,
      );

      // Refresh queue stats immediately
      await fetchQueueStats();

      // Clear toast after 5 seconds
      setTimeout(() => setToastMessage(null), 5000);
    } catch (err) {
      setToastMessage(
        `✗ Failed to sync ${item.itemId}: ${
          err instanceof Error ? err.message : "Unknown error"
        }`,
      );
      setTimeout(() => setToastMessage(null), 5000);
    } finally {
      setSyncingItems((prev) => {
        const next = new Set(prev);
        next.delete(itemKey);
        return next;
      });
    }
  };

  // Filter and sort items
  const filteredItems = items
    .filter((item) => {
      // Search filter
      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase();
        const matchesId = item.itemId.toLowerCase().includes(query);
        const matchesTitle = item.title?.toLowerCase().includes(query);
        if (!matchesId && !matchesTitle) return false;
      }

      // Sync status filter
      if (syncStatusFilter.value !== "all" && queueStats) {
        const status = determineSyncStatus(item, {
          active: queueStats.jobs.active,
          waiting: queueStats.jobs.waiting,
          failed: queueStats.jobs.failed,
        });
        if (status !== syncStatusFilter.value) return false;
      }

      return true;
    })
    .sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortBy.value) {
        case "itemId":
          aVal = a.itemId;
          bVal = b.itemId;
          break;
        case "title":
          aVal = a.title || "";
          bVal = b.title || "";
          break;
        case "lastScrapedAt":
          aVal = a.lastScrapedAt ? new Date(a.lastScrapedAt).getTime() : 0;
          bVal = b.lastScrapedAt ? new Date(b.lastScrapedAt).getTime() : 0;
          break;
        case "nextScrapeAt":
          aVal = a.nextScrapeAt ? new Date(a.nextScrapeAt).getTime() : 0;
          bVal = b.nextScrapeAt ? new Date(b.nextScrapeAt).getTime() : 0;
          break;
        default:
          aVal = new Date(a.updatedAt).getTime();
          bVal = new Date(b.updatedAt).getTime();
      }

      if (sortOrder.value === "asc") {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });

  // Pagination
  const totalPages = Math.ceil(filteredItems.length / limit);
  const paginatedItems = filteredItems.slice(
    (page.value - 1) * limit,
    page.value * limit,
  );

  // Format price for display
  const formatPrice = (priceBox: PricingBox | null): string => {
    if (!priceBox || !priceBox.avg_price) return "N/A";
    return `${priceBox.avg_price.currency} ${
      priceBox.avg_price.amount.toFixed(
        2,
      )
    }`;
  };

  return (
    <div class="container mx-auto p-4">
      {/* Toast notification */}
      {toastMessage && (
        <div class="toast toast-top toast-end">
          <div
            class={`alert ${
              toastMessage.startsWith("✓") ? "alert-success" : "alert-error"
            }`}
          >
            <span>{toastMessage}</span>
          </div>
        </div>
      )}

      {/* Queue Statistics Banner */}
      <QueueStatsBanner
        stats={queueStats
          ? {
            counts: queueStats.queue.counts,
            lastCompleted: queueStats.jobs.completed[0],
          }
          : null}
        isLoading={isLoadingQueue}
        onRefresh={fetchQueueStats}
      />

      {/* Filters and Search */}
      <div class="card bg-base-100 shadow-xl mb-6">
        <div class="card-body">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Search */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Search</span>
              </label>
              <input
                type="text"
                placeholder="Item ID or title..."
                class="input input-bordered"
                value={searchQuery.value}
                onInput={(e) =>
                  searchQuery.value = (e.target as HTMLInputElement).value}
              />
            </div>

            {/* Watch Status Filter */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Watch Status</span>
              </label>
              <select
                class="select select-bordered"
                value={watchStatusFilter.value}
                onChange={(e) =>
                  watchStatusFilter.value = (e.target as HTMLSelectElement)
                    .value}
              >
                <option value="all">All</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="stopped">Stopped</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            {/* Sync Status Filter */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Sync Status</span>
              </label>
              <select
                class="select select-bordered"
                value={syncStatusFilter.value}
                onChange={(e) =>
                  syncStatusFilter.value = (e.target as HTMLSelectElement)
                    .value}
              >
                <option value="all">All</option>
                <option value="up_to_date">Up to date</option>
                <option value="due_soon">Due soon</option>
                <option value="overdue">Overdue</option>
                <option value="scraping">Scraping</option>
                <option value="queued">Queued</option>
                <option value="failed">Failed</option>
                <option value="paused">Paused</option>
              </select>
            </div>

            {/* Sort */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Sort By</span>
              </label>
              <select
                class="select select-bordered"
                value={sortBy.value}
                onChange={(e) =>
                  sortBy.value = (e.target as HTMLSelectElement).value}
              >
                <option value="updatedAt">Updated</option>
                <option value="lastScrapedAt">Last Scraped</option>
                <option value="nextScrapeAt">Next Scrape</option>
                <option value="itemId">Item ID</option>
                <option value="title">Title</option>
              </select>
            </div>
          </div>

          <div class="text-sm text-base-content/70 mt-2">
            Showing {paginatedItems.length} of {filteredItems.length} items
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div class="alert alert-error mb-6">
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
          <span>{error}</span>
        </div>
      )}

      {/* Loading State */}
      {isLoadingItems && (
        <div class="flex justify-center items-center py-12">
          <span class="loading loading-spinner loading-lg"></span>
        </div>
      )}

      {/* Empty State */}
      {!isLoadingItems && paginatedItems.length === 0 && (
        <div class="alert alert-info">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            class="stroke-current shrink-0 w-6 h-6"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>No Bricklink items found. Start by scraping some items!</span>
        </div>
      )}

      {/* Items Table */}
      {!isLoadingItems && paginatedItems.length > 0 && (
        <div class="overflow-x-auto">
          <table class="table table-zebra">
            <thead>
              <tr>
                <th>Item ID</th>
                <th>Title</th>
                <th>Sync Status</th>
                <th>Last Scraped</th>
                <th>Next Scrape</th>
                <th>Avg Price</th>
                <th>Watch Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedItems.map((item) => {
                const syncStatus = queueStats
                  ? determineSyncStatus(item, {
                    active: queueStats.jobs.active,
                    waiting: queueStats.jobs.waiting,
                    failed: queueStats.jobs.failed,
                  })
                  : "up_to_date" as SyncStatus;

                const isSyncing = syncingItems.has(item.itemId);
                const isInQueue = syncStatus === "scraping" ||
                  syncStatus === "queued";
                const countdown = getNextScrapeCountdown(item.nextScrapeAt);

                return (
                  <tr key={item.id}>
                    <td>
                      <div class="flex items-center gap-2">
                        <span class="badge badge-outline">
                          {item.itemType}
                        </span>
                        <a
                          href={buildBricklinkUrl(item.itemType, item.itemId)}
                          target="_blank"
                          rel="noopener noreferrer"
                          class="link link-primary"
                        >
                          {item.itemId}
                        </a>
                      </div>
                    </td>
                    <td>
                      <div class="max-w-xs truncate" title={item.title || ""}>
                        {item.title || (
                          <span class="text-base-content/50">No title</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <SyncStatusBadge status={syncStatus} />
                    </td>
                    <td>
                      <span class="text-sm">
                        {formatRelativeTime(item.lastScrapedAt)}
                      </span>
                    </td>
                    <td>
                      <span
                        class={`text-sm ${
                          countdown.isOverdue
                            ? "text-error font-semibold"
                            : countdown.isDueSoon
                            ? "text-warning font-semibold"
                            : ""
                        }`}
                      >
                        {countdown.text}
                      </span>
                      <div class="text-xs text-base-content/50">
                        Every {item.scrapeIntervalDays} days
                      </div>
                    </td>
                    <td>
                      <div class="text-sm">
                        {formatPrice(item.currentNew)}
                      </div>
                    </td>
                    <td>
                      <span
                        class={`badge ${
                          item.watchStatus === "active"
                            ? "badge-success"
                            : "badge-ghost"
                        } badge-sm`}
                      >
                        {item.watchStatus}
                      </span>
                    </td>
                    <td>
                      <button
                        class="btn btn-sm btn-primary"
                        onClick={() => handleSyncNow(item)}
                        disabled={isSyncing || isInQueue}
                      >
                        {isSyncing && (
                          <span class="loading loading-spinner loading-xs" />
                        )}
                        {!isSyncing && "Sync Now"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div class="flex justify-center mt-6">
          <div class="join">
            <button
              class="join-item btn"
              onClick={() => page.value = Math.max(1, page.value - 1)}
              disabled={page.value === 1}
            >
              «
            </button>
            <button class="join-item btn">
              Page {page.value} of {totalPages}
            </button>
            <button
              class="join-item btn"
              onClick={() => page.value = Math.min(totalPages, page.value + 1)}
              disabled={page.value === totalPages}
            >
              »
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

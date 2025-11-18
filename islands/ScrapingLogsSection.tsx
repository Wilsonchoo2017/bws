/**
 * ScrapingLogsSection - Displays scraping session logs for a product
 * Shows recent scraping activity with status, counts, and error messages
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

interface ScrapingLog {
  id: number;
  source: string;
  sourceUrl: string | null;
  productsFound: number;
  productsStored: number;
  status: string;
  errorMessage: string | null;
  sessionLabel: string | null;
  shopName: string | null;
  scrapedAt: string; // ISO date string
}

interface ScrapingLogsSectionProps {
  productId: string;
}

/**
 * Format date to readable string
 */
function formatDate(dateString: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

/**
 * Get badge class based on status
 */
function getStatusBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case "success":
      return "badge-success";
    case "partial":
      return "badge-warning";
    case "failed":
      return "badge-error";
    default:
      return "badge-ghost";
  }
}

/**
 * Get source badge class and display name
 */
function getSourceInfo(source: string): { class: string; display: string } {
  const sourceLower = source.toLowerCase();
  switch (sourceLower) {
    case "shopee":
      return { class: "badge-primary", display: "Shopee" };
    case "bricklink":
      return { class: "badge-secondary", display: "Bricklink" };
    case "toysrus":
      return { class: "badge-accent", display: "ToysRUs" };
    case "brickeconomy":
      return { class: "badge-info", display: "BrickEconomy" };
    case "worldbricks":
      return { class: "badge-success", display: "WorldBricks" };
    case "brickranker":
      return { class: "badge-warning", display: "BrickRanker" };
    default:
      return { class: "badge-ghost", display: source };
  }
}

export default function ScrapingLogsSection(
  { productId }: ScrapingLogsSectionProps,
) {
  const logs = useSignal<ScrapingLog[]>([]);
  const isLoading = useSignal<boolean>(true);
  const error = useSignal<string | null>(null);

  useEffect(() => {
    async function fetchLogs() {
      try {
        isLoading.value = true;
        error.value = null;

        const response = await fetch(
          `/api/scraping-logs/product/${productId}`,
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch logs: ${response.statusText}`);
        }

        const data = await response.json();
        logs.value = data.logs || [];
      } catch (err) {
        console.error("Error fetching scraping logs:", err);
        error.value = err instanceof Error
          ? err.message
          : "Failed to load scraping logs";
      } finally {
        isLoading.value = false;
      }
    }

    fetchLogs();
  }, [productId]);

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        <h2 class="card-title text-xl mb-4">Scraping Logs</h2>

        {isLoading.value && (
          <div class="flex justify-center items-center py-8">
            <span class="loading loading-spinner loading-lg"></span>
          </div>
        )}

        {error.value && (
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
            <span>{error.value}</span>
          </div>
        )}

        {!isLoading.value && !error.value && logs.value.length === 0 && (
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
            <span>No scraping logs found for this product.</span>
          </div>
        )}

        {!isLoading.value && !error.value && logs.value.length > 0 && (
          <div class="overflow-x-auto">
            <table class="table table-zebra">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Found / Stored</th>
                  <th>Shop</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {logs.value.map((log) => {
                  const sourceInfo = getSourceInfo(log.source);
                  return (
                    <tr key={log.id}>
                      <td class="text-sm">
                        {formatDate(log.scrapedAt)}
                      </td>
                      <td>
                        <div class={`badge ${sourceInfo.class}`}>
                          {sourceInfo.display}
                        </div>
                        {log.sessionLabel && (
                          <div class="text-xs text-base-content/60 mt-1">
                            {log.sessionLabel}
                          </div>
                        )}
                      </td>
                      <td>
                        <div class={`badge ${getStatusBadgeClass(log.status)}`}>
                          {log.status}
                        </div>
                      </td>
                      <td class="text-sm">
                        <span class="font-semibold">{log.productsFound}</span>
                        {" / "}
                        <span class="font-semibold">{log.productsStored}</span>
                      </td>
                      <td class="text-sm">
                        {log.shopName || <span class="text-base-content/40">-</span>}
                      </td>
                      <td>
                        {log.errorMessage
                          ? (
                            <div class="tooltip tooltip-left" data-tip={log.errorMessage}>
                              <button class="btn btn-ghost btn-xs">
                                View Error
                              </button>
                            </div>
                          )
                          : <span class="text-base-content/40">-</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading.value && !error.value && logs.value.length > 0 && (
          <div class="text-sm text-base-content/60 mt-2">
            Showing last {logs.value.length} scraping session{logs.value
              .length !== 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  );
}

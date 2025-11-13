import { useComputed, useSignal } from "@preact/signals";
import { useEffect, useState } from "preact/hooks";
import { formatDate, formatNumber, formatPrice } from "../utils/formatters.ts";
import { PAGINATION } from "../constants/app-config.ts";
import type { ProductSource } from "../db/schema.ts";
import QueueHealthBanner from "./components/QueueHealthBanner.tsx";

interface Product {
  id: number;
  source: ProductSource;
  productId: string | null;
  name: string | null;
  brand: string | null;
  currency: string | null;
  price: number | null;
  priceMin: number | null;
  priceMax: number | null;
  priceBeforeDiscount: number | null;
  image: string | null;
  images: string[] | null;
  legoSetNumber: string | null;

  // Shopee-specific fields
  unitsSold: number | null;
  lifetimeSold: number | null;
  liked_count: number | null;
  commentCount: number | null;
  view_count: number | null;
  avgStarRating: number | null;
  ratingCount: number[] | null;
  stockInfoSummary: string | null;
  stockType: number | null;
  currentStock: number | null;
  isAdult: boolean | null;
  isMart: boolean | null;
  isPreferred: boolean | null;
  isServiceByShopee: boolean | null;
  shopId: number | null;
  shopName: string | null;
  shopLocation: string | null;

  // Toys"R"Us-specific fields
  sku: string | null;
  categoryNumber: string | null;
  categoryName: string | null;
  ageRange: string | null;

  rawData: unknown | null;
  createdAt: Date | null;
  updatedAt: Date | null;
  hasBricklinkData: boolean;
}

interface Pagination {
  page: number;
  limit: number;
  totalCount: number;
  totalPages: number;
  hasNextPage: boolean;
  hasPrevPage: boolean;
}

interface ApiResponse {
  items: Product[];
  pagination: Pagination;
}

interface JobInfo {
  id: string;
  data?: {
    url?: string;
    itemId?: string;
    itemType?: string;
  };
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

type SortBy = "price" | "sold" | "createdAt" | "updatedAt";
type SortOrder = "asc" | "desc";

export default function ProductsList() {
  const items = useSignal<Product[]>([]);
  const pagination = useSignal<Pagination | null>(null);
  const isLoading = useSignal(false);
  const error = useSignal<string | null>(null);

  // Queue stats state
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
  const [isLoadingQueue, setIsLoadingQueue] = useState(true);

  // Filter and sort state
  const searchQuery = useSignal("");
  const legoSetFilter = useSignal("");
  const sourceFilter = useSignal<ProductSource | "all">("all");
  const sortBy = useSignal<SortBy>("updatedAt");
  const sortOrder = useSignal<SortOrder>("desc");
  const currentPage = useSignal(1);

  // Manual add modal state
  const showAddModal = useSignal(false);
  const addLegoSetNumber = useSignal("");
  const isAdding = useSignal(false);
  const addError = useSignal<string | null>(null);
  const addSuccess = useSignal<string | null>(null);

  // Debounced search query
  const debouncedSearch = useSignal("");

  useEffect(() => {
    const timer = setTimeout(() => {
      debouncedSearch.value = searchQuery.value;
      currentPage.value = 1; // Reset to first page on search
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery.value]);

  // Fetch products
  const fetchProducts = async () => {
    isLoading.value = true;
    error.value = null;

    try {
      const params = new URLSearchParams({
        page: currentPage.value.toString(),
        limit: PAGINATION.DEFAULT_LIMIT.toString(),
        sortBy: sortBy.value,
        sortOrder: sortOrder.value,
      });

      if (debouncedSearch.value.trim()) {
        params.set("search", debouncedSearch.value.trim());
      }

      if (legoSetFilter.value.trim()) {
        params.set("legoSetNumber", legoSetFilter.value.trim());
      }

      if (sourceFilter.value) {
        params.set("source", sourceFilter.value);
      }

      const response = await fetch(`/api/shopee-items?${params}`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ApiResponse = await response.json();
      items.value = data.items;
      pagination.value = data.pagination;
    } catch (err) {
      error.value = err instanceof Error
        ? err.message
        : "Failed to fetch products";
      console.error("Error fetching products:", err);
    } finally {
      isLoading.value = false;
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

  // Handle manual product add
  const handleAddProduct = async () => {
    const setNumber = addLegoSetNumber.value.trim();

    // Validate input
    if (!setNumber) {
      addError.value = "Please enter a LEGO set number";
      return;
    }

    if (!/^\d{5}$/.test(setNumber)) {
      addError.value =
        "Please enter a valid 5-digit LEGO set number (e.g., 75192)";
      return;
    }

    isAdding.value = true;
    addError.value = null;
    addSuccess.value = null;

    try {
      const response = await fetch("/api/products/manual", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          legoSetNumber: setNumber,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `HTTP error! status: ${response.status}`);
      }

      // Show success message with job info
      addSuccess.value = data.message ||
        "Scraping job enqueued! Data will appear once scraping completes.";
      addLegoSetNumber.value = "";

      // Close modal and refresh after showing success
      setTimeout(() => {
        showAddModal.value = false;
        addSuccess.value = null;
        // Refresh queue stats to show the new job
        fetchQueueStats();
      }, 3000);
    } catch (err) {
      addError.value = err instanceof Error
        ? err.message
        : "Failed to add product";
      console.error("Error adding product:", err);
    } finally {
      isAdding.value = false;
    }
  };

  // Handle modal close
  const handleCloseModal = () => {
    showAddModal.value = false;
    addLegoSetNumber.value = "";
    addError.value = null;
    addSuccess.value = null;
  };

  // Fetch on mount and when dependencies change
  useEffect(() => {
    fetchProducts();
  }, [
    debouncedSearch.value,
    legoSetFilter.value,
    sourceFilter.value,
    sortBy.value,
    sortOrder.value,
    currentPage.value,
  ]);

  // Fetch queue stats on mount and auto-refresh every 30 seconds
  useEffect(() => {
    fetchQueueStats();
    const interval = setInterval(fetchQueueStats, 30000);
    return () => clearInterval(interval);
  }, []);

  // Get badge color based on sold volume
  const getSoldBadgeColor = (unitsSold: number | null): string => {
    if (unitsSold === null || unitsSold === 0) return "badge-ghost";
    if (unitsSold < 100) return "badge-info";
    if (unitsSold < 500) return "badge-success";
    if (unitsSold < 1000) return "badge-warning";
    return "badge-error"; // High volume (1000+)
  };

  // Handle sort column click
  const handleSort = (column: SortBy) => {
    if (sortBy.value === column) {
      // Toggle sort order
      sortOrder.value = sortOrder.value === "asc" ? "desc" : "asc";
    } else {
      // New column, default to descending
      sortBy.value = column;
      sortOrder.value = "desc";
    }
    currentPage.value = 1; // Reset to first page
  };

  // Sort icon component
  const SortIcon = ({ column }: { column: SortBy }) => {
    if (sortBy.value !== column) {
      return <span class="opacity-30">↕</span>;
    }
    return <span>{sortOrder.value === "asc" ? "↑" : "↓"}</span>;
  };

  // Pagination controls
  const handlePrevPage = () => {
    if (pagination.value?.hasPrevPage) {
      currentPage.value -= 1;
    }
  };

  const handleNextPage = () => {
    if (pagination.value?.hasNextPage) {
      currentPage.value += 1;
    }
  };

  const handlePageClick = (page: number) => {
    currentPage.value = page;
  };

  // Generate page numbers for pagination
  const pageNumbers = useComputed(() => {
    if (!pagination.value) return [];
    const { page, totalPages } = pagination.value;
    const pages: number[] = [];
    const maxVisible = 7;

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Always show first page
      pages.push(1);

      const start = Math.max(2, page - 2);
      const end = Math.min(totalPages - 1, page + 2);

      if (start > 2) {
        pages.push(-1); // Ellipsis
      }

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (end < totalPages - 1) {
        pages.push(-1); // Ellipsis
      }

      // Always show last page
      pages.push(totalPages);
    }

    return pages;
  });

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        {/* Queue Health Banner */}
        <QueueHealthBanner
          stats={queueStats}
          isLoading={isLoadingQueue}
          onRefresh={fetchQueueStats}
        />

        {/* Header with Add Button */}
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-xl font-semibold">Products</h2>
          <button
            class="btn btn-primary btn-sm"
            onClick={() => showAddModal.value = true}
          >
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
                d="M12 4v16m8-8H4"
              />
            </svg>
            Add Product
          </button>
        </div>

        {/* Filters */}
        <div class="flex flex-col lg:flex-row gap-4 mb-6">
          <div class="form-control flex-1">
            <label class="label">
              <span class="label-text">Search by name</span>
            </label>
            <input
              type="text"
              placeholder="Search products..."
              class="input input-bordered w-full"
              value={searchQuery.value}
              onInput={(e) =>
                searchQuery.value = (e.target as HTMLInputElement).value}
            />
          </div>
          <div class="form-control flex-1">
            <label class="label">
              <span class="label-text">LEGO Set Number</span>
            </label>
            <input
              type="text"
              placeholder="e.g., 75192"
              class="input input-bordered w-full"
              value={legoSetFilter.value}
              onInput={(e) =>
                legoSetFilter.value = (e.target as HTMLInputElement).value}
            />
          </div>
          <div class="form-control flex-1">
            <label class="label">
              <span class="label-text">Platform</span>
            </label>
            <select
              class="select select-bordered w-full"
              value={sourceFilter.value}
              onChange={(e) => {
                sourceFilter.value = (e.target as HTMLSelectElement).value as
                  | ProductSource
                  | "all";
                currentPage.value = 1;
              }}
            >
              <option value="all">All Platforms</option>
              <option value="shopee">Shopee</option>
              <option value="toysrus">Toys"R"Us</option>
              <option value="self">Manual Entry</option>
            </select>
          </div>
        </div>

        {/* Error state */}
        {error.value && (
          <div class="alert alert-error mb-4">
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

        {/* Loading state */}
        {isLoading.value && (
          <div class="flex justify-center items-center py-12">
            <span class="loading loading-spinner loading-lg"></span>
          </div>
        )}

        {/* Results info */}
        {!isLoading.value && pagination.value && (
          <div class="text-sm text-base-content/70 mb-4">
            Showing {items.value.length > 0
              ? ((pagination.value.page - 1) * pagination.value.limit + 1)
              : 0} to {Math.min(
                pagination.value.page * pagination.value.limit,
                pagination.value.totalCount,
              )} of {pagination.value.totalCount} products
          </div>
        )}

        {/* Table */}
        {!isLoading.value && items.value.length > 0 && (
          <div class="overflow-x-auto">
            <table class="table table-zebra w-full">
              <thead>
                <tr>
                  <th class="w-20">Platform</th>
                  <th class="w-20">Image</th>
                  <th>Name</th>
                  <th class="w-24">LEGO Set</th>
                  <th class="w-24">BL Data</th>
                  <th
                    class="cursor-pointer hover:bg-base-200 w-28"
                    onClick={() => handleSort("price")}
                  >
                    Price <SortIcon column="price" />
                  </th>
                  {sourceFilter.value !== "toysrus" && (
                    <th
                      class="cursor-pointer hover:bg-base-200 w-24"
                      onClick={() => handleSort("sold")}
                    >
                      Sold <SortIcon column="sold" />
                    </th>
                  )}
                  <th>
                    {sourceFilter.value === "toysrus" ? "SKU" : "Shop"}
                  </th>
                  <th
                    class="cursor-pointer hover:bg-base-200 w-32"
                    onClick={() => handleSort("updatedAt")}
                  >
                    Updated <SortIcon column="updatedAt" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.value.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span
                        class={`badge badge-sm ${
                          item.source === "shopee"
                            ? "badge-primary"
                            : item.source === "toysrus"
                            ? "badge-secondary"
                            : "badge-accent"
                        }`}
                      >
                        {item.source === "shopee"
                          ? "Shopee"
                          : item.source === "toysrus"
                          ? 'Toys"R"Us'
                          : "Manual"}
                      </span>
                    </td>
                    <td>
                      {item.image
                        ? (
                          <div class="avatar">
                            <div class="w-16 rounded">
                              <img
                                src={item.image}
                                alt={item.name || "Product"}
                                loading="lazy"
                              />
                            </div>
                          </div>
                        )
                        : (
                          <div class="w-16 h-16 bg-base-300 rounded flex items-center justify-center">
                            <span class="text-xs text-base-content/50">
                              No image
                            </span>
                          </div>
                        )}
                    </td>
                    <td class="max-w-xs">
                      <a
                        href={`/products/${item.productId}`}
                        class="font-medium line-clamp-2 link link-hover text-primary"
                      >
                        {item.name || "Unnamed product"}
                      </a>
                      {item.brand && (
                        <div class="text-xs text-base-content/60 mt-1">
                          {item.brand}
                        </div>
                      )}
                    </td>
                    <td>
                      {item.legoSetNumber
                        ? (
                          <span class="badge badge-primary">
                            {item.legoSetNumber}
                          </span>
                        )
                        : <span class="text-base-content/50">—</span>}
                    </td>
                    <td>
                      <div class="font-semibold">{formatPrice(item.price)}</div>
                      {item.priceBeforeDiscount &&
                        item.priceBeforeDiscount > (item.price || 0) && (
                        <div class="text-xs text-base-content/50 line-through">
                          {formatPrice(item.priceBeforeDiscount)}
                        </div>
                      )}
                    </td>
                    {sourceFilter.value !== "toysrus" && (
                      <td>
                        <span
                          class={`badge ${getSoldBadgeColor(item.unitsSold)}`}
                        >
                          {formatNumber(item.unitsSold)}
                        </span>
                      </td>
                    )}
                    <td>
                      {item.source === "shopee"
                        ? (
                          <>
                            <div class="text-sm">
                              {item.shopName || "Unknown"}
                            </div>
                            {item.shopLocation && (
                              <div class="text-xs text-base-content/50">
                                {item.shopLocation}
                              </div>
                            )}
                          </>
                        )
                        : (
                          <div class="text-sm font-mono">
                            {item.sku || "—"}
                          </div>
                        )}
                    </td>
                    <td class="text-sm text-base-content/70">
                      {formatDate(item.updatedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty state */}
        {!isLoading.value && items.value.length === 0 && (
          <div class="text-center py-12">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-16 w-16 mx-auto text-base-content/30"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
              />
            </svg>
            <p class="text-lg text-base-content/70 mt-4">No products found</p>
            <p class="text-sm text-base-content/50 mt-2">
              {debouncedSearch.value || legoSetFilter.value ||
                  sourceFilter.value !== "all"
                ? "Try adjusting your search or filters"
                : "Start by adding some products using the parser"}
            </p>
          </div>
        )}

        {/* Pagination */}
        {!isLoading.value && pagination.value &&
          pagination.value.totalPages > 1 && (
          <div class="flex justify-center items-center gap-2 mt-6">
            <button
              class="btn btn-sm"
              onClick={handlePrevPage}
              disabled={!pagination.value.hasPrevPage}
            >
              « Prev
            </button>

            <div class="join">
              {pageNumbers.value.map((pageNum, idx) => {
                if (pageNum === -1) {
                  return (
                    <button
                      key={`ellipsis-${idx}`}
                      class="join-item btn btn-sm btn-disabled"
                    >
                      ...
                    </button>
                  );
                }
                return (
                  <button
                    key={pageNum}
                    class={`join-item btn btn-sm ${
                      currentPage.value === pageNum ? "btn-active" : ""
                    }`}
                    onClick={() => handlePageClick(pageNum)}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>

            <button
              class="btn btn-sm"
              onClick={handleNextPage}
              disabled={!pagination.value.hasNextPage}
            >
              Next »
            </button>
          </div>
        )}

        {/* Add Product Modal */}
        {showAddModal.value && (
          <div class="modal modal-open">
            <div class="modal-box">
              <h3 class="font-bold text-lg mb-4">Add LEGO Product Manually</h3>

              <div class="form-control">
                <label class="label">
                  <span class="label-text">
                    LEGO Set Number (5 digits)
                  </span>
                </label>
                <input
                  type="text"
                  placeholder="e.g., 75192"
                  class="input input-bordered w-full"
                  value={addLegoSetNumber.value}
                  onInput={(e) =>
                    addLegoSetNumber.value =
                      (e.target as HTMLInputElement).value}
                  disabled={isAdding.value}
                  maxLength={5}
                />
                <label class="label">
                  <span class="label-text-alt text-base-content/60">
                    Data will be scraped from Bricklink (takes 10-30 seconds)
                  </span>
                </label>
              </div>

              {/* Error message */}
              {addError.value && (
                <div class="alert alert-error mt-4">
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
                  <span>{addError.value}</span>
                </div>
              )}

              {/* Success message */}
              {addSuccess.value && (
                <div class="alert alert-success mt-4">
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
                  <span>{addSuccess.value}</span>
                </div>
              )}

              <div class="modal-action">
                <button
                  class="btn btn-ghost"
                  onClick={handleCloseModal}
                  disabled={isAdding.value}
                >
                  Cancel
                </button>
                <button
                  class="btn btn-primary"
                  onClick={handleAddProduct}
                  disabled={isAdding.value}
                >
                  {isAdding.value && (
                    <span class="loading loading-spinner"></span>
                  )}
                  {isAdding.value ? "Adding..." : "Add Product"}
                </button>
              </div>
            </div>
            <div class="modal-backdrop" onClick={handleCloseModal}></div>
          </div>
        )}
      </div>
    </div>
  );
}

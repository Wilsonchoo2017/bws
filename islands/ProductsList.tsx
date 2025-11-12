import { useComputed, useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { formatDate, formatNumber, formatPrice } from "../utils/formatters.ts";
import { PAGINATION } from "../constants/app-config.ts";

interface ShopeeItem {
  id: number;
  productId: string | null;
  name: string | null;
  brand: string | null;
  currency: string | null;
  price: number | null;
  priceMin: number | null;
  priceMax: number | null;
  priceBeforeDiscount: number | null;
  sold: number | null;
  historical_sold: number | null;
  liked_count: number | null;
  cmt_count: number | null;
  view_count: number | null;
  itemRatingStarRating: number | null;
  itemRatingRatingCount: number[] | null;
  stockInfoSummary: string | null;
  stockInfoStockType: number | null;
  stockInfoCurrentStock: number | null;
  isAdult: boolean | null;
  isMart: boolean | null;
  isPreferred: boolean | null;
  isServiceByShopee: boolean | null;
  image: string | null;
  images: string[] | null;
  shopId: number | null;
  shopName: string | null;
  shopLocation: string | null;
  legoSetNumber: string | null;
  rawData: unknown | null;
  createdAt: Date | null;
  updatedAt: Date | null;
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
  items: ShopeeItem[];
  pagination: Pagination;
}

type SortBy = "price" | "sold" | "createdAt" | "updatedAt";
type SortOrder = "asc" | "desc";

export default function ProductsList() {
  const items = useSignal<ShopeeItem[]>([]);
  const pagination = useSignal<Pagination | null>(null);
  const isLoading = useSignal(false);
  const error = useSignal<string | null>(null);

  // Filter and sort state
  const searchQuery = useSignal("");
  const legoSetFilter = useSignal("");
  const sortBy = useSignal<SortBy>("updatedAt");
  const sortOrder = useSignal<SortOrder>("desc");
  const currentPage = useSignal(1);

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

  // Fetch on mount and when dependencies change
  useEffect(() => {
    fetchProducts();
  }, [
    debouncedSearch.value,
    legoSetFilter.value,
    sortBy.value,
    sortOrder.value,
    currentPage.value,
  ]);

  // Get badge color based on sold volume
  const getSoldBadgeColor = (sold: number | null): string => {
    if (sold === null || sold === 0) return "badge-ghost";
    if (sold < 100) return "badge-info";
    if (sold < 500) return "badge-success";
    if (sold < 1000) return "badge-warning";
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
                  <th class="w-20">Image</th>
                  <th>Name</th>
                  <th class="w-24">LEGO Set</th>
                  <th
                    class="cursor-pointer hover:bg-base-200 w-28"
                    onClick={() => handleSort("price")}
                  >
                    Price <SortIcon column="price" />
                  </th>
                  <th
                    class="cursor-pointer hover:bg-base-200 w-24"
                    onClick={() => handleSort("sold")}
                  >
                    Sold <SortIcon column="sold" />
                  </th>
                  <th>Shop</th>
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
                      <div class="font-medium line-clamp-2">
                        {item.name || "Unnamed product"}
                      </div>
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
                    <td>
                      <span class={`badge ${getSoldBadgeColor(item.sold)}`}>
                        {formatNumber(item.sold)}
                      </span>
                    </td>
                    <td>
                      <div class="text-sm">{item.shopName || "Unknown"}</div>
                      {item.shopLocation && (
                        <div class="text-xs text-base-content/50">
                          {item.shopLocation}
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
              {debouncedSearch.value || legoSetFilter.value
                ? "Try adjusting your search or filters"
                : "Start by adding some products using the Shopee Parser"}
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
      </div>
    </div>
  );
}

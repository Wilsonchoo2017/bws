import { ProductTableRow } from "./ProductTableRow.tsx";
import type { Pagination, Product } from "../../hooks/useProductList.ts";
import type { ProductSource } from "../../db/schema.ts";
import type { SortBy, SortOrder } from "../../hooks/useProductFilters.ts";

interface ProductTableProps {
  items: Product[];
  pagination: Pagination | null;
  isLoading: boolean;
  error: string | null;
  sourceFilter: ProductSource | "all";
  sortBy: SortBy;
  sortOrder: SortOrder;
  debouncedSearch: string;
  legoSetFilter: string;
  onSort: (column: SortBy) => void;
}

interface SortIconProps {
  column: SortBy;
  currentSortBy: SortBy;
  currentSortOrder: SortOrder;
}

/**
 * Sort indicator icon component.
 * Shows current sort direction or neutral state.
 */
function SortIcon({ column, currentSortBy, currentSortOrder }: SortIconProps) {
  if (currentSortBy !== column) {
    return <span class="opacity-30">↕</span>;
  }
  return <span>{currentSortOrder === "asc" ? "↑" : "↓"}</span>;
}

/**
 * Product table component with sortable columns.
 * Displays products in a table with loading, error, and empty states.
 * Follows Single Responsibility Principle - only handles table display logic.
 */
export function ProductTable({
  items,
  pagination,
  isLoading,
  error,
  sourceFilter,
  sortBy,
  sortOrder,
  debouncedSearch,
  legoSetFilter,
  onSort,
}: ProductTableProps) {
  // Error state
  if (error) {
    return (
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
        <span>{error}</span>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div class="flex justify-center items-center py-12">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Empty state
  if (items.length === 0) {
    return (
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
          {debouncedSearch || legoSetFilter || sourceFilter !== "all"
            ? "Try adjusting your search or filters"
            : "Start by adding some products using the parser"}
        </p>
      </div>
    );
  }

  // Results info
  const resultsInfo = pagination && (
    <div class="text-sm text-base-content/70 mb-4">
      Showing{" "}
      {items.length > 0 ? ((pagination.page - 1) * pagination.limit + 1) : 0} to
      {" "}
      {Math.min(
        pagination.page * pagination.limit,
        pagination.totalCount,
      )} of {pagination.totalCount} products
    </div>
  );

  return (
    <>
      {resultsInfo}

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
                onClick={() => onSort("price")}
              >
                Price{" "}
                <SortIcon
                  column="price"
                  currentSortBy={sortBy}
                  currentSortOrder={sortOrder}
                />
              </th>
              {sourceFilter !== "toysrus" && (
                <th
                  class="cursor-pointer hover:bg-base-200 w-24"
                  onClick={() => onSort("sold")}
                >
                  Sold{" "}
                  <SortIcon
                    column="sold"
                    currentSortBy={sortBy}
                    currentSortOrder={sortOrder}
                  />
                </th>
              )}
              <th>
                {sourceFilter === "toysrus" ? "SKU" : "Shop"}
              </th>
              <th
                class="cursor-pointer hover:bg-base-200 w-32"
                onClick={() => onSort("updatedAt")}
              >
                Updated{" "}
                <SortIcon
                  column="updatedAt"
                  currentSortBy={sortBy}
                  currentSortOrder={sortOrder}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <ProductTableRow
                key={item.id}
                product={item}
                sourceFilter={sourceFilter}
              />
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

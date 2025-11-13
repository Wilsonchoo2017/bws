import { useProductFilters } from "../hooks/useProductFilters.ts";
import { useProductList } from "../hooks/useProductList.ts";
import { useAddProduct } from "../hooks/useAddProduct.ts";
import { ProductFilters } from "../components/products/ProductFilters.tsx";
import { ProductTable } from "../components/products/ProductTable.tsx";
import { PaginationControls } from "../components/products/PaginationControls.tsx";
import { AddProductModal } from "../components/products/AddProductModal.tsx";

/**
 * ProductsList island component.
 * Main container for the products list page with filters, table, and pagination.
 *
 * Refactored to follow SOLID principles:
 * - Single Responsibility: Orchestrates child components and hooks
 * - Open/Closed: Easy to extend with new filters or columns by modifying child components
 * - Dependency Inversion: Depends on hook abstractions rather than concrete implementations
 *
 * Reduced from 828 lines to ~80 lines by extracting:
 * - 3 custom hooks (useProductFilters, useProductList, useAddProduct)
 * - 5 presentational components (ProductFilters, ProductTable, ProductTableRow, PaginationControls, AddProductModal)
 * - 1 utility module (product-helpers)
 */
export default function ProductsList() {
  // Custom hooks for state management
  const { filters, actions: filterActions } = useProductFilters();

  const {
    items,
    pagination,
    isLoading,
    error,
    currentPage,
    setCurrentPage,
    refresh,
  } = useProductList({
    debouncedSearch: filters.debouncedSearch,
    legoSetFilter: filters.legoSetFilter,
    sourceFilter: filters.sourceFilter,
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
  });

  const { state: addProductState, actions: addProductActions } = useAddProduct(
    refresh,
  );

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        {/* Header with Add Button */}
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-xl font-semibold">Products</h2>
          <button
            class="btn btn-primary btn-sm"
            onClick={addProductActions.openModal}
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
        <ProductFilters
          searchQuery={filters.searchQuery}
          legoSetFilter={filters.legoSetFilter}
          sourceFilter={filters.sourceFilter}
          onSearchChange={filterActions.setSearchQuery}
          onLegoSetChange={filterActions.setLegoSetFilter}
          onSourceChange={filterActions.setSourceFilter}
        />

        {/* Table with loading, error, and empty states */}
        <ProductTable
          items={items}
          pagination={pagination}
          isLoading={isLoading}
          error={error}
          sourceFilter={filters.sourceFilter}
          sortBy={filters.sortBy}
          sortOrder={filters.sortOrder}
          debouncedSearch={filters.debouncedSearch}
          legoSetFilter={filters.legoSetFilter}
          onSort={filterActions.handleSort}
        />

        {/* Pagination */}
        <PaginationControls
          pagination={pagination}
          currentPage={currentPage}
          onPageChange={setCurrentPage}
        />

        {/* Add Product Modal */}
        <AddProductModal
          showModal={addProductState.showModal}
          legoSetNumber={addProductState.legoSetNumber}
          isAdding={addProductState.isAdding}
          error={addProductState.error}
          success={addProductState.success}
          onClose={addProductActions.closeModal}
          onLegoSetNumberChange={addProductActions.setLegoSetNumber}
          onSubmit={addProductActions.submitProduct}
        />
      </div>
    </div>
  );
}

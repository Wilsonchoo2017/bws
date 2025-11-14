import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { useVoucherFilters } from "../hooks/useVoucherFilters.ts";
import { useVoucherList, type Voucher } from "../hooks/useVoucherList.ts";
import { useVoucherForm } from "../hooks/useVoucherForm.ts";
import { VoucherFilters } from "../components/vouchers/VoucherFilters.tsx";
import { VoucherTable } from "../components/vouchers/VoucherTable.tsx";
import { PaginationControls } from "../components/products/PaginationControls.tsx";
import VoucherEditModal from "./VoucherEditModal.tsx";

interface ProductTag {
  id: string;
  name: string;
  endDate: string | null;
  isExpired?: boolean;
}

/**
 * VouchersList island component.
 * Main container for the vouchers list page with filters, table, and pagination.
 *
 * Follows SOLID principles:
 * - Single Responsibility: Orchestrates child components and hooks
 * - Open/Closed: Easy to extend with new filters or features
 * - Dependency Inversion: Depends on hook abstractions
 */
export default function VouchersList() {
  // Custom hooks for state management
  const { filters, actions: filterActions } = useVoucherFilters();
  const voucherForm = useVoucherForm();

  const {
    items,
    pagination,
    isLoading,
    error,
    currentPage,
    setCurrentPage,
    refresh,
  } = useVoucherList({
    search: filters.debouncedSearch,
    status: filters.statusFilter,
    platform: filters.platformFilter,
    tagId: filters.tagFilter,
  });

  // Tag management state
  const availableTags = useSignal<ProductTag[]>([]);
  const isModalOpen = useSignal(false);

  // Load tags on mount
  useEffect(() => {
    loadTags();
  }, []);

  const loadTags = async () => {
    try {
      const response = await fetch("/api/tags");
      if (response.ok) {
        const tags = await response.json();
        availableTags.value = tags;
      }
    } catch (err) {
      console.error("Failed to load tags:", err);
    }
  };

  const handleCreateNew = () => {
    voucherForm.actions.resetForm();
    isModalOpen.value = true;
  };

  const handleEdit = (voucher: Voucher) => {
    voucherForm.actions.loadVoucher(voucher);
    isModalOpen.value = true;
  };

  const handleDuplicate = (voucher: Voucher) => {
    voucherForm.actions.duplicateVoucher(voucher);
    isModalOpen.value = true;
  };

  const handleDelete = async (voucher: Voucher) => {
    if (!confirm(`Are you sure you want to delete "${voucher.name}"?`)) {
      return;
    }

    try {
      const response = await fetch(`/api/vouchers?id=${voucher.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Failed to delete voucher");
      }

      refresh();
    } catch (err) {
      console.error("Error deleting voucher:", err);
      alert(err instanceof Error ? err.message : "Failed to delete voucher");
    }
  };

  const handleSave = async (payload: Record<string, unknown>) => {
    const method = voucherForm.isEditing ? "PUT" : "POST";

    const response = await fetch("/api/vouchers", {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Failed to save voucher");
    }

    refresh();
  };

  const handleModalClose = () => {
    isModalOpen.value = false;
    voucherForm.actions.resetForm();
  };

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        {/* Header with Add Button */}
        <div class="flex justify-between items-center mb-4">
          <h2 class="card-title text-2xl">Vouchers</h2>
          <button
            class="btn btn-primary"
            onClick={handleCreateNew}
          >
            + Add Voucher
          </button>
        </div>

        {/* Filters */}
        <VoucherFilters
          searchQuery={filters.searchQuery}
          statusFilter={filters.statusFilter}
          platformFilter={filters.platformFilter}
          tagFilter={filters.tagFilter}
          availableTags={availableTags.value}
          onSearchChange={filterActions.setSearchQuery}
          onStatusChange={filterActions.setStatusFilter}
          onPlatformChange={filterActions.setPlatformFilter}
          onTagFilterChange={filterActions.setTagFilter}
        />

        {/* Vouchers Table */}
        <VoucherTable
          items={items}
          pagination={pagination}
          isLoading={isLoading}
          error={error}
          onEdit={handleEdit}
          onDuplicate={handleDuplicate}
          onDelete={handleDelete}
        />

        {/* Pagination */}
        {pagination && pagination.totalPages > 1 && (
          <PaginationControls
            pagination={pagination}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
          />
        )}

        {/* Edit/Create Modal */}
        <VoucherEditModal
          isOpen={isModalOpen.value}
          availableTags={availableTags.value}
          voucherForm={voucherForm}
          onClose={handleModalClose}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}

import { VoucherTableRow } from "./VoucherTableRow.tsx";
import type { Pagination, Voucher } from "../../hooks/useVoucherList.ts";

interface VoucherTableProps {
  items: Voucher[];
  pagination: Pagination | null;
  isLoading: boolean;
  error: string | null;
  onEdit: (voucher: Voucher) => void;
  onDuplicate: (voucher: Voucher) => void;
  onDelete: (voucher: Voucher) => void;
}

/**
 * Voucher table component.
 * Displays vouchers in a table with loading, error, and empty states.
 * Follows Single Responsibility Principle - only handles table display logic.
 */
export function VoucherTable({
  items,
  pagination,
  isLoading,
  error,
  onEdit,
  onDuplicate,
  onDelete,
}: VoucherTableProps) {
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
        <span>Error: {error}</span>
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
  if (!items || items.length === 0) {
    return (
      <div class="text-center py-12">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-16 w-16 mx-auto mb-4 opacity-20"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2zM10 8.5a.5.5 0 11-1 0 .5.5 0 011 0zm5 5a.5.5 0 11-1 0 .5.5 0 011 0z"
          />
        </svg>
        <p class="text-xl text-gray-500">No vouchers found</p>
        <p class="text-sm text-gray-400 mt-2">
          Try adjusting your filters or create a new voucher
        </p>
      </div>
    );
  }

  return (
    <div class="overflow-x-auto">
      <table class="table table-zebra">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type & Status</th>
            <th>Discount</th>
            <th>Min Purchase</th>
            <th>Platform/Shop</th>
            <th>Date Range</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((voucher) => (
            <VoucherTableRow
              key={voucher.id}
              voucher={voucher}
              onEdit={onEdit}
              onDuplicate={onDuplicate}
              onDelete={onDelete}
            />
          ))}
        </tbody>
      </table>

      {/* Pagination info */}
      {pagination && (
        <div class="mt-4 text-sm text-gray-500 text-center">
          Showing {items.length} of {pagination.totalCount} vouchers
        </div>
      )}
    </div>
  );
}

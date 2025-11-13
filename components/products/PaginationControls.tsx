import { useComputed } from "@preact/signals";
import type { Pagination } from "../../hooks/useProductList.ts";

interface PaginationControlsProps {
  pagination: Pagination | null;
  currentPage: number;
  onPageChange: (page: number) => void;
}

/**
 * Generates page numbers for pagination with ellipsis support.
 * Shows first page, last page, and pages around current page.
 */
function generatePageNumbers(
  currentPage: number,
  totalPages: number,
): number[] {
  const pages: number[] = [];
  const maxVisible = 7;

  if (totalPages <= maxVisible) {
    for (let i = 1; i <= totalPages; i++) {
      pages.push(i);
    }
  } else {
    // Always show first page
    pages.push(1);

    const start = Math.max(2, currentPage - 2);
    const end = Math.min(totalPages - 1, currentPage + 2);

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
}

/**
 * Pagination controls component.
 * Displays page numbers with prev/next buttons and ellipsis for large page counts.
 * Follows Single Responsibility Principle - only handles pagination UI.
 */
export function PaginationControls({
  pagination,
  currentPage,
  onPageChange,
}: PaginationControlsProps) {
  // Don't render if no pagination or only one page
  if (!pagination || pagination.totalPages <= 1) {
    return null;
  }

  const pageNumbers = useComputed(() => {
    return generatePageNumbers(currentPage, pagination.totalPages);
  });

  const handlePrevPage = () => {
    if (pagination.hasPrevPage) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNextPage = () => {
    if (pagination.hasNextPage) {
      onPageChange(currentPage + 1);
    }
  };

  return (
    <div class="flex justify-center items-center gap-2 mt-6">
      <button
        class="btn btn-sm"
        onClick={handlePrevPage}
        disabled={!pagination.hasPrevPage}
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
                currentPage === pageNum ? "btn-active" : ""
              }`}
              onClick={() => onPageChange(pageNum)}
            >
              {pageNum}
            </button>
          );
        })}
      </div>

      <button
        class="btn btn-sm"
        onClick={handleNextPage}
        disabled={!pagination.hasNextPage}
      >
        Next »
      </button>
    </div>
  );
}

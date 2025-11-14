import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { PAGINATION } from "../constants/app-config.ts";

export type VoucherStatus = "active" | "soon" | "expired" | "all";

export interface Voucher {
  id: string;
  name: string;
  description: string | null;
  voucherType: "platform" | "shop" | "item_tag";
  discountType: "percentage" | "fixed";
  discountValue: number; // Cents or percentage * 100
  platform: string | null;
  shopId: number | null;
  shopName: string | null;
  minPurchase: number | null; // Cents
  maxDiscount: number | null; // Cents
  requiredTagIds: string[] | null; // Array of tag UUIDs
  tieredDiscounts: { minSpend: number; discount: number }[] | null;
  isActive: boolean;
  startDate: string | null;
  endDate: string | null;
  createdAt: string;
  updatedAt: string;
  status?: "active" | "soon" | "expired" | "inactive"; // Computed by API
}

export interface Pagination {
  page: number;
  limit: number;
  totalCount: number;
  totalPages: number;
  hasNextPage: boolean;
  hasPrevPage: boolean;
}

interface ApiResponse {
  items: Voucher[];
  pagination: Pagination;
}

export interface VoucherListFilters {
  search: string;
  status: VoucherStatus;
  platform: string;
  tagId: string | null;
}

export interface UseVoucherListReturn {
  items: Voucher[];
  pagination: Pagination | null;
  isLoading: boolean;
  error: string | null;
  currentPage: number;
  setCurrentPage: (page: number) => void;
  refresh: () => void;
}

/**
 * Custom hook for managing voucher list data fetching and pagination.
 * Handles API calls, loading states, and pagination logic.
 */
export function useVoucherList(
  filters: VoucherListFilters,
): UseVoucherListReturn {
  const items = useSignal<Voucher[]>([]);
  const pagination = useSignal<Pagination | null>(null);
  const isLoading = useSignal(false);
  const error = useSignal<string | null>(null);
  const currentPage = useSignal(1);

  // Reset to first page when filters change
  useEffect(() => {
    currentPage.value = 1;
  }, [
    filters.search,
    filters.status,
    filters.platform,
    filters.tagId,
  ]);

  const fetchVouchers = async () => {
    isLoading.value = true;
    error.value = null;

    try {
      const params = new URLSearchParams({
        page: currentPage.value.toString(),
        limit: PAGINATION.DEFAULT_LIMIT.toString(),
      });

      if (filters.search.trim()) {
        params.set("search", filters.search.trim());
      }

      if (filters.status !== "all") {
        params.set("status", filters.status);
      }

      if (filters.platform && filters.platform !== "all") {
        params.set("platform", filters.platform);
      }

      if (filters.tagId) {
        params.set("tagId", filters.tagId);
      }

      const response = await fetch(`/api/vouchers?${params}`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ApiResponse = await response.json();
      items.value = data.items;
      pagination.value = data.pagination;
    } catch (err) {
      error.value = err instanceof Error
        ? err.message
        : "Failed to fetch vouchers";
      console.error("Error fetching vouchers:", err);
    } finally {
      isLoading.value = false;
    }
  };

  // Fetch on mount and when dependencies change
  useEffect(() => {
    fetchVouchers();
  }, [
    filters.search,
    filters.status,
    filters.platform,
    filters.tagId,
    currentPage.value,
  ]);

  const setCurrentPage = (page: number) => {
    currentPage.value = page;
  };

  const refresh = () => {
    fetchVouchers();
  };

  return {
    items: items.value,
    pagination: pagination.value,
    isLoading: isLoading.value,
    error: error.value,
    currentPage: currentPage.value,
    setCurrentPage,
    refresh,
  };
}

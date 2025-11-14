import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { VoucherStatus } from "./useVoucherList.ts";

export interface VoucherFiltersState {
  searchQuery: string;
  statusFilter: VoucherStatus;
  platformFilter: string;
  tagFilter: string | null;
  debouncedSearch: string;
}

export interface VoucherFiltersActions {
  setSearchQuery: (value: string) => void;
  setStatusFilter: (value: VoucherStatus) => void;
  setPlatformFilter: (value: string) => void;
  setTagFilter: (value: string | null) => void;
  resetFilters: () => void;
}

export interface UseVoucherFiltersReturn {
  filters: VoucherFiltersState;
  actions: VoucherFiltersActions;
}

/**
 * Custom hook for managing voucher filter state and logic.
 * Handles search, status filtering, platform filtering, and tag filtering.
 * Includes debounce logic for search input.
 */
export function useVoucherFilters(): UseVoucherFiltersReturn {
  const searchQuery = useSignal("");
  const statusFilter = useSignal<VoucherStatus>("all");
  const platformFilter = useSignal<string>("all");
  const tagFilter = useSignal<string | null>(null);
  const debouncedSearch = useSignal("");

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      debouncedSearch.value = searchQuery.value;
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery.value]);

  const setSearchQuery = (value: string) => {
    searchQuery.value = value;
  };

  const setStatusFilter = (value: VoucherStatus) => {
    statusFilter.value = value;
  };

  const setPlatformFilter = (value: string) => {
    platformFilter.value = value;
  };

  const setTagFilter = (value: string | null) => {
    tagFilter.value = value;
  };

  const resetFilters = () => {
    searchQuery.value = "";
    statusFilter.value = "all";
    platformFilter.value = "all";
    tagFilter.value = null;
  };

  return {
    filters: {
      searchQuery: searchQuery.value,
      statusFilter: statusFilter.value,
      platformFilter: platformFilter.value,
      tagFilter: tagFilter.value,
      debouncedSearch: debouncedSearch.value,
    },
    actions: {
      setSearchQuery,
      setStatusFilter,
      setPlatformFilter,
      setTagFilter,
      resetFilters,
    },
  };
}

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { ProductSource } from "../db/schema.ts";

export type SortBy = "price" | "sold" | "createdAt" | "updatedAt";
export type SortOrder = "asc" | "desc";

export interface ProductFiltersState {
  searchQuery: string;
  legoSetFilter: string;
  sourceFilter: ProductSource | "all";
  sortBy: SortBy;
  sortOrder: SortOrder;
  debouncedSearch: string;
}

export interface ProductFiltersActions {
  setSearchQuery: (value: string) => void;
  setLegoSetFilter: (value: string) => void;
  setSourceFilter: (value: ProductSource | "all") => void;
  handleSort: (column: SortBy) => void;
  resetFilters: () => void;
}

export interface UseProductFiltersReturn {
  filters: ProductFiltersState;
  actions: ProductFiltersActions;
}

/**
 * Custom hook for managing product filter state and logic.
 * Handles search, LEGO set filtering, platform filtering, and sorting.
 * Includes debounce logic for search input.
 */
export function useProductFilters(): UseProductFiltersReturn {
  const searchQuery = useSignal("");
  const legoSetFilter = useSignal("");
  const sourceFilter = useSignal<ProductSource | "all">("all");
  const sortBy = useSignal<SortBy>("updatedAt");
  const sortOrder = useSignal<SortOrder>("desc");
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

  const setLegoSetFilter = (value: string) => {
    legoSetFilter.value = value;
  };

  const setSourceFilter = (value: ProductSource | "all") => {
    sourceFilter.value = value;
  };

  const handleSort = (column: SortBy) => {
    if (sortBy.value === column) {
      // Toggle sort order
      sortOrder.value = sortOrder.value === "asc" ? "desc" : "asc";
    } else {
      // New column, default to descending
      sortBy.value = column;
      sortOrder.value = "desc";
    }
  };

  const resetFilters = () => {
    searchQuery.value = "";
    legoSetFilter.value = "";
    sourceFilter.value = "all";
    sortBy.value = "updatedAt";
    sortOrder.value = "desc";
  };

  return {
    filters: {
      searchQuery: searchQuery.value,
      legoSetFilter: legoSetFilter.value,
      sourceFilter: sourceFilter.value,
      sortBy: sortBy.value,
      sortOrder: sortOrder.value,
      debouncedSearch: debouncedSearch.value,
    },
    actions: {
      setSearchQuery,
      setLegoSetFilter,
      setSourceFilter,
      handleSort,
      resetFilters,
    },
  };
}

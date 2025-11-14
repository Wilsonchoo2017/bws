import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { PAGINATION } from "../constants/app-config.ts";
import type { ProductSource } from "../db/schema.ts";
import type { SortBy, SortOrder } from "./useProductFilters.ts";

export interface Product {
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

  // LEGO data fields
  releaseYear: number | null;
  retiredYear: number | null;
  retiringSoon: boolean;
  expectedRetirementDate: string | null;
  retailPrice: number | null;

  // Data availability flags (for UI indicators)
  hasReleaseYear: boolean;
  hasRetiredYear: boolean;
  hasRetiringSoon: boolean;
  hasBricklinkData: boolean;
  hasBrickEconomyData: boolean;
  bricklinkDataStatus: "complete" | "partial" | "missing";
  bricklinkMissingBoxes: string[];
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
  items: Product[];
  pagination: Pagination;
}

export interface ProductListFilters {
  debouncedSearch: string;
  legoSetFilter: string;
  sourceFilter: ProductSource | "all";
  sortBy: SortBy;
  sortOrder: SortOrder;
}

export interface UseProductListReturn {
  items: Product[];
  pagination: Pagination | null;
  isLoading: boolean;
  error: string | null;
  currentPage: number;
  setCurrentPage: (page: number) => void;
  refresh: () => void;
}

/**
 * Custom hook for managing product list data fetching and pagination.
 * Handles API calls, loading states, and pagination logic.
 */
export function useProductList(
  filters: ProductListFilters,
): UseProductListReturn {
  const items = useSignal<Product[]>([]);
  const pagination = useSignal<Pagination | null>(null);
  const isLoading = useSignal(false);
  const error = useSignal<string | null>(null);
  const currentPage = useSignal(1);

  // Reset to first page when filters change
  useEffect(() => {
    currentPage.value = 1;
  }, [
    filters.debouncedSearch,
    filters.legoSetFilter,
    filters.sourceFilter,
  ]);

  const fetchProducts = async () => {
    isLoading.value = true;
    error.value = null;

    try {
      const params = new URLSearchParams({
        page: currentPage.value.toString(),
        limit: PAGINATION.DEFAULT_LIMIT.toString(),
        sortBy: filters.sortBy,
        sortOrder: filters.sortOrder,
      });

      if (filters.debouncedSearch.trim()) {
        params.set("search", filters.debouncedSearch.trim());
      }

      if (filters.legoSetFilter.trim()) {
        params.set("legoSetNumber", filters.legoSetFilter.trim());
      }

      if (filters.sourceFilter !== "all") {
        params.set("source", filters.sourceFilter);
      }

      const response = await fetch(`/api/products?${params}`);

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
    filters.debouncedSearch,
    filters.legoSetFilter,
    filters.sourceFilter,
    filters.sortBy,
    filters.sortOrder,
    currentPage.value,
  ]);

  const setCurrentPage = (page: number) => {
    currentPage.value = page;
  };

  const refresh = () => {
    fetchProducts();
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

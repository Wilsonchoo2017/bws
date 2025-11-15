import { useSignal } from "@preact/signals";
import { useMemo } from "preact/hooks";
import type { ValueInvestingProduct } from "../types/value-investing.ts";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import { IntrinsicValueProgressBar } from "./components/IntrinsicValueProgressBar.tsx";
import { formatCurrency, formatPercentage } from "../utils/formatters.ts";
import VoucherSelector from "./VoucherSelector.tsx";
import type { VoucherTemplate } from "../types/voucher.ts";
import type { Voucher } from "../hooks/useVoucherList.ts";
import { VoucherEnhancedCalculator } from "../services/value-investing/VoucherEnhancedCalculator.ts";
import type { VoucherEnhancedMetrics } from "../services/value-investing/VoucherEnhancedCalculator.ts";

interface ValueInvestingDashboardProps {
  products: ValueInvestingProduct[];
  availableVouchers: Voucher[];
}

export default function ValueInvestingDashboard(
  { products: initialProducts, availableVouchers }: ValueInvestingDashboardProps,
) {
  const products = useSignal<ValueInvestingProduct[]>(initialProducts);
  const minROI = useSignal<number>(0);
  const maxDistanceFromIntrinsic = useSignal<number>(50); // ±50% from intrinsic value
  const sortBy = useSignal<string>("bestValue"); // Default: furthest below intrinsic first
  const selectedVouchers = useSignal<VoucherTemplate[]>([]);
  const voucherMode = useSignal<"original" | "voucher" | "both">("both");

  /**
   * Memoized voucher-enhanced products
   * Calculates voucher-adjusted metrics for each product
   */
  const productsWithVouchers = useMemo<Array<{
    product: ValueInvestingProduct;
    voucherMetrics: VoucherEnhancedMetrics;
  }>>(() => {
    return products.value.map((product) => {
      const voucherMetrics = VoucherEnhancedCalculator.calculateVoucherEnhancedMetrics({
        productId: product.productId,
        legoSetNumber: product.legoSetNumber || undefined,
        currentPrice: product.currentPrice,
        tags: undefined, // TODO: Add tags to product data if needed
        valueMetrics: product.valueMetrics,
        selectedVouchers: selectedVouchers.value,
      });

      return {
        product,
        voucherMetrics,
      };
    });
  }, [products.value, selectedVouchers.value]);

  /**
   * Memoized filtered products computation
   * Only recalculates when dependencies change
   * Prevents expensive filtering/sorting on every render
   */
  const filteredProducts = useMemo(() => {
    let filtered = [...productsWithVouchers];

    // ROI filter (use voucher-enhanced ROI when vouchers are selected)
    if (minROI.value > 0) {
      filtered = filtered.filter(({ product, voucherMetrics }) => {
        const roiToCheck = selectedVouchers.value.length > 0
          ? voucherMetrics.voucherEnhancedROI
          : product.valueMetrics?.expectedROI ?? 0;
        return roiToCheck >= minROI.value;
      });
    }

    // Distance from intrinsic value filter
    filtered = filtered.filter(({ product, voucherMetrics }) => {
      const intrinsicValue = product.valueMetrics?.intrinsicValue ?? 0;
      if (intrinsicValue === 0) return false;

      const priceToCheck = selectedVouchers.value.length > 0
        ? voucherMetrics.voucherDiscountedPrice
        : product.currentPrice;

      const distancePercent = ((priceToCheck - intrinsicValue) / intrinsicValue) * 100;
      return Math.abs(distancePercent) <= maxDistanceFromIntrinsic.value;
    });

    // Sort products (with null safety)
    filtered.sort((a, b) => {
      switch (sortBy.value) {
        case "bestValue": {
          // Furthest below intrinsic value first (most negative distance)
          const aPrice = selectedVouchers.value.length > 0
            ? a.voucherMetrics.voucherDiscountedPrice
            : a.product.currentPrice;
          const bPrice = selectedVouchers.value.length > 0
            ? b.voucherMetrics.voucherDiscountedPrice
            : b.product.currentPrice;

          const aIntrinsic = a.product.valueMetrics?.intrinsicValue ?? 0;
          const bIntrinsic = b.product.valueMetrics?.intrinsicValue ?? 0;

          const aDistance = ((aPrice - aIntrinsic) / (aIntrinsic || 1)) * 100;
          const bDistance = ((bPrice - bIntrinsic) / (bIntrinsic || 1)) * 100;
          return aDistance - bDistance;
        }
        case "expectedROI": {
          const aROI = selectedVouchers.value.length > 0
            ? a.voucherMetrics.voucherEnhancedROI
            : a.product.valueMetrics?.expectedROI ?? 0;
          const bROI = selectedVouchers.value.length > 0
            ? b.voucherMetrics.voucherEnhancedROI
            : b.product.valueMetrics?.expectedROI ?? 0;
          return bROI - aROI;
        }
        case "price": {
          const aPrice = selectedVouchers.value.length > 0
            ? a.voucherMetrics.voucherDiscountedPrice
            : a.product.currentPrice;
          const bPrice = selectedVouchers.value.length > 0
            ? b.voucherMetrics.voucherDiscountedPrice
            : b.product.currentPrice;
          return aPrice - bPrice;
        }
        case "priceDesc": {
          const aPrice = selectedVouchers.value.length > 0
            ? a.voucherMetrics.voucherDiscountedPrice
            : a.product.currentPrice;
          const bPrice = selectedVouchers.value.length > 0
            ? b.voucherMetrics.voucherDiscountedPrice
            : b.product.currentPrice;
          return bPrice - aPrice;
        }
        default:
          return 0;
      }
    });

    return filtered;
  }, [
    productsWithVouchers,
    minROI.value,
    maxDistanceFromIntrinsic.value,
    sortBy.value,
    selectedVouchers.value,
  ]);


  return (
    <ErrorBoundary>
      <div class="space-y-6">
        {/* Header */}
        <div class="flex flex-col gap-2">
          <h1 class="text-3xl font-bold">Buy Opportunities</h1>
          <p class="text-base-content/70">
            Find products close to their intrinsic value{selectedVouchers.value.length > 0 ? " (with voucher simulation)" : ""}
          </p>
        </div>

        {/* Voucher Selector */}
        <VoucherSelector
          availableVouchers={availableVouchers}
          selectedVouchers={selectedVouchers.value}
          onSelectionChange={(vouchers) => selectedVouchers.value = vouchers}
          maxSelections={5}
        />

        {/* Filters */}
        <div class="card bg-base-100">
          <div class="card-body">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Distance from Intrinsic Filter */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text font-semibold">
                    Max Distance from Intrinsic Value
                  </span>
                  <span class="label-text-alt badge badge-primary">
                    ±{maxDistanceFromIntrinsic.value}%
                  </span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={maxDistanceFromIntrinsic.value}
                  class="range range-primary"
                  step="5"
                  onInput={(e) =>
                    maxDistanceFromIntrinsic.value = parseInt(
                      (e.target as HTMLInputElement).value,
                    )}
                />
                <div class="w-full flex justify-between text-xs px-2 opacity-60 mt-1">
                  <span>0%</span>
                  <span>±25%</span>
                  <span>±50%</span>
                  <span>±75%</span>
                  <span>±100%</span>
                </div>
              </div>

              {/* Min ROI Filter */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text font-semibold">
                    Minimum Expected ROI
                  </span>
                  <span class="label-text-alt badge badge-secondary">
                    {minROI.value}%
                  </span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={minROI.value}
                  class="range range-secondary"
                  step="5"
                  onInput={(e) =>
                    minROI.value = parseInt(
                      (e.target as HTMLInputElement).value,
                    )}
                />
                <div class="w-full flex justify-between text-xs px-2 opacity-60 mt-1">
                  <span>0%</span>
                  <span>50%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>

            <div class="flex gap-2 items-center mt-4">
              <div class="badge badge-ghost">
                {filteredProducts.length} products
              </div>
              <div class="ml-auto flex gap-2 items-center">
                <span class="text-sm opacity-70">Sort by:</span>
                <select
                  class="select select-bordered select-sm"
                  value={sortBy.value}
                  onChange={(e) =>
                    sortBy.value = (e.target as HTMLSelectElement).value}
                >
                  <option value="bestValue">
                    Best Value (Furthest Below Intrinsic)
                  </option>
                  <option value="expectedROI">Expected ROI (Highest)</option>
                  <option value="price">Price (Low to High)</option>
                  <option value="priceDesc">Price (High to Low)</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Products Table */}
        <div class="card bg-base-100">
          <div class="card-body">
            {filteredProducts.length === 0
              ? (
                <div class="alert">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    class="stroke-info shrink-0 w-6 h-6"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    >
                    </path>
                  </svg>
                  <span>
                    No products match your filters. Try adjusting your criteria.
                  </span>
                </div>
              )
              : (
                <div class="overflow-x-auto">
                  <table class="table table-zebra">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Price Comparison</th>
                        <th>Distance from Intrinsic</th>
                        <th>Expected ROI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProducts.map(({ product, voucherMetrics }) => {
                        const hasVouchers = selectedVouchers.value.length > 0;
                        const showBothPrices = hasVouchers && voucherMode.value === "both";
                        const useVoucherPrice = hasVouchers && (voucherMode.value === "voucher" || voucherMode.value === "both");

                        return (
                          <tr key={product.id} class="hover">
                            <td>
                              <div class="flex items-center gap-3">
                                <div class="avatar">
                                  <div class="mask mask-squircle w-12 h-12">
                                    <img
                                      src={product.image}
                                      alt={product.name}
                                    />
                                  </div>
                                </div>
                                <div>
                                  <div class="font-bold text-sm line-clamp-1">
                                    {product.name}
                                  </div>
                                  <div class="text-xs opacity-50">
                                    {product.legoSetNumber || product.productId}
                                  </div>
                                  {voucherMetrics.worthItWithVoucher && (
                                    <div class="badge badge-success badge-xs mt-1">
                                      Good deal with vouchers!
                                    </div>
                                  )}
                                </div>
                              </div>
                            </td>
                            <td>
                              <div class="flex flex-col gap-1">
                                <div class="flex items-center gap-2">
                                  <span class="text-xs opacity-60">
                                    {showBothPrices ? "Original:" : "Current:"}
                                  </span>
                                  <span class={`badge font-mono ${showBothPrices ? "badge-ghost line-through opacity-60" : "badge-neutral"}`}>
                                    {formatCurrency(
                                      product.currentPrice,
                                      product.currency,
                                    )}
                                  </span>
                                </div>
                                {useVoucherPrice && voucherMetrics.voucherSavings > 0 && (
                                  <div class="flex items-center gap-2">
                                    <span class="text-xs opacity-60">With Voucher:</span>
                                    <span class="badge badge-success font-mono font-bold">
                                      {formatCurrency(
                                        voucherMetrics.voucherDiscountedPrice,
                                        product.currency,
                                      )}
                                    </span>
                                    <span class="text-xs text-success">
                                      (-{formatCurrency(voucherMetrics.voucherSavings, product.currency)})
                                    </span>
                                  </div>
                                )}
                                <div class="flex items-center gap-2">
                                  <span class="text-xs opacity-60">Intrinsic:</span>
                                  <span class="badge badge-info font-mono">
                                    {formatCurrency(
                                      product.valueMetrics.intrinsicValue,
                                      product.currency,
                                    )}
                                  </span>
                                </div>
                              </div>
                            </td>
                            <td class="min-w-[300px]">
                              <IntrinsicValueProgressBar
                                currentPriceCents={useVoucherPrice ? voucherMetrics.voucherDiscountedPrice : product.currentPrice}
                                intrinsicValueCents={product.valueMetrics.intrinsicValue}
                              />
                              {showBothPrices && voucherMetrics.voucherSavings > 0 && (
                                <div class="text-xs text-gray-500 mt-1">
                                  Margin: {formatPercentage(voucherMetrics.originalMarginOfSafety)} → {formatPercentage(voucherMetrics.voucherEnhancedMarginOfSafety)}
                                </div>
                              )}
                            </td>
                            <td>
                              <div class="flex flex-col gap-1">
                                {showBothPrices ? (
                                  <>
                                    <span class="badge badge-ghost font-mono line-through opacity-60">
                                      {formatPercentage(product.valueMetrics.expectedROI)}
                                    </span>
                                    {voucherMetrics.voucherSavings > 0 && (
                                      <span
                                        class={`badge font-mono font-bold ${
                                          voucherMetrics.voucherEnhancedROI > 0
                                            ? "badge-success"
                                            : "badge-error"
                                        }`}
                                      >
                                        {formatPercentage(voucherMetrics.voucherEnhancedROI)}
                                        {voucherMetrics.roiImprovement > 0 && (
                                          <span class="ml-1 text-xs">
                                            (+{formatPercentage(voucherMetrics.roiImprovement)}pp)
                                          </span>
                                        )}
                                      </span>
                                    )}
                                  </>
                                ) : (
                                  <span
                                    class={`badge font-mono font-bold ${
                                      (useVoucherPrice ? voucherMetrics.voucherEnhancedROI : product.valueMetrics.expectedROI) > 0
                                        ? "badge-success"
                                        : "badge-error"
                                    }`}
                                  >
                                    {formatPercentage(
                                      useVoucherPrice ? voucherMetrics.voucherEnhancedROI : product.valueMetrics.expectedROI,
                                    )}
                                  </span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}

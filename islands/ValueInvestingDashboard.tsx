import { useSignal } from "@preact/signals";
import { useMemo } from "preact/hooks";
import type { ValueInvestingProduct } from "../types/value-investing.ts";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import { IntrinsicValueProgressBar } from "./components/IntrinsicValueProgressBar.tsx";
import { formatCurrency, formatPercentage } from "../utils/formatters.ts";

interface ValueInvestingDashboardProps {
  products: ValueInvestingProduct[];
}

export default function ValueInvestingDashboard(
  { products: initialProducts }: ValueInvestingDashboardProps,
) {
  const products = useSignal<ValueInvestingProduct[]>(initialProducts);
  const minROI = useSignal<number>(0);
  const maxDistanceFromIntrinsic = useSignal<number>(50); // ±50% from intrinsic value
  const sortBy = useSignal<string>("bestValue"); // Default: furthest below intrinsic first

  /**
   * Memoized filtered products computation
   * Only recalculates when dependencies change
   * Prevents expensive filtering/sorting on every render
   */
  const filteredProducts = useMemo(() => {
    let filtered = [...products.value];

    // ROI filter
    if (minROI.value > 0) {
      filtered = filtered.filter((p) =>
        p.valueMetrics?.expectedROI >= minROI.value
      );
    }

    // Distance from intrinsic value filter
    filtered = filtered.filter((p) => {
      const intrinsicValue = p.valueMetrics?.intrinsicValue ?? 0;
      if (intrinsicValue === 0) return false;

      const distancePercent = ((p.currentPrice - intrinsicValue) / intrinsicValue) * 100;
      return Math.abs(distancePercent) <= maxDistanceFromIntrinsic.value;
    });

    // Sort products (with null safety)
    filtered.sort((a, b) => {
      switch (sortBy.value) {
        case "bestValue": {
          // Furthest below intrinsic value first (most negative distance)
          const aDistance = ((a.currentPrice - (a.valueMetrics?.intrinsicValue ?? 0)) / (a.valueMetrics?.intrinsicValue ?? 1)) * 100;
          const bDistance = ((b.currentPrice - (b.valueMetrics?.intrinsicValue ?? 0)) / (b.valueMetrics?.intrinsicValue ?? 1)) * 100;
          return aDistance - bDistance;
        }
        case "expectedROI":
          return (b.valueMetrics?.expectedROI ?? 0) -
            (a.valueMetrics?.expectedROI ?? 0);
        case "price":
          return a.currentPrice - b.currentPrice;
        case "priceDesc":
          return b.currentPrice - a.currentPrice;
        default:
          return 0;
      }
    });

    return filtered;
  }, [
    products.value,
    minROI.value,
    maxDistanceFromIntrinsic.value,
    sortBy.value,
  ]);


  return (
    <ErrorBoundary>
      <div class="space-y-6">
        {/* Header */}
        <div class="flex flex-col gap-2">
          <h1 class="text-3xl font-bold">Buy Opportunities</h1>
          <p class="text-base-content/70">
            Find products close to their intrinsic value
          </p>
        </div>

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
                      {filteredProducts.map((product) => (
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
                              </div>
                            </div>
                          </td>
                          <td>
                            <div class="flex flex-col gap-1">
                              <div class="flex items-center gap-2">
                                <span class="text-xs opacity-60">Current:</span>
                                <span class="badge badge-neutral font-mono">
                                  {formatCurrency(
                                    product.currentPrice,
                                    product.currency,
                                  )}
                                </span>
                              </div>
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
                              currentPriceCents={product.currentPrice}
                              intrinsicValueCents={product.valueMetrics.intrinsicValue}
                            />
                          </td>
                          <td>
                            <span
                              class={`badge font-mono font-bold ${
                                product.valueMetrics.expectedROI > 0
                                  ? "badge-success"
                                  : "badge-error"
                              }`}
                            >
                              {formatPercentage(
                                product.valueMetrics.expectedROI,
                              )}
                            </span>
                          </td>
                        </tr>
                      ))}
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

import { useSignal } from "@preact/signals";
import type { ValueInvestingProduct } from "../types/value-investing.ts";
import { ErrorBoundary } from "./components/ErrorBoundary.tsx";
import { ValueRatingBadge } from "./components/ValueRatingBadge.tsx";
import {
  formatCurrency,
  formatPercentage,
} from "../utils/formatters.ts";

interface ValueInvestingDashboardProps {
  products: ValueInvestingProduct[];
  strategies: string[];
}

export default function ValueInvestingDashboard(
  { products: initialProducts, strategies }: ValueInvestingDashboardProps,
) {
  const products = useSignal<ValueInvestingProduct[]>(initialProducts);
  const selectedStrategy = useSignal<string>("all");
  const minROI = useSignal<number>(0);
  const minPrice = useSignal<number>(0);
  const maxPrice = useSignal<number>(10000);
  const sortBy = useSignal<string>("marginOfSafety"); // Default: best value first

  // Filter products based on current filters
  const filteredProducts = () => {
    let filtered = [...products.value];

    // Strategy filter
    if (selectedStrategy.value !== "all") {
      filtered = filtered.filter((p) =>
        p.strategy === selectedStrategy.value
      );
    }

    // ROI filter
    if (minROI.value > 0) {
      filtered = filtered.filter((p) =>
        p.valueMetrics?.expectedROI >= minROI.value
      );
    }

    // Price range filter
    filtered = filtered.filter((p) =>
      p.currentPrice >= minPrice.value && p.currentPrice <= maxPrice.value
    );

    // Only show buy opportunities
    filtered = filtered.filter((p) =>
      p.action === "strong_buy" || p.action === "buy"
    );

    // Sort products (with null safety)
    filtered.sort((a, b) => {
      switch (sortBy.value) {
        case "marginOfSafety":
          return (b.valueMetrics?.marginOfSafety ?? 0) -
            (a.valueMetrics?.marginOfSafety ?? 0);
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
  };

  // Calculate summary statistics safely
  const getSummaryStats = () => {
    const filtered = filteredProducts();
    const count = filtered.length;

    if (count === 0) {
      return {
        count: 0,
        avgMarginOfSafety: 0,
        avgExpectedROI: 0,
        totalValueGap: 0,
      };
    }

    const avgMarginOfSafety = filtered.reduce(
        (sum, p) => sum + (p.valueMetrics?.marginOfSafety ?? 0),
        0,
      ) / count;

    const avgExpectedROI = filtered.reduce(
        (sum, p) => sum + (p.valueMetrics?.expectedROI ?? 0),
        0,
      ) / count;

    const totalValueGap = filtered.reduce(
      (sum, p) =>
        sum +
        ((p.valueMetrics?.intrinsicValue ?? 0) - p.currentPrice),
      0,
    );

    return {
      count,
      avgMarginOfSafety,
      avgExpectedROI,
      totalValueGap,
    };
  };

  const resetFilters = () => {
    selectedStrategy.value = "all";
    minROI.value = 0;
    minPrice.value = 0;
    maxPrice.value = 10000;
  };

  // Get stats once per render
  const stats = getSummaryStats();

  return (
    <ErrorBoundary>
      <div class="space-y-6">
      {/* Header */}
      <div class="flex flex-col gap-2">
        <h1 class="text-3xl font-bold">Value Investing Dashboard</h1>
        <p class="text-base-content/70">
          Buy quality assets at a discount to intrinsic value - inspired by
          Buffett & Pabrai
        </p>
      </div>

      {/* Summary Stats */}
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="stat bg-base-100 rounded-lg">
          <div class="stat-title">Buy Opportunities</div>
          <div class="stat-value text-success">
            {stats.count}
          </div>
          <div class="stat-desc">Products with margin of safety</div>
        </div>

        <div class="stat bg-base-100 rounded-lg">
          <div class="stat-title">Avg Margin of Safety</div>
          <div class="stat-value text-primary">
            {formatPercentage(stats.avgMarginOfSafety)}
          </div>
          <div class="stat-desc">Average discount to value</div>
        </div>

        <div class="stat bg-base-100 rounded-lg">
          <div class="stat-title">Avg Expected ROI</div>
          <div class="stat-value text-info">
            {formatPercentage(stats.avgExpectedROI)}
          </div>
          <div class="stat-desc">Potential returns</div>
        </div>

        <div class="stat bg-base-100 rounded-lg">
          <div class="stat-title">Total Value Gap</div>
          <div class="stat-value text-accent">
            {formatCurrency(stats.totalValueGap)}
          </div>
          <div class="stat-desc">Intrinsic value - current price</div>
        </div>
      </div>

      {/* Filters */}
      <div class="card bg-base-100">
        <div class="card-body">
          <h2 class="card-title text-lg">Filters</h2>

          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Strategy Filter */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Investment Strategy</span>
              </label>
              <select
                class="select select-bordered w-full"
                value={selectedStrategy.value}
                onChange={(e) =>
                  selectedStrategy.value =
                    (e.target as HTMLSelectElement).value}
              >
                <option value="all">All Strategies</option>
                {strategies.map((strategy) => (
                  <option key={strategy} value={strategy}>{strategy}</option>
                ))}
              </select>
            </div>

            {/* Min ROI Filter */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">
                  Min ROI: {minROI.value}%
                </span>
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={minROI.value}
                class="range range-primary"
                step="5"
                onInput={(e) =>
                  minROI.value = parseInt(
                    (e.target as HTMLInputElement).value,
                  )}
              />
              <div class="w-full flex justify-between text-xs px-2 opacity-60">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </div>
            </div>

            {/* Price Range */}
            <div class="form-control">
              <label class="label">
                <span class="label-text">Min Price</span>
              </label>
              <input
                type="number"
                class="input input-bordered w-full"
                value={minPrice.value}
                min="0"
                step="10"
                onInput={(e) =>
                  minPrice.value = parseFloat(
                    (e.target as HTMLInputElement).value,
                  )}
              />
            </div>

            <div class="form-control">
              <label class="label">
                <span class="label-text">Max Price</span>
              </label>
              <input
                type="number"
                class="input input-bordered w-full"
                value={maxPrice.value}
                min="0"
                step="10"
                onInput={(e) =>
                  maxPrice.value = parseFloat(
                    (e.target as HTMLInputElement).value,
                  )}
              />
            </div>
          </div>

          <div class="flex gap-2 mt-4">
            <button class="btn btn-sm btn-ghost" onClick={resetFilters}>
              Reset Filters
            </button>
            <div class="ml-auto flex gap-2 items-center">
              <span class="text-sm opacity-70">Sort by:</span>
              <select
                class="select select-bordered select-sm"
                value={sortBy.value}
                onChange={(e) =>
                  sortBy.value = (e.target as HTMLSelectElement).value}
              >
                <option value="marginOfSafety">Margin of Safety (Best)</option>
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
          <h2 class="card-title">
            Buy List ({filteredProducts().length} opportunities)
          </h2>

          {filteredProducts().length === 0
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
                      <th>Current Price</th>
                      <th>Target Price</th>
                      <th>Intrinsic Value</th>
                      <th>Margin of Safety</th>
                      <th>Expected ROI</th>
                      <th>Time Horizon</th>
                      <th>Strategy</th>
                      <th>Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProducts().map((product) => (
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
                          <span class="font-mono">
                            {formatCurrency(
                              product.currentPrice,
                              product.currency,
                            )}
                          </span>
                        </td>
                        <td>
                          <span class="font-mono text-success">
                            {formatCurrency(
                              product.valueMetrics.targetPrice,
                              product.currency,
                            )}
                          </span>
                        </td>
                        <td>
                          <span class="font-mono text-info">
                            {formatCurrency(
                              product.valueMetrics.intrinsicValue,
                              product.currency,
                            )}
                          </span>
                        </td>
                        <td>
                          <span
                            class={`font-mono font-bold ${
                              product.valueMetrics.marginOfSafety > 0
                                ? "text-success"
                                : "text-error"
                            }`}
                          >
                            {formatPercentage(
                              product.valueMetrics.marginOfSafety,
                            )}
                          </span>
                        </td>
                        <td>
                          <span
                            class={`font-mono font-bold ${
                              product.valueMetrics.expectedROI > 0
                                ? "text-success"
                                : "text-error"
                            }`}
                          >
                            {formatPercentage(product.valueMetrics.expectedROI)}
                          </span>
                        </td>
                        <td>
                          <span class="text-sm">
                            {product.valueMetrics.timeHorizon}
                          </span>
                        </td>
                        <td>
                          <span class="badge badge-outline badge-sm">
                            {product.strategy}
                          </span>
                        </td>
                        <td>
                          <ValueRatingBadge
                            marginOfSafety={product.valueMetrics.marginOfSafety}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </div>
      </div>

      {/* Educational Footer */}
      <div class="alert alert-info">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          class="stroke-current shrink-0 w-6 h-6"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          >
          </path>
        </svg>
        <div class="text-sm">
          <p class="font-bold">Value Investing Principles:</p>
          <ul class="list-disc list-inside mt-1 space-y-1">
            <li>
              <strong>Intrinsic Value:</strong>{" "}
              The true worth based on resale potential, demand, and quality
            </li>
            <li>
              <strong>Margin of Safety:</strong>{" "}
              Buy below intrinsic value to protect against errors
            </li>
            <li>
              <strong>Target Price:</strong>{" "}
              The price you should pay (intrinsic value - margin of safety)
            </li>
            <li>
              <strong>Be Patient:</strong>{" "}
              Wait for opportunities where you can buy quality at a discount
            </li>
          </ul>
        </div>
      </div>
    </div>
    </ErrorBoundary>
  );
}

/**
 * PricingOverview - Displays current retail price vs recommended buy price
 * Shows actionable buy/wait signals based on investment analysis
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

interface PricingOverviewProps {
  productId: string;
  currentPrice?: number;
  priceBeforeDiscount?: number;
  currency?: string;
}

interface RecommendedBuyPrice {
  price: number;
  reasoning: string;
  confidence: number;
}

interface AnalysisResponse {
  recommendedBuyPrice?: RecommendedBuyPrice;
  availableDimensions: number;
}

function formatPrice(price: number, currency: string = "MYR"): string {
  return new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
  }).format(price);
}

function getPriceComparison(
  currentPrice: number,
  recommendedPrice: number,
): { status: "good" | "fair" | "overpriced"; label: string; color: string } {
  const ratio = currentPrice / recommendedPrice;

  if (ratio <= 1.0) {
    return {
      status: "good",
      label: "🟢 Great Deal! Buy Now",
      color: "text-success",
    };
  } else if (ratio <= 1.1) {
    return {
      status: "fair",
      label: "🟡 Fair Price",
      color: "text-warning",
    };
  } else {
    return {
      status: "overpriced",
      label: "🔴 Overpriced - Wait for Discount",
      color: "text-error",
    };
  }
}

export default function PricingOverview(
  { productId, currentPrice, priceBeforeDiscount, currency = "MYR" }:
    PricingOverviewProps,
) {
  const loading = useSignal(true);
  const error = useSignal<string | null>(null);
  const analysis = useSignal<AnalysisResponse | null>(null);

  // Fetch analysis data
  useEffect(() => {
    loading.value = true;
    error.value = null;

    fetch(`/api/analysis/${productId}?strategy=Investment Focus`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        analysis.value = data;
        loading.value = false;
      })
      .catch((err) => {
        error.value = err.message;
        loading.value = false;
      });
  }, [productId]);

  // Don't show if no analysis data or no recommended price
  if (
    !loading.value && (!analysis.value?.recommendedBuyPrice ||
      analysis.value.availableDimensions < 3)
  ) {
    return null;
  }

  // Loading state
  if (loading.value) {
    return (
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title text-2xl mb-4">Pricing Overview</h2>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 animate-pulse">
            <div class="h-32 bg-base-300 rounded-lg"></div>
            <div class="h-32 bg-base-300 rounded-lg"></div>
            <div class="h-32 bg-base-300 rounded-lg"></div>
          </div>
        </div>
      </div>
    );
  }

  // Error state - silently hide
  if (error.value) {
    return null;
  }

  const recommendedBuyPrice = analysis.value?.recommendedBuyPrice;
  if (!recommendedBuyPrice) return null;

  const discountPercent = currentPrice && priceBeforeDiscount
    ? Math.round(
      ((priceBeforeDiscount - currentPrice) / priceBeforeDiscount) * 100,
    )
    : null;

  const comparison = currentPrice
    ? getPriceComparison(currentPrice, recommendedBuyPrice.price)
    : null;

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body">
        <h2 class="card-title text-2xl mb-4">💰 Pricing Overview</h2>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Current Retail Price */}
          {currentPrice && (
            <div class="p-4 bg-base-200 rounded-lg">
              <p class="text-sm text-base-content/70 mb-1">Current Price</p>
              <p class="text-3xl font-bold">
                {formatPrice(currentPrice, currency)}
              </p>
              {priceBeforeDiscount && priceBeforeDiscount > currentPrice && (
                <div class="mt-2">
                  <p class="text-sm line-through text-base-content/50">
                    {formatPrice(priceBeforeDiscount, currency)}
                  </p>
                  <div class="badge badge-success gap-1">
                    {discountPercent}% OFF
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recommended Buy Price */}
          <div class="p-4 bg-success/10 border-2 border-success rounded-lg">
            <p class="text-sm text-success font-medium mb-1">
              Recommended Buy Price
            </p>
            <p class="text-3xl font-bold text-success">
              {formatPrice(recommendedBuyPrice.price, currency)}
            </p>
            <p class="text-xs text-success/70 mt-1">or below</p>
            <div class="mt-2">
              <div class="badge badge-success badge-sm">
                {Math.round(recommendedBuyPrice.confidence * 100)}% confidence
              </div>
            </div>
          </div>

          {/* Price Signal */}
          {comparison && currentPrice !== undefined && (
            <div class="p-4 bg-base-200 rounded-lg flex flex-col justify-center">
              <p class={`text-2xl font-bold ${comparison.color} mb-2`}>
                {comparison.label}
              </p>
              <p class="text-sm text-base-content/70">
                Current price is{" "}
                {currentPrice < recommendedBuyPrice.price
                  ? `${formatPrice(recommendedBuyPrice.price - currentPrice, currency)} below`
                  : `${formatPrice(currentPrice - recommendedBuyPrice.price, currency)} above`}{" "}
                target
              </p>
            </div>
          )}
        </div>

        {/* Reasoning (collapsible) */}
        <details class="collapse collapse-arrow bg-base-200 mt-4">
          <summary class="collapse-title text-sm font-medium">
            Why this price?
          </summary>
          <div class="collapse-content">
            <p class="text-sm text-base-content/80">
              {recommendedBuyPrice.reasoning}
            </p>
          </div>
        </details>
      </div>
    </div>
  );
}

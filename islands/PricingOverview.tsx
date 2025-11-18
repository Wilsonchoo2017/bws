/**
 * PricingOverview - Displays current retail price vs recommended buy price
 * Shows actionable buy/wait signals based on investment analysis
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { Cents } from "../types/price.ts";

/**
 * ⚠️ UNIT CONVENTION: All prices in CENTS
 * - currentPrice: CENTS (from database, may be raw number)
 * - priceBeforeDiscount: CENTS (from database, may be raw number)
 * - recommendedBuyPrice.price: CENTS (from API - RecommendationEngine converts from ValueCalculator's DOLLARS to CENTS)
 *
 * Note: Accepts number for backward compatibility with database queries
 */
interface PricingOverviewProps {
  productId: string;
  currentPrice?: Cents | number; // CENTS (accepts number from DB)
  priceBeforeDiscount?: Cents | number; // CENTS (accepts number from DB)
  currency?: string;
}

/**
 * Recommended buy price data structure
 * All price fields are in CENTS for consistency with database layer
 */
interface RecommendedBuyPrice {
  price: Cents; // CENTS - Target buy price (e.g., 31503 = RM 315.03)
  reasoning: string;
  confidence: number;
  breakdown?: {
    intrinsicValue: Cents; // CENTS - Calculated intrinsic value
    baseMargin: number; // Decimal (e.g., 0.25 = 25%)
    adjustedMargin: number; // Decimal (e.g., 0.30 = 30%)
    marginAdjustments: Array<{ reason: string; value: number }>;
    inputs: {
      msrp?: Cents; // CENTS - ValueCalculator now works in cents
      bricklinkAvgPrice?: Cents; // CENTS
      bricklinkMaxPrice?: Cents; // CENTS
      retirementStatus?: string;
      demandScore?: number;
      qualityScore?: number;
      availabilityScore?: number;
    };
  };
}

interface ValueMetrics {
  monthsOfInventory?: number | null;
}

interface AnalysisResponse {
  recommendedBuyPrice?: RecommendedBuyPrice;
  availableDimensions: number;
}

interface ValueInvestingResponse {
  valueMetrics: ValueMetrics;
}

/**
 * Format price from cents (all prices are now in cents)
 * ⚠️ UNIT CONVENTION: Accepts CENTS (or number), displays as currency
 */
function formatPrice(cents: Cents | number, currency: string = "MYR"): string {
  return new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

/**
 * Compare current price vs recommended price
 * ⚠️ UNIT CONVENTION: Both prices in CENTS (or number)
 */
function getPriceComparison(
  currentPriceCents: Cents | number,
  recommendedPriceCents: Cents | number,
): { status: "good" | "fair" | "overpriced"; label: string; color: string } {
  // Both already in cents, compare directly
  const ratio = currentPriceCents / recommendedPriceCents;

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
  const valueInvesting = useSignal<ValueInvestingResponse | null>(null);

  // Fetch analysis data
  useEffect(() => {
    loading.value = true;
    error.value = null;

    // Fetch both analysis and value investing data
    Promise.all([
      fetch(`/api/analysis/${productId}?strategy=Investment Focus`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        }),
      fetch(`/api/value-investing/${productId}`)
        .then((res) => {
          if (!res.ok) return null; // Silently fail for value investing data
          return res.json();
        })
        .catch(() => null), // Silently fail
    ])
      .then(([analysisData, valueData]) => {
        analysis.value = analysisData;
        valueInvesting.value = valueData;
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
                Current price is {currentPrice < recommendedBuyPrice.price
                  ? `${
                    formatPrice(
                      (recommendedBuyPrice.price - currentPrice) as Cents,
                      currency,
                    )
                  } below`
                  : `${
                    formatPrice(
                      (currentPrice - recommendedBuyPrice.price) as Cents,
                      currency,
                    )
                  } above`} target
              </p>
            </div>
          )}
        </div>

        {/* MARKET SUPPLY - MONTHS OF INVENTORY */}
        {valueInvesting.value?.valueMetrics?.monthsOfInventory !== undefined &&
          valueInvesting.value.valueMetrics.monthsOfInventory !== null && (
          <div class="mt-4">
            <div class={`alert ${
              valueInvesting.value.valueMetrics.monthsOfInventory > 24
                ? "alert-error"
                : valueInvesting.value.valueMetrics.monthsOfInventory > 12
                ? "alert-warning"
                : valueInvesting.value.valueMetrics.monthsOfInventory < 3
                ? "alert-success"
                : "alert-info"
            }`}>
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
                />
              </svg>
              <div>
                <h3 class="font-bold">Market Supply</h3>
                <div class="text-sm">
                  {valueInvesting.value.valueMetrics.monthsOfInventory.toFixed(1)} months of inventory at current sales rate
                  {valueInvesting.value.valueMetrics.monthsOfInventory > 24 && (
                    <span class="ml-2">(Dead inventory - avoid)</span>
                  )}
                  {valueInvesting.value.valueMetrics.monthsOfInventory > 12 &&
                    valueInvesting.value.valueMetrics.monthsOfInventory <= 24 && (
                    <span class="ml-2">(High supply - may suppress prices)</span>
                  )}
                  {valueInvesting.value.valueMetrics.monthsOfInventory >= 3 &&
                    valueInvesting.value.valueMetrics.monthsOfInventory <= 12 && (
                    <span class="ml-2">(Healthy supply)</span>
                  )}
                  {valueInvesting.value.valueMetrics.monthsOfInventory < 3 && (
                    <span class="ml-2">(Low supply - scarcity premium)</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

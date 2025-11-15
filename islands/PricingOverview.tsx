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

interface AnalysisResponse {
  recommendedBuyPrice?: RecommendedBuyPrice;
  availableDimensions: number;
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

        {/* Calculation Details (collapsible) */}
        <details class="collapse collapse-arrow bg-base-200 mt-4">
          <summary class="collapse-title text-sm font-medium">
            📊 How is this price calculated?
          </summary>
          <div class="collapse-content space-y-3">
            {/* Reasoning */}
            <div>
              <p class="text-xs font-semibold text-base-content/60 mb-1">
                PRICING STRATEGY
              </p>
              <p class="text-sm text-base-content/80">
                {recommendedBuyPrice.reasoning}
              </p>
            </div>

            {/* Step-by-Step Calculation */}
            {recommendedBuyPrice.breakdown && (
              <>
                <div class="divider my-2"></div>
                <div>
                  <p class="text-xs font-semibold text-base-content/60 mb-3">
                    STEP-BY-STEP CALCULATION
                  </p>

                  {/* Step 1: Intrinsic Value */}
                  <div class="bg-base-300 p-3 rounded-lg mb-3">
                    <div class="flex items-start gap-2 mb-2">
                      <span class="text-success font-mono font-bold">
                        Step 1
                      </span>
                      <div class="flex-1">
                        <strong>Calculate Intrinsic Value</strong>
                      </div>
                    </div>
                    <div class="ml-12 text-sm space-y-1">
                      <div class="text-base-content/70">
                        Using:
                        {recommendedBuyPrice.breakdown.inputs.msrp && (
                          <div>
                            • MSRP: {formatPrice(
                              recommendedBuyPrice.breakdown.inputs.msrp,
                              currency,
                            )}
                          </div>
                        )}
                        {recommendedBuyPrice.breakdown.inputs
                          .bricklinkAvgPrice && (
                          <div>
                            • Bricklink Avg: {formatPrice(
                              recommendedBuyPrice.breakdown.inputs
                                .bricklinkAvgPrice,
                              currency,
                            )}
                          </div>
                        )}
                        {recommendedBuyPrice.breakdown.inputs
                          .retirementStatus &&
                          (
                            <div>
                              • Status: {recommendedBuyPrice.breakdown.inputs
                                .retirementStatus}
                            </div>
                          )}
                        {recommendedBuyPrice.breakdown.inputs.demandScore !==
                            undefined && (
                          <div>
                            • Demand Score:{" "}
                            {recommendedBuyPrice.breakdown.inputs.demandScore
                              .toFixed(
                                0,
                              )}
                            /100
                          </div>
                        )}
                        {recommendedBuyPrice.breakdown.inputs.qualityScore !==
                            undefined && (
                          <div>
                            • Quality Score:{" "}
                            {recommendedBuyPrice.breakdown.inputs.qualityScore
                              .toFixed(
                                0,
                              )}
                            /100
                          </div>
                        )}
                      </div>
                      <div class="font-bold text-success mt-2">
                        = {formatPrice(
                          recommendedBuyPrice.breakdown.intrinsicValue,
                          currency,
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Step 2: Margin of Safety */}
                  <div class="bg-base-300 p-3 rounded-lg mb-3">
                    <div class="flex items-start gap-2 mb-2">
                      <span class="text-success font-mono font-bold">
                        Step 2
                      </span>
                      <div class="flex-1">
                        <strong>Apply Margin of Safety</strong>
                      </div>
                    </div>
                    <div class="ml-12 text-sm space-y-1">
                      <div class="text-base-content/70">
                        Base margin:{" "}
                        {(recommendedBuyPrice.breakdown.baseMargin * 100)
                          .toFixed(
                            0,
                          )}%
                        {recommendedBuyPrice.breakdown.marginAdjustments
                              .length >
                            0 && (
                          <div class="mt-2">
                            Adjustments:
                            {recommendedBuyPrice.breakdown.marginAdjustments
                              .map((
                                adj,
                                i,
                              ) => (
                                <div key={i} class="ml-4">
                                  • {adj.reason}: {adj.value > 0 ? "+" : ""}
                                  {(adj.value * 100).toFixed(1)}%
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                      <div class="font-bold text-success mt-2">
                        Final margin:{" "}
                        {(recommendedBuyPrice.breakdown.adjustedMargin * 100)
                          .toFixed(
                            1,
                          )}%
                      </div>
                    </div>
                  </div>

                  {/* Step 3: Target Price */}
                  <div class="bg-base-300 p-3 rounded-lg">
                    <div class="flex items-start gap-2 mb-2">
                      <span class="text-success font-mono font-bold">
                        Step 3
                      </span>
                      <div class="flex-1">
                        <strong>Calculate Target Buy Price</strong>
                      </div>
                    </div>
                    <div class="ml-12 text-sm space-y-1">
                      <div class="font-mono text-base-content/70">
                        {formatPrice(
                          recommendedBuyPrice.breakdown.intrinsicValue,
                          currency,
                        )} × (1 -{" "}
                        {(recommendedBuyPrice.breakdown.adjustedMargin *
                          100).toFixed(1)}%)
                      </div>
                      <div class="font-mono text-base-content/70">
                        = {formatPrice(
                          recommendedBuyPrice.breakdown.intrinsicValue,
                          currency,
                        )} × {(1 - recommendedBuyPrice.breakdown.adjustedMargin)
                          .toFixed(
                            3,
                          )}
                      </div>
                      <div class="font-bold text-success text-lg mt-2">
                        = {formatPrice(
                          recommendedBuyPrice.price,
                          currency,
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Confidence indicator */}
            <div class="divider my-2"></div>
            <div>
              <p class="text-xs font-semibold text-base-content/60 mb-1">
                DATA CONFIDENCE
              </p>
              <div class="flex items-center gap-2">
                <progress
                  class="progress progress-success w-full"
                  value={recommendedBuyPrice.confidence * 100}
                  max="100"
                >
                </progress>
                <span class="text-sm font-medium">
                  {Math.round(recommendedBuyPrice.confidence * 100)}%
                </span>
              </div>
              <p class="text-xs text-base-content/60 mt-1">
                Based on availability of pricing data, market metrics, and
                quality scores
              </p>
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}

import { RecommendedBuyPrice } from "../hooks/usePriceGuide.ts";

interface PriceComparisonProps {
  unitPriceCents: number; // The price user paid (in cents)
  recommendedBuyPrice?: RecommendedBuyPrice;
  loading?: boolean;
  error?: string;
}

type DealQuality = "great" | "fair" | "overpriced";

interface DealAnalysis {
  quality: DealQuality;
  percentageDiff: number; // Negative means below recommended (good), positive means above (bad)
  badge: string;
  badgeColor: string;
}

/**
 * Analyzes the deal quality by comparing actual price paid with recommended price
 */
function analyzeDeal(
  unitPriceCents: number,
  recommendedPriceDollars: number,
): DealAnalysis {
  const unitPriceDollars = unitPriceCents / 100;
  const diff = unitPriceDollars - recommendedPriceDollars;
  const percentageDiff = (diff / recommendedPriceDollars) * 100;

  let quality: DealQuality;
  let badge: string;
  let badgeColor: string;

  if (percentageDiff <= -10) {
    quality = "great";
    badge = "Great Deal";
    badgeColor = "bg-green-100 text-green-800 border-green-300";
  } else if (percentageDiff >= 10) {
    quality = "overpriced";
    badge = "Overpriced";
    badgeColor = "bg-red-100 text-red-800 border-red-300";
  } else {
    quality = "fair";
    badge = "Fair Price";
    badgeColor = "bg-yellow-100 text-yellow-800 border-yellow-300";
  }

  return {
    quality,
    percentageDiff,
    badge,
    badgeColor,
  };
}

/**
 * Component to display price comparison with recommended buy price
 */
export function PriceComparison({
  unitPriceCents,
  recommendedBuyPrice,
  loading,
  error,
}: PriceComparisonProps) {
  // Loading state
  if (loading) {
    return (
      <div class="flex flex-col gap-1">
        <div class="h-4 w-20 bg-gray-200 animate-pulse rounded"></div>
        <div class="h-5 w-24 bg-gray-200 animate-pulse rounded"></div>
        <div class="h-4 w-16 bg-gray-200 animate-pulse rounded"></div>
      </div>
    );
  }

  // Error state
  if (error || !recommendedBuyPrice) {
    return (
      <div class="text-sm text-gray-400">
        No data
      </div>
    );
  }

  const analysis = analyzeDeal(unitPriceCents, recommendedBuyPrice.price);
  const recommendedPriceFormatted = `$${recommendedBuyPrice.price.toFixed(2)}`;

  // Format percentage difference
  const percentageText = Math.abs(analysis.percentageDiff) < 0.1
    ? "at recommended"
    : `${Math.abs(analysis.percentageDiff).toFixed(0)}% ${
      analysis.percentageDiff < 0 ? "below" : "above"
    }`;

  return (
    <div class="flex flex-col gap-1 text-sm">
      {/* Recommended Price */}
      <div class="text-gray-600">
        Rec:{" "}
        <span class="font-medium text-gray-800">
          {recommendedPriceFormatted}
        </span>
      </div>

      {/* Deal Quality Badge */}
      <div>
        <span
          class={`inline-block px-2 py-0.5 text-xs font-semibold rounded border ${analysis.badgeColor}`}
        >
          {analysis.badge}
        </span>
      </div>

      {/* Percentage Savings/Overpay */}
      <div
        class={`text-xs font-medium ${
          analysis.percentageDiff < 0
            ? "text-green-600"
            : analysis.percentageDiff > 0
            ? "text-red-600"
            : "text-gray-600"
        }`}
      >
        {percentageText}
      </div>
    </div>
  );
}

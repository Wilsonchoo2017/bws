/**
 * IntrinsicValueCard - Interactive island for displaying intrinsic value analysis
 * Shows value investing metrics consistently across the application
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { Cents } from "../types/price.ts";

interface ValueMetrics {
  currentPrice: Cents; // Branded Cents type
  targetPrice: Cents; // Branded Cents type
  intrinsicValue: Cents; // Branded Cents type
  realizedValue?: Cents; // Branded Cents type
  marginOfSafety: number; // Percentage
  expectedROI: number; // Percentage
  realizedROI?: number; // Percentage
  timeHorizon: string;
}

interface BreakdownInputs {
  msrp?: number;
  bricklinkAvgPrice?: number;
  retirementStatus?: string;
  demandScore?: number;
  qualityScore?: number;
  priceToPieceRatio?: number;
  theme?: string;
}

interface MarginAdjustment {
  reason: string;
  value: number;
}

interface CalculationBreakdown {
  intrinsicValue: Cents;
  baseMargin: number;
  adjustedMargin: number;
  marginAdjustments: MarginAdjustment[];
  inputs: BreakdownInputs;
}

interface QualityScoreBreakdown {
  components: {
    ppdScore: { score: number; weightedScore: number; notes: string };
    complexityScore: { score: number; weightedScore: number; notes: string };
    themePremium: { score: number; weightedScore: number; notes: string };
    scarcityScore: { score: number; weightedScore: number; notes: string };
  };
  dataQuality: {
    hasParts: boolean;
    hasMsrp: boolean;
    hasTheme: boolean;
    hasAvailability: boolean;
  };
}

interface DemandScoreBreakdown {
  components: {
    salesVelocity: {
      score: number;
      weight: number;
      weightedScore: number;
      confidence: number;
      notes?: string;
    };
    priceMomentum: {
      score: number;
      weight: number;
      weightedScore: number;
      confidence: number;
      notes?: string;
    };
    marketDepth: {
      score: number;
      weight: number;
      weightedScore: number;
      confidence: number;
      notes?: string;
    };
    supplyDemandRatio: {
      score: number;
      weight: number;
      weightedScore: number;
      confidence: number;
      notes?: string;
    };
    velocityConsistency: {
      score: number;
      weight: number;
      weightedScore: number;
      confidence: number;
      notes?: string;
    };
  };
  dataQuality: {
    hasSalesData: boolean;
    hasPriceData: boolean;
    hasMarketDepth: boolean;
    observationPeriod: number;
  };
}

interface IntrinsicValueData {
  valueMetrics: ValueMetrics;
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  risks: string[];
  opportunities: string[];
  analyzedAt: string;
  currency: string;
  breakdown?: CalculationBreakdown;
  reasoning?: string;
  confidence?: number;
  qualityScoreBreakdown?: QualityScoreBreakdown;
  demandScoreBreakdown?: DemandScoreBreakdown;
}

interface IntrinsicValueCardProps {
  productId: string;
}

export default function IntrinsicValueCard(
  { productId }: IntrinsicValueCardProps,
) {
  const loading = useSignal(true);
  const error = useSignal<string | null>(null);
  const data = useSignal<IntrinsicValueData | null>(null);
  const showDetails = useSignal(false);
  const showQualityBreakdown = useSignal(false);
  const showDemandBreakdown = useSignal(false);

  // Fetch intrinsic value data
  useEffect(() => {
    loading.value = true;
    error.value = null;

    fetch(`/api/value-investing/${productId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((responseData) => {
        data.value = responseData;
        loading.value = false;
      })
      .catch((err) => {
        error.value = err.message;
        loading.value = false;
      });
  }, [productId]);

  if (loading.value) {
    return (
      <div class="card bg-base-100 shadow-xl p-6 animate-pulse">
        <div class="h-8 bg-base-300 rounded w-1/3 mb-4"></div>
        <div class="h-4 bg-base-300 rounded w-full mb-2"></div>
        <div class="h-4 bg-base-300 rounded w-2/3"></div>
      </div>
    );
  }

  if (error.value) {
    return (
      <div class="alert alert-error">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="stroke-current shrink-0 h-6 w-6"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div>
          <h3 class="font-bold">Analysis Error</h3>
          <div class="text-sm">{error.value}</div>
        </div>
      </div>
    );
  }

  if (!data.value) return null;

  const {
    valueMetrics,
    action,
    risks,
    opportunities,
    analyzedAt,
    currency,
    breakdown,
    reasoning,
    confidence,
    qualityScoreBreakdown,
    demandScoreBreakdown,
  } = data.value;

  // Helper: Calculate data completeness percentage
  const calculateQualityCompleteness = () => {
    if (!qualityScoreBreakdown) return 0;
    const { hasParts, hasMsrp, hasTheme, hasAvailability } =
      qualityScoreBreakdown.dataQuality;
    const total = 4;
    const available =
      [hasParts, hasMsrp, hasTheme, hasAvailability].filter(Boolean).length;
    return Math.round((available / total) * 100);
  };

  const calculateDemandCompleteness = () => {
    if (!demandScoreBreakdown) return 0;
    const { hasSalesData, hasPriceData, hasMarketDepth } =
      demandScoreBreakdown.dataQuality;
    const total = 3;
    const available =
      [hasSalesData, hasPriceData, hasMarketDepth].filter(Boolean).length;
    return Math.round((available / total) * 100);
  };

  const formatCurrency = (amountInCents: Cents) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
    }).format(amountInCents / 100); // Convert cents to dollars
  };

  const formatPercentage = (value: number) => {
    return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
  };

  const getActionBadge = (action: string) => {
    switch (action) {
      case "strong_buy":
        return (
          <div class="badge badge-success badge-lg gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
              />
            </svg>
            STRONG BUY
          </div>
        );
      case "buy":
        return (
          <div class="badge badge-success badge-lg gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M5 13l4 4L19 7"
              />
            </svg>
            BUY
          </div>
        );
      case "hold":
        return (
          <div class="badge badge-warning badge-lg gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            HOLD
          </div>
        );
      case "pass":
        return (
          <div class="badge badge-error badge-lg gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
            PASS
          </div>
        );
      default:
        return <div class="badge badge-ghost badge-lg">INSUFFICIENT DATA</div>;
    }
  };

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body space-y-6">
        {/* Header */}
        <div class="flex items-start justify-between">
          <div>
            <h3 class="text-xl font-bold mb-2">Value Investing Analysis</h3>
            <p class="text-sm text-base-content/70">
              Intrinsic value-based evaluation
            </p>
          </div>
          <div>{getActionBadge(action)}</div>
        </div>

        {/* Main Value Metrics */}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Current Price */}
          <div class="p-4 bg-base-200 rounded-lg">
            <p class="text-xs text-base-content/60 mb-1">Current Price</p>
            <p class="text-2xl font-bold font-mono">
              {formatCurrency(valueMetrics.currentPrice)}
            </p>
          </div>

          {/* Intrinsic Value */}
          <div class="p-4 bg-info/10 border-2 border-info rounded-lg">
            <p class="text-xs text-info font-medium mb-1">Intrinsic Value</p>
            <p class="text-2xl font-bold font-mono text-info">
              {formatCurrency(valueMetrics.intrinsicValue)}
            </p>
          </div>

          {/* Target Price */}
          <div class="p-4 bg-success/10 border-2 border-success rounded-lg">
            <p class="text-xs text-success font-medium mb-1">
              Target Buy Price
            </p>
            <p class="text-2xl font-bold font-mono text-success">
              {formatCurrency(valueMetrics.targetPrice)}
            </p>
            <p class="text-xs text-success/70 mt-1">
              or below (with margin of safety)
            </p>
          </div>

          {/* Margin of Safety */}
          <div class="p-4 bg-base-200 rounded-lg">
            <p class="text-xs text-base-content/60 mb-1">Margin of Safety</p>
            <p
              class={`text-2xl font-bold font-mono ${
                valueMetrics.marginOfSafety > 0 ? "text-success" : "text-error"
              }`}
            >
              {formatPercentage(valueMetrics.marginOfSafety)}
            </p>
          </div>
        </div>

        {/* ROI and Time Horizon */}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Expected ROI */}
          <div class="p-4 bg-base-200 rounded-lg">
            <p class="text-xs text-base-content/60 mb-1">Expected ROI</p>
            <p
              class={`text-xl font-bold font-mono ${
                valueMetrics.expectedROI > 0 ? "text-success" : "text-error"
              }`}
            >
              {formatPercentage(valueMetrics.expectedROI)}
            </p>
          </div>

          {/* Time Horizon */}
          <div class="p-4 bg-primary/10 rounded-lg">
            <p class="text-xs text-primary font-medium mb-1">Time Horizon</p>
            <p class="text-xl font-semibold">{valueMetrics.timeHorizon}</p>
          </div>
        </div>

        {/* Realized Value (if available) */}
        {valueMetrics.realizedValue !== undefined && (
          <div class="p-4 bg-warning/10 border border-warning rounded-lg">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-xs text-warning font-medium mb-1">
                  Realized Value (after costs)
                </p>
                <p class="text-xl font-bold font-mono">
                  {formatCurrency(valueMetrics.realizedValue)}
                </p>
              </div>
              {valueMetrics.realizedROI !== undefined && (
                <div class="text-right">
                  <p class="text-xs text-base-content/60 mb-1">Realized ROI</p>
                  <p
                    class={`text-xl font-bold font-mono ${
                      valueMetrics.realizedROI > 0
                        ? "text-success"
                        : "text-error"
                    }`}
                  >
                    {formatPercentage(valueMetrics.realizedROI)}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Quality Score Breakdown */}
        {qualityScoreBreakdown && (
          <>
            <button
              class="btn btn-outline btn-block btn-sm"
              onClick={() =>
                showQualityBreakdown.value = !showQualityBreakdown.value}
            >
              {showQualityBreakdown.value
                ? "▲ Hide Quality Score Breakdown"
                : "▼ Show Quality Score Breakdown"}
              {calculateQualityCompleteness() < 100 && (
                <span class="badge badge-warning badge-sm ml-2">
                  ⚠️ Incomplete Data
                </span>
              )}
            </button>

            {showQualityBreakdown.value && (
              <div class="space-y-4 pt-4 border-t border-base-300">
                {/* Data Completeness Bar */}
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <p class="text-xs font-semibold text-base-content/60">
                      DATA COMPLETENESS
                    </p>
                    <span class="text-sm font-medium">
                      {calculateQualityCompleteness()}%
                    </span>
                  </div>
                  <progress
                    class={`progress w-full ${
                      calculateQualityCompleteness() === 100
                        ? "progress-success"
                        : calculateQualityCompleteness() >= 50
                        ? "progress-warning"
                        : "progress-error"
                    }`}
                    value={calculateQualityCompleteness()}
                    max="100"
                  >
                  </progress>
                  {calculateQualityCompleteness() < 100 && (
                    <p class="text-xs text-base-content/60 mt-1">
                      Missing: {[
                        !qualityScoreBreakdown.dataQuality.hasParts &&
                        "Parts Count",
                        !qualityScoreBreakdown.dataQuality.hasMsrp && "MSRP",
                        !qualityScoreBreakdown.dataQuality.hasTheme && "Theme",
                        !qualityScoreBreakdown.dataQuality.hasAvailability &&
                        "Availability",
                      ].filter(Boolean).join(", ")}
                    </p>
                  )}
                </div>

                {/* Component Scores */}
                <div class="space-y-3">
                  <p class="text-xs font-semibold text-base-content/60">
                    COMPONENT BREAKDOWN
                  </p>

                  {/* PPD Score */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Parts-Per-Dollar (40% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {qualityScoreBreakdown.components.ppdScore.score}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-primary flex-1"
                        value={qualityScoreBreakdown.components.ppdScore.score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        →{" "}
                        {qualityScoreBreakdown.components.ppdScore.weightedScore
                          .toFixed(1)} pts
                      </span>
                    </div>
                    <p class="text-xs text-base-content/60 mt-1">
                      {qualityScoreBreakdown.components.ppdScore.notes}
                    </p>
                  </div>

                  {/* Complexity Score */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Build Complexity (30% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {qualityScoreBreakdown.components.complexityScore
                          .score}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-primary flex-1"
                        value={qualityScoreBreakdown.components.complexityScore
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {qualityScoreBreakdown.components.complexityScore
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    <p class="text-xs text-base-content/60 mt-1">
                      {qualityScoreBreakdown.components.complexityScore.notes}
                    </p>
                  </div>

                  {/* Theme Premium */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Theme Premium (20% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {qualityScoreBreakdown.components.themePremium
                          .score}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-primary flex-1"
                        value={qualityScoreBreakdown.components.themePremium
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {qualityScoreBreakdown.components.themePremium
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    <p class="text-xs text-base-content/60 mt-1">
                      {qualityScoreBreakdown.components.themePremium.notes}
                    </p>
                  </div>

                  {/* Scarcity Score */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Scarcity (10% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {qualityScoreBreakdown.components.scarcityScore
                          .score}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-primary flex-1"
                        value={qualityScoreBreakdown.components.scarcityScore
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {qualityScoreBreakdown.components.scarcityScore
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    <p class="text-xs text-base-content/60 mt-1">
                      {qualityScoreBreakdown.components.scarcityScore.notes}
                    </p>
                  </div>

                  {/* Total */}
                  <div class="bg-success/10 border-2 border-success p-3 rounded-lg">
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-bold text-success">
                        Total Quality Score
                      </span>
                      <span class="text-lg font-bold text-success">
                        {Math.round(
                          qualityScoreBreakdown.components.ppdScore
                            .weightedScore +
                            qualityScoreBreakdown.components.complexityScore
                              .weightedScore +
                            qualityScoreBreakdown.components.themePremium
                              .weightedScore +
                            qualityScoreBreakdown.components.scarcityScore
                              .weightedScore,
                        )}/100
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Demand Score Breakdown */}
        {demandScoreBreakdown && (
          <>
            <button
              class="btn btn-outline btn-block btn-sm"
              onClick={() =>
                showDemandBreakdown.value = !showDemandBreakdown.value}
            >
              {showDemandBreakdown.value
                ? "▲ Hide Demand Score Breakdown"
                : "▼ Show Demand Score Breakdown"}
              {calculateDemandCompleteness() < 100 && (
                <span class="badge badge-warning badge-sm ml-2">
                  ⚠️ Incomplete Data
                </span>
              )}
            </button>

            {showDemandBreakdown.value && (
              <div class="space-y-4 pt-4 border-t border-base-300">
                {/* Data Completeness Bar */}
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <p class="text-xs font-semibold text-base-content/60">
                      DATA COMPLETENESS
                    </p>
                    <span class="text-sm font-medium">
                      {calculateDemandCompleteness()}%
                    </span>
                  </div>
                  <progress
                    class={`progress w-full ${
                      calculateDemandCompleteness() === 100
                        ? "progress-success"
                        : calculateDemandCompleteness() >= 50
                        ? "progress-warning"
                        : "progress-error"
                    }`}
                    value={calculateDemandCompleteness()}
                    max="100"
                  >
                  </progress>
                  {calculateDemandCompleteness() < 100 && (
                    <p class="text-xs text-base-content/60 mt-1">
                      Missing: {[
                        !demandScoreBreakdown.dataQuality.hasSalesData &&
                        "Sales Data",
                        !demandScoreBreakdown.dataQuality.hasPriceData &&
                        "Price History",
                        !demandScoreBreakdown.dataQuality.hasMarketDepth &&
                        "Market Depth",
                      ].filter(Boolean).join(", ")}
                    </p>
                  )}
                  <p class="text-xs text-base-content/60 mt-1">
                    Observation Period:{" "}
                    {demandScoreBreakdown.dataQuality.observationPeriod} days
                  </p>
                </div>

                {/* Component Scores */}
                <div class="space-y-3">
                  <p class="text-xs font-semibold text-base-content/60">
                    COMPONENT BREAKDOWN
                  </p>

                  {/* Sales Velocity */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Sales Velocity
                        ({(demandScoreBreakdown.components.salesVelocity
                          .weight * 100).toFixed(0)}% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {demandScoreBreakdown.components.salesVelocity.score
                          .toFixed(0)}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-info flex-1"
                        value={demandScoreBreakdown.components.salesVelocity
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {demandScoreBreakdown.components.salesVelocity
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    {demandScoreBreakdown.components.salesVelocity.notes && (
                      <p class="text-xs text-base-content/60 mt-1">
                        {demandScoreBreakdown.components.salesVelocity.notes}
                      </p>
                    )}
                  </div>

                  {/* Price Momentum */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Price Momentum
                        ({(demandScoreBreakdown.components.priceMomentum
                          .weight * 100).toFixed(0)}% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {demandScoreBreakdown.components.priceMomentum.score
                          .toFixed(0)}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-info flex-1"
                        value={demandScoreBreakdown.components.priceMomentum
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {demandScoreBreakdown.components.priceMomentum
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    {demandScoreBreakdown.components.priceMomentum.notes && (
                      <p class="text-xs text-base-content/60 mt-1">
                        {demandScoreBreakdown.components.priceMomentum.notes}
                      </p>
                    )}
                  </div>

                  {/* Market Depth */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Market Depth
                        ({(demandScoreBreakdown.components.marketDepth.weight *
                          100).toFixed(0)}% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {demandScoreBreakdown.components.marketDepth.score
                          .toFixed(0)}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-info flex-1"
                        value={demandScoreBreakdown.components.marketDepth
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {demandScoreBreakdown.components.marketDepth
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    {demandScoreBreakdown.components.marketDepth.notes && (
                      <p class="text-xs text-base-content/60 mt-1">
                        {demandScoreBreakdown.components.marketDepth.notes}
                      </p>
                    )}
                  </div>

                  {/* Supply/Demand Ratio */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Supply/Demand Ratio
                        ({(demandScoreBreakdown.components.supplyDemandRatio
                          .weight * 100).toFixed(0)}% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {demandScoreBreakdown.components.supplyDemandRatio.score
                          .toFixed(0)}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-info flex-1"
                        value={demandScoreBreakdown.components.supplyDemandRatio
                          .score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {demandScoreBreakdown.components.supplyDemandRatio
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    {demandScoreBreakdown.components.supplyDemandRatio.notes &&
                      (
                        <p class="text-xs text-base-content/60 mt-1">
                          {demandScoreBreakdown.components.supplyDemandRatio
                            .notes}
                        </p>
                      )}
                  </div>

                  {/* Velocity Consistency */}
                  <div class="bg-base-200 p-3 rounded-lg">
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-sm font-medium">
                        Velocity Consistency
                        ({(demandScoreBreakdown.components.velocityConsistency
                          .weight * 100).toFixed(0)}% weight)
                      </span>
                      <span class="text-sm font-bold">
                        {demandScoreBreakdown.components.velocityConsistency
                          .score.toFixed(0)}/100
                      </span>
                    </div>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-info flex-1"
                        value={demandScoreBreakdown.components
                          .velocityConsistency.score}
                        max="100"
                      >
                      </progress>
                      <span class="text-xs text-base-content/60">
                        → {demandScoreBreakdown.components.velocityConsistency
                          .weightedScore.toFixed(1)} pts
                      </span>
                    </div>
                    {demandScoreBreakdown.components.velocityConsistency
                      .notes && (
                      <p class="text-xs text-base-content/60 mt-1">
                        {demandScoreBreakdown.components.velocityConsistency
                          .notes}
                      </p>
                    )}
                  </div>

                  {/* Total */}
                  <div class="bg-info/10 border-2 border-info p-3 rounded-lg">
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-bold text-info">
                        Total Demand Score
                      </span>
                      <span class="text-lg font-bold text-info">
                        {Math.round(
                          demandScoreBreakdown.components.salesVelocity
                            .weightedScore +
                            demandScoreBreakdown.components.priceMomentum
                              .weightedScore +
                            demandScoreBreakdown.components.marketDepth
                              .weightedScore +
                            demandScoreBreakdown.components.supplyDemandRatio
                              .weightedScore +
                            demandScoreBreakdown.components.velocityConsistency
                              .weightedScore,
                        )}/100
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Opportunities and Risks Toggle */}
        {(risks.length > 0 || opportunities.length > 0) && (
          <>
            <button
              class="btn btn-outline btn-block btn-sm"
              onClick={() => showDetails.value = !showDetails.value}
            >
              {showDetails.value
                ? "▲ Hide Details"
                : "▼ Show Opportunities & Risks"}
            </button>

            {/* Details Section */}
            {showDetails.value && (
              <div class="space-y-4 pt-4 border-t border-base-300">
                {/* Opportunities */}
                {opportunities.length > 0 && (
                  <div>
                    <h5 class="font-semibold text-success mb-2">
                      ✅ Opportunities
                    </h5>
                    <ul class="space-y-1">
                      {opportunities.map((opp, idx) => (
                        <li key={idx} class="text-sm flex items-start">
                          <span class="text-success mr-2">•</span>
                          <span>{opp}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Risks */}
                {risks.length > 0 && (
                  <div>
                    <h5 class="font-semibold text-error mb-2">⚠️ Risks</h5>
                    <ul class="space-y-1">
                      {risks.map((risk, idx) => (
                        <li key={idx} class="text-sm flex items-start">
                          <span class="text-error mr-2">•</span>
                          <span>{risk}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Calculation Details (collapsible) */}
        {breakdown && (
          <details class="collapse collapse-arrow bg-base-200 mt-4">
            <summary class="collapse-title text-sm font-medium">
              📊 How is this value calculated?
            </summary>
            <div class="collapse-content space-y-3">
              {/* Reasoning */}
              {reasoning && (
                <div>
                  <p class="text-xs font-semibold text-base-content/60 mb-1">
                    PRICING STRATEGY
                  </p>
                  <p class="text-sm text-base-content/80">
                    {reasoning}
                  </p>
                </div>
              )}

              {/* Step-by-Step Calculation */}
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
                      {breakdown.inputs.msrp && (
                        <div>
                          • MSRP:{" "}
                          {formatCurrency(breakdown.inputs.msrp as Cents)}
                        </div>
                      )}
                      {breakdown.inputs.bricklinkAvgPrice && (
                        <div>
                          • Bricklink Avg: {formatCurrency(
                            breakdown.inputs.bricklinkAvgPrice as Cents,
                          )}
                        </div>
                      )}
                      {breakdown.inputs.retirementStatus && (
                        <div>
                          • Status: {breakdown.inputs.retirementStatus}
                        </div>
                      )}
                      {breakdown.inputs.demandScore !== undefined && (
                        <div>
                          • Demand Score:{" "}
                          {breakdown.inputs.demandScore.toFixed(0)}/100
                        </div>
                      )}
                      {breakdown.inputs.qualityScore !== undefined && (
                        <div>
                          • Quality Score:{" "}
                          {breakdown.inputs.qualityScore.toFixed(0)}/100
                        </div>
                      )}
                      {breakdown.inputs.priceToPieceRatio !== undefined && (
                        <div>
                          • Price/Piece: ${breakdown.inputs.priceToPieceRatio
                            .toFixed(
                              3,
                            )}
                        </div>
                      )}
                      {breakdown.inputs.theme && (
                        <div>
                          • Theme: {breakdown.inputs.theme}
                        </div>
                      )}
                    </div>
                    <div class="font-bold text-success mt-2">
                      = {formatCurrency(breakdown.intrinsicValue)}
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
                      Base margin: {(breakdown.baseMargin * 100).toFixed(0)}%
                      {breakdown.marginAdjustments.length > 0 && (
                        <div class="mt-2">
                          Adjustments:
                          {breakdown.marginAdjustments.map((adj, i) => (
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
                      {(breakdown.adjustedMargin * 100).toFixed(1)}%
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
                      {formatCurrency(breakdown.intrinsicValue)} × (1 -{" "}
                      {(breakdown.adjustedMargin * 100).toFixed(1)}%)
                    </div>
                    <div class="font-mono text-base-content/70">
                      = {formatCurrency(breakdown.intrinsicValue)} ×{" "}
                      {(1 - breakdown.adjustedMargin).toFixed(3)}
                    </div>
                    <div class="font-bold text-success text-lg mt-2">
                      = {formatCurrency(valueMetrics.targetPrice)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Confidence indicator */}
              {confidence !== undefined && (
                <>
                  <div class="divider my-2"></div>
                  <div>
                    <p class="text-xs font-semibold text-base-content/60 mb-1">
                      DATA CONFIDENCE
                    </p>
                    <div class="flex items-center gap-2">
                      <progress
                        class="progress progress-success w-full"
                        value={confidence * 100}
                        max="100"
                      >
                      </progress>
                      <span class="text-sm font-medium">
                        {Math.round(confidence * 100)}%
                      </span>
                    </div>
                    <p class="text-xs text-base-content/60 mt-1">
                      Based on availability of pricing data, market metrics, and
                      quality scores
                    </p>
                  </div>
                </>
              )}
            </div>
          </details>
        )}

        {/* Analysis Timestamp */}
        <p class="text-xs text-base-content/50 text-center pt-4 border-t border-base-300">
          Analyzed: {new Date(analyzedAt).toLocaleString()}
        </p>
      </div>
    </div>
  );
}

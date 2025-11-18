/**
 * IntrinsicValueCard - Interactive island for displaying intrinsic value analysis
 * Shows value investing metrics consistently across the application
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { Cents } from "../types/price.ts";

interface DataQuality {
  canCalculate: boolean;
  qualityScore: number;
  confidenceLevel: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT";
  explanation: string;
  missingCriticalData: string[];
  missingOptionalData: string[];
}

interface ValueProjection {
  currentValue: Cents;
  oneYearValue: Cents;
  threeYearValue: Cents;
  fiveYearValue: Cents;
  expectedCAGR: number;
  supplyExhaustionMonths: number | null;
  monthsOfInventory: number | null;
  projectionConfidence: number;
  assumptions: string[];
  risks: string[];
}

interface ValueMetrics {
  currentPrice: Cents; // Branded Cents type
  targetPrice: Cents; // Branded Cents type
  intrinsicValue: Cents; // Branded Cents type
  realizedValue?: Cents; // Branded Cents type
  marginOfSafety: number; // Percentage
  expectedROI: number; // Percentage
  realizedROI?: number; // Percentage
  timeHorizon: string;
  // Deal quality metrics
  dealQualityScore?: number;
  dealQualityLabel?: string;
  dealRecommendation?: string;
  retailDiscountPercent?: number;
  priceToMarketRatio?: number;
  priceToValueRatio?: number;
  // Detailed calculation breakdown
  calculationBreakdown?: IntrinsicValueBreakdown;
  // ENHANCED: Future value projections
  valueProjection?: ValueProjection | null;
  // ENHANCED: Data quality assessment
  dataQuality?: DataQuality | null;
  // ENHANCED: Months of inventory
  monthsOfInventory?: number | null;
}

interface IntrinsicValueBreakdown {
  baseValue: Cents;
  baseValueSource: "msrp" | "currentRetail" | "bricklink" | "none";
  baseValueExplanation: string;
  qualityMultipliers: {
    retirement: { value: number; explanation: string; applied: boolean };
    quality: { value: number; score: number; explanation: string };
    demand: { value: number; score: number; explanation: string };
    theme: { value: number; themeName: string; explanation: string };
    partsPerDollar: {
      value: number;
      ppdValue?: number;
      explanation: string;
    };
  };
  riskDiscounts: {
    liquidity: { value: number; explanation: string; applied: boolean };
    volatility: {
      value: number;
      volatilityPercent?: number;
      explanation: string;
      applied: boolean;
    };
    saturation: { value: number; explanation: string; applied: boolean };
    zeroSales: { value: number; explanation: string; applied: boolean };
  };
  intermediateValues: {
    afterQualityMultipliers: Cents;
    afterRiskDiscounts: Cents;
  };
  finalIntrinsicValue: Cents;
  totalMultiplier: number;
  // Rejection metadata (Pabrai "Too Hard Pile")
  rejection?: {
    rejected: boolean;
    reason: string;
    category: "INSUFFICIENT_DATA" | "INSUFFICIENT_DEMAND" | "DEAD_INVENTORY" | "OVERSATURATED" | "VALUE_TRAP";
  };
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

interface AvailabilityScoreBreakdown {
  components: Array<{
    name: string;
    weight: number;
    score: number;
    rawValue: string | number;
    calculation: string;
    reasoning: string;
  }>;
  formula: string;
  totalScore: number;
  dataPoints: Record<string, unknown>;
  missingData?: string[];
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
  availabilityScoreBreakdown?: AvailabilityScoreBreakdown;
  catalyst?: {
    isPreRetirementOpportunity: boolean;
    urgency: "high" | "medium" | "low";
    reason: string;
  };
  appreciationPhase?: {
    phase: "market-flooded" | "stabilizing" | "appreciation" | "scarcity" | "vintage";
    description: string;
  };
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
  const showQualityBreakdown = useSignal(true);
  const showDemandBreakdown = useSignal(true);
  const showAvailabilityBreakdown = useSignal(true);
  const showIntrinsicBreakdown = useSignal(false);

  // Fetch intrinsic value data
  useEffect(() => {
    loading.value = true;
    error.value = null;

    fetch(`/api/value-investing/${productId}`)
      .then(async (res) => {
        // Get response text first (can be parsed as JSON or used as-is)
        const responseText = await res.text();

        if (!res.ok) {
          // Extract error details from API response
          let errorMessage = `HTTP ${res.status}`;

          try {
            const errorData = JSON.parse(responseText);
            // Extract the most informative error message
            errorMessage = errorData.reason ||
                          errorData.error ||
                          errorData.details?.reasoning ||
                          (errorData.details?.risks && errorData.details.risks[0]) ||
                          `HTTP ${res.status} - ${res.statusText}`;
          } catch (_parseError) {
            // If not valid JSON, use the text directly (truncated)
            if (responseText && responseText.length > 0) {
              errorMessage = responseText.substring(0, 200);
            }
          }

          throw new Error(errorMessage);
        }

        // Parse successful response
        return JSON.parse(responseText);
      })
      .then((responseData) => {
        data.value = responseData;
        loading.value = false;
      })
      .catch((err) => {
        console.error('[IntrinsicValueCard] Error fetching data:', err);
        error.value = err.message || 'Failed to load investment analysis';
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
    analyzedAt,
    currency,
    breakdown: _breakdown,
    reasoning: _reasoning,
    confidence: _confidence,
    qualityScoreBreakdown,
    demandScoreBreakdown,
    availabilityScoreBreakdown,
    catalyst,
    appreciationPhase,
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

  const calculateAvailabilityCompleteness = () => {
    if (!availabilityScoreBreakdown) return 0;
    const { missingData } = availabilityScoreBreakdown;
    const totalComponents = 3; // Retirement Urgency, Stock Availability, Platform Status
    const missingCount = missingData ? missingData.length : 0;
    const available = totalComponents - missingCount;
    return Math.round((available / totalComponents) * 100);
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

        {/* PABRAI "TOO HARD PILE" - REJECTION BANNER */}
        {valueMetrics.calculationBreakdown?.rejection?.rejected && (
          <div class="alert alert-error shadow-lg">
            <div class="flex items-start gap-4">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="stroke-current shrink-0 h-8 w-8"
                fill="none"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                />
              </svg>
              <div class="flex-1">
                <h3 class="font-bold text-lg">
                  ⛔ REJECTED - "Too Hard Pile"
                </h3>
                <p class="text-sm mt-1">
                  {valueMetrics.calculationBreakdown.rejection.reason}
                </p>
                <div class="mt-3 p-3 bg-base-100 rounded-lg">
                  <p class="text-xs font-semibold mb-2">Why was this rejected?</p>
                  <p class="text-xs opacity-90">
                    {valueMetrics.calculationBreakdown.rejection.category === "INSUFFICIENT_DATA" && (
                      <>
                        <strong>Quality/Demand Too Low:</strong> Pabrai's principle - only invest in sets you can confidently value.
                        Sets with quality or demand scores below 40/100 lack sufficient data for accurate valuation.
                      </>
                    )}
                    {valueMetrics.calculationBreakdown.rejection.category === "INSUFFICIENT_DEMAND" && (
                      <>
                        <strong>Market Demand Too Weak:</strong> Sets with demand scores below 40/100 indicate insufficient buyer interest.
                        Without demand, even "cheap" sets are bad investments.
                      </>
                    )}
                    {valueMetrics.calculationBreakdown.rejection.category === "DEAD_INVENTORY" && (
                      <>
                        <strong>Illiquid Market:</strong> Less than 1 sale per month indicates dead inventory.
                        You won't be able to sell this - your money will be tied up indefinitely.
                      </>
                    )}
                    {valueMetrics.calculationBreakdown.rejection.category === "OVERSATURATED" && (
                      <>
                        <strong>Market Flooded:</strong> More than 24 months of inventory at current sales velocity.
                        It would take years to sell through existing supply - avoid oversaturated markets.
                      </>
                    )}
                    {valueMetrics.calculationBreakdown.rejection.category === "VALUE_TRAP" && (
                      <>
                        <strong>Falling Knife Detected:</strong> Declining prices combined with high inventory is a classic value trap.
                        The set appears "cheap" but prices are falling for a reason - don't catch falling knives.
                      </>
                    )}
                  </p>
                </div>
                <div class="mt-3">
                  <div class="badge badge-neutral badge-sm">
                    Category: {valueMetrics.calculationBreakdown.rejection.category.replace(/_/g, " ")}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* DATA QUALITY BANNER - PABRAI APPROACH */}
        {valueMetrics.dataQuality && (
          <div>
            {/* INSUFFICIENT DATA - RED BANNER */}
            {!valueMetrics.dataQuality.canCalculate && (
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
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <div>
                  <h3 class="font-bold">INSUFFICIENT DATA TO VALUE</h3>
                  <div class="text-sm">{valueMetrics.dataQuality.explanation}</div>
                  {valueMetrics.dataQuality.missingCriticalData.length > 0 && (
                    <div class="text-xs mt-2">
                      Missing: {valueMetrics.dataQuality.missingCriticalData.join(", ")}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* LOW CONFIDENCE - YELLOW BANNER */}
            {valueMetrics.dataQuality.canCalculate &&
              valueMetrics.dataQuality.confidenceLevel === "LOW" && (
              <div class="alert alert-warning">
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
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <div>
                  <h3 class="font-bold">LOW CONFIDENCE - Use with Caution</h3>
                  <div class="text-sm">
                    Quality Score: {valueMetrics.dataQuality.qualityScore}/100
                  </div>
                </div>
              </div>
            )}

            {/* MEDIUM CONFIDENCE - INFO BANNER */}
            {valueMetrics.dataQuality.canCalculate &&
              valueMetrics.dataQuality.confidenceLevel === "MEDIUM" && (
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
                  />
                </svg>
                <div>
                  <h3 class="font-bold">MEDIUM CONFIDENCE</h3>
                  <div class="text-sm">
                    Quality Score: {valueMetrics.dataQuality.qualityScore}/100
                  </div>
                </div>
              </div>
            )}

            {/* HIGH CONFIDENCE - GREEN CHECKMARK */}
            {valueMetrics.dataQuality.canCalculate &&
              valueMetrics.dataQuality.confidenceLevel === "HIGH" && (
              <div class="alert alert-success">
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
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <h3 class="font-bold">HIGH CONFIDENCE - Comprehensive Data</h3>
                  <div class="text-sm">
                    Quality Score: {valueMetrics.dataQuality.qualityScore}/100
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* PRE-RETIREMENT CATALYST BADGE */}
        {catalyst?.isPreRetirementOpportunity && (
          <div class={`alert ${
            catalyst.urgency === "high"
              ? "alert-error"
              : catalyst.urgency === "medium"
              ? "alert-warning"
              : "alert-info"
          }`}>
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
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div>
              <h3 class="font-bold">⏰ RETIRING SOON - BUY BEFORE SCARCITY</h3>
              <div class="text-sm">{catalyst.reason}</div>
            </div>
          </div>
        )}

        {/* APPRECIATION PHASE INDICATOR */}
        {appreciationPhase && (
          <div class={`badge badge-lg ${
            appreciationPhase.phase === "appreciation"
              ? "badge-success"
              : appreciationPhase.phase === "stabilizing"
              ? "badge-info"
              : appreciationPhase.phase === "scarcity"
              ? "badge-warning"
              : appreciationPhase.phase === "vintage"
              ? "badge-secondary"
              : "badge-ghost"
          }`}>
            {appreciationPhase.phase.toUpperCase()}: {appreciationPhase.description}
          </div>
        )}

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

        {/* FUTURE VALUE PROJECTIONS - PABRAI'S "CASH GENERATION" FOCUS */}
        {valueMetrics.valueProjection && (
          <div class="collapse collapse-arrow bg-base-200">
            <input type="checkbox" />
            <div class="collapse-title text-lg font-medium">
              📈 Future Value Projections
              <span class="text-sm text-base-content/60 ml-2">
                ({valueMetrics.valueProjection.projectionConfidence}% confidence)
              </span>
            </div>
            <div class="collapse-content space-y-4">
              {/* Value Timeline */}
              <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div class="p-3 bg-base-100 rounded-lg">
                  <p class="text-xs text-base-content/60 mb-1">Current</p>
                  <p class="text-lg font-bold">
                    {formatCurrency(valueMetrics.valueProjection.currentValue)}
                  </p>
                </div>
                <div class="p-3 bg-base-100 rounded-lg">
                  <p class="text-xs text-base-content/60 mb-1">1 Year</p>
                  <p class="text-lg font-bold text-info">
                    {formatCurrency(valueMetrics.valueProjection.oneYearValue)}
                  </p>
                </div>
                <div class="p-3 bg-base-100 rounded-lg">
                  <p class="text-xs text-base-content/60 mb-1">3 Years</p>
                  <p class="text-lg font-bold text-success">
                    {formatCurrency(valueMetrics.valueProjection.threeYearValue)}
                  </p>
                </div>
                <div class="p-3 bg-base-100 rounded-lg">
                  <p class="text-xs text-base-content/60 mb-1">5 Years</p>
                  <p class="text-lg font-bold text-warning">
                    {formatCurrency(valueMetrics.valueProjection.fiveYearValue)}
                  </p>
                </div>
              </div>

              {/* Expected CAGR */}
              <div class="p-3 bg-base-100 rounded-lg">
                <p class="text-xs text-base-content/60 mb-1">Expected Annual Growth (CAGR)</p>
                <p class={`text-2xl font-bold ${
                  valueMetrics.valueProjection.expectedCAGR > 0 ? "text-success" : "text-error"
                }`}>
                  {formatPercentage(valueMetrics.valueProjection.expectedCAGR)}
                </p>
              </div>

              {/* Supply Metrics */}
              {(valueMetrics.valueProjection.monthsOfInventory !== null ||
                valueMetrics.valueProjection.supplyExhaustionMonths !== null) && (
                <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {valueMetrics.valueProjection.monthsOfInventory !== null && (
                    <div class="p-3 bg-base-100 rounded-lg">
                      <p class="text-xs text-base-content/60 mb-1">Months of Inventory</p>
                      <p class="text-xl font-bold">
                        {valueMetrics.valueProjection.monthsOfInventory.toFixed(1)} months
                      </p>
                    </div>
                  )}
                  {valueMetrics.valueProjection.supplyExhaustionMonths !== null && (
                    <div class="p-3 bg-base-100 rounded-lg">
                      <p class="text-xs text-base-content/60 mb-1">Supply Exhaustion</p>
                      <p class="text-xl font-bold">
                        ~{valueMetrics.valueProjection.supplyExhaustionMonths.toFixed(0)} months
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Key Assumptions */}
              {valueMetrics.valueProjection.assumptions.length > 0 && (
                <div class="collapse collapse-arrow bg-base-100">
                  <input type="checkbox" />
                  <div class="collapse-title text-sm font-medium">
                    Key Assumptions ({valueMetrics.valueProjection.assumptions.length})
                  </div>
                  <div class="collapse-content">
                    <ul class="text-sm space-y-1">
                      {valueMetrics.valueProjection.assumptions.map((assumption, idx) => (
                        <li key={idx} class="flex items-start">
                          <span class="text-info mr-2">•</span>
                          <span>{assumption}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Key Risks */}
              {valueMetrics.valueProjection.risks.length > 0 && (
                <div class="collapse collapse-arrow bg-base-100">
                  <input type="checkbox" />
                  <div class="collapse-title text-sm font-medium">
                    Key Risks ({valueMetrics.valueProjection.risks.length})
                  </div>
                  <div class="collapse-content">
                    <ul class="text-sm space-y-1">
                      {valueMetrics.valueProjection.risks.map((risk, idx) => (
                        <li key={idx} class="flex items-start">
                          <span class="text-error mr-2">⚠</span>
                          <span>{risk}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Consolidated Score Breakdown */}
        {(qualityScoreBreakdown || demandScoreBreakdown ||
          availabilityScoreBreakdown) && (
          <>
            <button
              class="btn btn-outline btn-block btn-sm"
              onClick={() => {
                const newValue = !showQualityBreakdown.value;
                showQualityBreakdown.value = newValue;
                showDemandBreakdown.value = newValue;
                showAvailabilityBreakdown.value = newValue;
              }}
            >
              {showQualityBreakdown.value
                ? "▲ Hide Score Breakdown"
                : "▼ Show Score Breakdown"}
            </button>

            {showQualityBreakdown.value && (
              <div class="space-y-6 pt-4 border-t border-base-300">
                {/* Overall Data Completeness */}
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <p class="text-xs font-semibold text-base-content/60">
                      DATA COMPLETENESS
                    </p>
                    <span class="text-sm font-medium">
                      {(() => {
                        const scores = [
                          qualityScoreBreakdown
                            ? calculateQualityCompleteness()
                            : null,
                          demandScoreBreakdown
                            ? calculateDemandCompleteness()
                            : null,
                          availabilityScoreBreakdown
                            ? calculateAvailabilityCompleteness()
                            : null,
                        ].filter((s) => s !== null);
                        const avg = scores.length > 0
                          ? Math.round(
                            scores.reduce((a, b) => a! + b!, 0)! /
                              scores.length,
                          )
                          : 0;
                        return avg;
                      })()}%
                    </span>
                  </div>
                  <progress
                    class={`progress w-full ${
                      (() => {
                        const scores = [
                          qualityScoreBreakdown
                            ? calculateQualityCompleteness()
                            : null,
                          demandScoreBreakdown
                            ? calculateDemandCompleteness()
                            : null,
                          availabilityScoreBreakdown
                            ? calculateAvailabilityCompleteness()
                            : null,
                        ].filter((s) => s !== null);
                        const avg = scores.length > 0
                          ? Math.round(
                            scores.reduce((a, b) =>
                              a! + b!, 0)! /
                              scores.length,
                          )
                          : 0;
                        return avg === 100
                          ? "progress-success"
                          : avg >= 50
                          ? "progress-warning"
                          : "progress-error";
                      })()
                    }`}
                    value={(() => {
                      const scores = [
                        qualityScoreBreakdown
                          ? calculateQualityCompleteness()
                          : null,
                        demandScoreBreakdown
                          ? calculateDemandCompleteness()
                          : null,
                        availabilityScoreBreakdown
                          ? calculateAvailabilityCompleteness()
                          : null,
                      ].filter((s) => s !== null);
                      const avg = scores.length > 0
                        ? Math.round(
                          scores.reduce((a, b) => a! + b!, 0)! / scores.length,
                        )
                        : 0;
                      return avg;
                    })()}
                    max="100"
                  >
                  </progress>
                  {(() => {
                    const missing: string[] = [];
                    if (
                      qualityScoreBreakdown &&
                      calculateQualityCompleteness() < 100
                    ) {
                      if (!qualityScoreBreakdown.dataQuality.hasParts) {
                        missing.push("Parts Count");
                      }
                      if (!qualityScoreBreakdown.dataQuality.hasMsrp) {
                        missing.push("MSRP");
                      }
                      if (!qualityScoreBreakdown.dataQuality.hasTheme) {
                        missing
                          .push("Theme");
                      }
                      if (
                        !qualityScoreBreakdown.dataQuality.hasAvailability
                      ) missing.push("Availability");
                    }
                    if (
                      demandScoreBreakdown &&
                      calculateDemandCompleteness() < 100
                    ) {
                      if (
                        !demandScoreBreakdown.dataQuality.hasSalesData
                      ) missing.push("Sales Data");
                      if (
                        !demandScoreBreakdown.dataQuality.hasPriceData
                      ) missing.push("Price History");
                      if (
                        !demandScoreBreakdown.dataQuality.hasMarketDepth
                      ) missing.push("Market Depth");
                    }
                    if (availabilityScoreBreakdown?.missingData) {
                      missing.push(...availabilityScoreBreakdown.missingData);
                    }
                    return missing.length > 0 && (
                      <p class="text-xs text-base-content/60 mt-1">
                        Missing: {missing.join(", ")}
                      </p>
                    );
                  })()}
                </div>

                <p class="text-xs font-semibold text-base-content/60">
                  COMPONENT BREAKDOWN
                </p>

                {/* Quality Score Section */}
                {qualityScoreBreakdown && (
                  <div class="space-y-3">
                    <p class="text-sm font-bold text-base-content/80 border-b border-base-300 pb-2">
                      Quality Score
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
                          value={qualityScoreBreakdown.components.ppdScore
                            .score}
                          max="100"
                        >
                        </progress>
                        <span class="text-xs text-base-content/60">
                          → {qualityScoreBreakdown.components.ppdScore
                            .weightedScore
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
                          value={qualityScoreBreakdown.components
                            .complexityScore
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
                )}

                {/* Demand Score Section */}
                {demandScoreBreakdown && (
                  <div class="space-y-3">
                    <p class="text-sm font-bold text-base-content/80 border-b border-base-300 pb-2">
                      Demand Score
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
                          ({(demandScoreBreakdown.components.marketDepth
                            .weight *
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
                          {demandScoreBreakdown.components.supplyDemandRatio
                            .score
                            .toFixed(0)}/100
                        </span>
                      </div>
                      <div class="flex items-center gap-2">
                        <progress
                          class="progress progress-info flex-1"
                          value={demandScoreBreakdown.components
                            .supplyDemandRatio
                            .score}
                          max="100"
                        >
                        </progress>
                        <span class="text-xs text-base-content/60">
                          → {demandScoreBreakdown.components.supplyDemandRatio
                            .weightedScore.toFixed(1)} pts
                        </span>
                      </div>
                      {demandScoreBreakdown.components.supplyDemandRatio
                        .notes &&
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
                              demandScoreBreakdown.components
                                .velocityConsistency
                                .weightedScore,
                          )}/100
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Availability Score Section */}
                {availabilityScoreBreakdown && (
                  <div class="space-y-3">
                    <p class="text-sm font-bold text-base-content/80 border-b border-base-300 pb-2">
                      Availability Score
                    </p>

                    {availabilityScoreBreakdown.components.map((component) => {
                      const weightedScore = component.score * component.weight;
                      return (
                        <div
                          key={component.name}
                          class="bg-base-200 p-3 rounded-lg"
                        >
                          <div class="flex items-center justify-between mb-1">
                            <span class="text-sm font-medium">
                              {component.name}
                              ({(component.weight * 100).toFixed(0)}% weight)
                            </span>
                            <span class="text-sm font-bold">
                              {component.score.toFixed(0)}/100
                            </span>
                          </div>
                          <div class="flex items-center gap-2">
                            <progress
                              class="progress progress-accent flex-1"
                              value={component.score}
                              max="100"
                            >
                            </progress>
                            <span class="text-xs text-base-content/60">
                              → {weightedScore.toFixed(1)} pts
                            </span>
                          </div>
                          <p class="text-xs text-base-content/60 mt-1">
                            {component.calculation}
                          </p>
                          <p class="text-xs text-base-content/50 mt-1 italic">
                            {component.reasoning}
                          </p>
                        </div>
                      );
                    })}

                    {/* Total */}
                    <div class="bg-accent/10 border-2 border-accent p-3 rounded-lg">
                      <div class="flex items-center justify-between">
                        <span class="text-sm font-bold text-accent">
                          Total Availability Score
                        </span>
                        <span class="text-lg font-bold text-accent">
                          {availabilityScoreBreakdown.totalScore}/100
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Intrinsic Value Calculation Breakdown */}
        {valueMetrics.calculationBreakdown && (
          <>
            <button
              class="btn btn-outline btn-block btn-sm mt-4"
              onClick={() =>
                showIntrinsicBreakdown.value = !showIntrinsicBreakdown.value}
            >
              {showIntrinsicBreakdown.value
                ? "▲ Hide Intrinsic Value Calculation"
                : "▼ Show Intrinsic Value Calculation"}
            </button>

            {showIntrinsicBreakdown.value && (
              <div class="space-y-4 pt-4 border-t border-base-300">
                {/* Show rejection notice if set was rejected */}
                {valueMetrics.calculationBreakdown.rejection?.rejected ? (
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
                        d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                      />
                    </svg>
                    <div>
                      <h3 class="font-bold">VALUATION NOT PERFORMED</h3>
                      <div class="text-sm">
                        This set was rejected during hard gate screening. No intrinsic value calculation was performed.
                      </div>
                      <div class="text-xs mt-2 opacity-80">
                        Reason: {valueMetrics.calculationBreakdown.rejection.reason}
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div class="flex items-center gap-2 mb-4">
                      <div class="badge badge-info badge-sm">CALCULATION</div>
                      <h3 class="text-sm font-bold">
                        How We Calculated {formatCurrency(
                          valueMetrics.calculationBreakdown.finalIntrinsicValue,
                        )}
                      </h3>
                    </div>

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
                  <span class="text-sm">
                    Each multiplier is applied sequentially. Watch the running
                    total change step-by-step.
                  </span>
                </div>

                {/* Step-by-step calculation flow */}
                {(() => {
                  const breakdown = valueMetrics.calculationBreakdown;
                  let runningTotal = breakdown.baseValue;

                  const steps: Array<{
                    label: string;
                    multiplier: number;
                    newTotal: Cents;
                    explanation: string;
                    isApplied: boolean;
                    category: "base" | "quality" | "risk";
                  }> = [];

                  // Base Value
                  steps.push({
                    label: "Base Value (Starting Point)",
                    multiplier: 1,
                    newTotal: runningTotal,
                    explanation:
                      `Source: ${breakdown.baseValueSource.toUpperCase()} - ${breakdown.baseValueExplanation}`,
                    isApplied: true,
                    category: "base",
                  });

                  // Quality Multipliers
                  if (breakdown.qualityMultipliers.retirement.applied) {
                    const mult = breakdown.qualityMultipliers.retirement.value;
                    runningTotal = Math.round(runningTotal * mult) as Cents;
                    steps.push({
                      label: "Retirement Premium",
                      multiplier: mult,
                      newTotal: runningTotal,
                      explanation: breakdown.qualityMultipliers.retirement
                        .explanation,
                      isApplied: true,
                      category: "quality",
                    });
                  }

                  const qualityMult = breakdown.qualityMultipliers.quality
                    .value;
                  runningTotal = Math.round(
                    runningTotal * qualityMult,
                  ) as Cents;
                  steps.push({
                    label:
                      `Quality Score (${breakdown.qualityMultipliers.quality.score}/100)`,
                    multiplier: qualityMult,
                    newTotal: runningTotal,
                    explanation: breakdown.qualityMultipliers.quality
                      .explanation,
                    isApplied: true,
                    category: "quality",
                  });

                  const demandMult = breakdown.qualityMultipliers.demand.value;
                  runningTotal = Math.round(runningTotal * demandMult) as Cents;
                  steps.push({
                    label:
                      `Demand Score (${breakdown.qualityMultipliers.demand.score}/100)`,
                    multiplier: demandMult,
                    newTotal: runningTotal,
                    explanation: breakdown.qualityMultipliers.demand
                      .explanation,
                    isApplied: true,
                    category: "quality",
                  });

                  const themeMult = breakdown.qualityMultipliers.theme.value;
                  runningTotal = Math.round(runningTotal * themeMult) as Cents;
                  steps.push({
                    label:
                      `Theme: ${breakdown.qualityMultipliers.theme.themeName}`,
                    multiplier: themeMult,
                    newTotal: runningTotal,
                    explanation: breakdown.qualityMultipliers.theme
                      .explanation,
                    isApplied: true,
                    category: "quality",
                  });

                  const ppdMult = breakdown.qualityMultipliers.partsPerDollar
                    .value;
                  runningTotal = Math.round(runningTotal * ppdMult) as Cents;
                  steps.push({
                    label: `Parts-Per-Dollar${
                      breakdown.qualityMultipliers.partsPerDollar.ppdValue
                        ? ` (${
                          breakdown.qualityMultipliers.partsPerDollar.ppdValue
                            .toFixed(2)
                        })`
                        : ""
                    }`,
                    multiplier: ppdMult,
                    newTotal: runningTotal,
                    explanation: breakdown.qualityMultipliers.partsPerDollar
                      .explanation,
                    isApplied: true,
                    category: "quality",
                  });

                  // Mark intermediate value after quality multipliers
                  const afterQualityIndex = steps.length - 1;

                  // Risk Discounts
                  if (breakdown.riskDiscounts.liquidity.applied) {
                    const mult = breakdown.riskDiscounts.liquidity.value;
                    runningTotal = Math.round(runningTotal * mult) as Cents;
                    steps.push({
                      label: "Liquidity Discount",
                      multiplier: mult,
                      newTotal: runningTotal,
                      explanation: breakdown.riskDiscounts.liquidity
                        .explanation,
                      isApplied: true,
                      category: "risk",
                    });
                  }

                  if (breakdown.riskDiscounts.volatility.applied) {
                    const mult = breakdown.riskDiscounts.volatility.value;
                    runningTotal = Math.round(runningTotal * mult) as Cents;
                    steps.push({
                      label: `Volatility Discount${
                        breakdown.riskDiscounts.volatility.volatilityPercent
                          ? ` (${
                            (breakdown.riskDiscounts.volatility
                              .volatilityPercent * 100).toFixed(0)
                          }% volatility)`
                          : ""
                      }`,
                      multiplier: mult,
                      newTotal: runningTotal,
                      explanation: breakdown.riskDiscounts.volatility
                        .explanation,
                      isApplied: true,
                      category: "risk",
                    });
                  }

                  if (breakdown.riskDiscounts.saturation.applied) {
                    const mult = breakdown.riskDiscounts.saturation.value;
                    runningTotal = Math.round(runningTotal * mult) as Cents;
                    steps.push({
                      label: "Market Saturation Discount",
                      multiplier: mult,
                      newTotal: runningTotal,
                      explanation: breakdown.riskDiscounts.saturation
                        .explanation,
                      isApplied: true,
                      category: "risk",
                    });
                  }

                  if (breakdown.riskDiscounts.zeroSales.applied) {
                    const mult = breakdown.riskDiscounts.zeroSales.value;
                    runningTotal = Math.round(runningTotal * mult) as Cents;
                    steps.push({
                      label: "Zero Sales Penalty",
                      multiplier: mult,
                      newTotal: runningTotal,
                      explanation: breakdown.riskDiscounts.zeroSales
                        .explanation,
                      isApplied: true,
                      category: "risk",
                    });
                  }

                  return (
                    <div class="space-y-3">
                      {steps.map((step, index) => {
                        const isBase = step.category === "base";
                        const isQuality = step.category === "quality";
                        const isAfterQuality = index === afterQualityIndex;
                        const isFinal = index === steps.length - 1;

                        return (
                          <div key={index}>
                            <div
                              class={`p-4 rounded-lg border-2 ${
                                isBase
                                  ? "bg-info/10 border-info"
                                  : isQuality
                                  ? "bg-success/5 border-success/30"
                                  : "bg-error/5 border-error/30"
                              }`}
                            >
                              {/* Step Header */}
                              <div class="flex items-start justify-between mb-2">
                                <div class="flex-1">
                                  <div class="flex items-center gap-2 mb-1">
                                    <span
                                      class={`badge badge-sm ${
                                        isBase
                                          ? "badge-info"
                                          : isQuality
                                          ? "badge-success"
                                          : "badge-error"
                                      }`}
                                    >
                                      {isBase
                                        ? "START"
                                        : isQuality
                                        ? "MULTIPLY"
                                        : "DISCOUNT"}
                                    </span>
                                    <span class="text-sm font-bold">
                                      {isBase ? "" : `Step ${index}`}
                                    </span>
                                  </div>
                                  <p class="text-sm font-medium">
                                    {step.label}
                                  </p>
                                </div>
                                {!isBase && (
                                  <span
                                    class={`text-lg font-bold font-mono ${
                                      isQuality ? "text-success" : "text-error"
                                    }`}
                                  >
                                    ×{step.multiplier.toFixed(3)}
                                  </span>
                                )}
                              </div>

                              {/* Calculation Formula */}
                              {!isBase && (
                                <div class="bg-base-100/50 p-2 rounded mb-2 font-mono text-xs">
                                  <span class="text-base-content/60">
                                    {formatCurrency(
                                      steps[index - 1].newTotal,
                                    )}
                                  </span>
                                  {" × "}
                                  <span
                                    class={isQuality
                                      ? "text-success font-bold"
                                      : "text-error font-bold"}
                                  >
                                    {step.multiplier.toFixed(3)}
                                  </span>
                                  {" = "}
                                  <span class="text-base-content font-bold">
                                    {formatCurrency(step.newTotal)}
                                  </span>
                                </div>
                              )}

                              {/* Running Total */}
                              <div
                                class={`flex items-center justify-between p-3 rounded ${
                                  isBase || isAfterQuality || isFinal
                                    ? "bg-base-100 border-2 border-dashed border-base-content/20"
                                    : "bg-base-100/30"
                                }`}
                              >
                                <span class="text-xs font-semibold text-base-content/70">
                                  {isBase
                                    ? "Starting Value:"
                                    : isAfterQuality
                                    ? "After Quality Multipliers:"
                                    : isFinal
                                    ? "FINAL INTRINSIC VALUE:"
                                    : "Running Total:"}
                                </span>
                                <span
                                  class={`font-mono font-bold ${
                                    isBase || isAfterQuality || isFinal
                                      ? "text-lg text-info"
                                      : "text-sm"
                                  }`}
                                >
                                  {formatCurrency(step.newTotal)}
                                </span>
                              </div>

                              {/* Explanation */}
                              <p class="text-xs text-base-content/60 mt-2">
                                {step.explanation}
                              </p>

                              {/* Additional breakdown for Quality and Demand scores */}
                              {step.label.includes("Quality Score") &&
                                qualityScoreBreakdown && (
                                <div class="mt-3 pt-3 border-t border-base-300">
                                  <p class="text-xs font-semibold text-base-content/70 mb-2">
                                    Quality Score Components:
                                  </p>
                                  <div class="space-y-1 pl-2 border-l-2 border-success/30">
                                    <p class="text-xs text-base-content/60">
                                      • PPD: {qualityScoreBreakdown.components
                                        .ppdScore.weightedScore.toFixed(
                                          1,
                                        )}/40pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Complexity: {qualityScoreBreakdown
                                        .components
                                        .complexityScore.weightedScore.toFixed(
                                          1,
                                        )}/30pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Theme: {qualityScoreBreakdown.components
                                        .themePremium.weightedScore.toFixed(
                                          1,
                                        )}/20pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Scarcity: {qualityScoreBreakdown
                                        .components
                                        .scarcityScore.weightedScore.toFixed(
                                          1,
                                        )}/10pts
                                    </p>
                                    <p class="text-xs text-base-content/50 italic mt-1">
                                      See "Score Breakdown" above for details
                                    </p>
                                  </div>
                                </div>
                              )}

                              {step.label.includes("Demand Score") &&
                                demandScoreBreakdown && (
                                <div class="mt-3 pt-3 border-t border-base-300">
                                  <p class="text-xs font-semibold text-base-content/70 mb-2">
                                    Demand Score Components:
                                  </p>
                                  <div class="space-y-1 pl-2 border-l-2 border-success/30">
                                    <p class="text-xs text-base-content/60">
                                      • Sales Velocity: {demandScoreBreakdown
                                        .components
                                        .salesVelocity.weightedScore.toFixed(
                                          1,
                                        )}pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Price Momentum: {demandScoreBreakdown
                                        .components
                                        .priceMomentum.weightedScore.toFixed(
                                          1,
                                        )}pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Market Depth: {demandScoreBreakdown
                                        .components
                                        .marketDepth.weightedScore.toFixed(
                                          1,
                                        )}pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Supply/Demand: {demandScoreBreakdown
                                        .components
                                        .supplyDemandRatio.weightedScore
                                        .toFixed(1)}pts
                                    </p>
                                    <p class="text-xs text-base-content/60">
                                      • Consistency: {demandScoreBreakdown
                                        .components
                                        .velocityConsistency.weightedScore
                                        .toFixed(1)}pts
                                    </p>
                                    <p class="text-xs text-base-content/50 italic mt-1">
                                      See "Score Breakdown" above for details
                                    </p>
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Arrow between steps */}
                            {index < steps.length - 1 && (
                              <div class="flex justify-center py-1">
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  class="h-6 w-6 text-base-content/30"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    stroke-width="2"
                                    d="M19 14l-7 7m0 0l-7-7m7 7V3"
                                  />
                                </svg>
                              </div>
                            )}
                          </div>
                        );
                      })}

                      {/* Summary */}
                      <div class="bg-gradient-to-r from-info/20 to-info/10 border-2 border-info p-4 rounded-lg mt-4">
                        <p class="text-sm font-bold text-info mb-2">
                          Calculation Summary
                        </p>
                        <div class="grid grid-cols-2 gap-3 text-xs">
                          <div>
                            <p class="text-base-content/60">Base Value:</p>
                            <p class="font-mono font-bold">
                              {formatCurrency(breakdown.baseValue)}
                            </p>
                          </div>
                          <div>
                            <p class="text-base-content/60">
                              Total Multiplier:
                            </p>
                            <p class="font-mono font-bold">
                              {breakdown.totalMultiplier.toFixed(3)}x
                            </p>
                          </div>
                          <div class="col-span-2">
                            <p class="text-base-content/60">
                              Formula: Base × All Multipliers × All Discounts
                            </p>
                            <p class="font-mono font-bold text-info text-base mt-1">
                              = {formatCurrency(
                                breakdown.finalIntrinsicValue,
                              )}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}
                  </>
                )}
              </div>
            )}
          </>
        )}

        {/* Analysis Timestamp */}
        <p class="text-xs text-base-content/50 text-center pt-4 border-t border-base-300">
          Analyzed: {new Date(analyzedAt).toLocaleString()}
        </p>
      </div>
    </div>
  );
}

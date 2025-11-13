/**
 * ProductAnalysisCard - Interactive island for displaying product analysis
 * Shows multi-dimensional breakdown with strategy selector
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import ScoreMeter from "../components/analysis/ScoreMeter.tsx";
import RecommendationBadge from "../components/analysis/RecommendationBadge.tsx";

interface AnalysisScore {
  value: number;
  confidence: number;
  reasoning: string;
  dataPoints: Record<string, unknown>;
}

interface DimensionalScores {
  demand: AnalysisScore | null;
  availability: AnalysisScore | null;
  quality: AnalysisScore | null;
}

interface ProductRecommendation {
  overall: AnalysisScore;
  dimensions: DimensionalScores;
  availableDimensions: number;
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  strategy: string;
  urgency: "urgent" | "moderate" | "low" | "no_rush";
  estimatedROI?: number;
  timeHorizon?: string;
  recommendedBuyPrice?: {
    price: number;
    reasoning: string;
    confidence: number;
  };
  risks: string[];
  opportunities: string[];
  analyzedAt: string;
}

interface Strategy {
  name: string;
  description: string;
}

interface ProductAnalysisCardProps {
  productId: string;
  defaultStrategy?: string;
}

export default function ProductAnalysisCard(
  { productId, defaultStrategy = "Investment Focus" }: ProductAnalysisCardProps,
) {
  const loading = useSignal(true);
  const error = useSignal<string | null>(null);
  const recommendation = useSignal<ProductRecommendation | null>(null);
  const strategies = useSignal<Strategy[]>([]);
  const selectedStrategy = useSignal(defaultStrategy);
  const showDetails = useSignal(false);

  // Fetch available strategies
  useEffect(() => {
    fetch("/api/analysis/strategies")
      .then((res) => res.json())
      .then((data) => {
        strategies.value = data.strategies;
      })
      .catch((err) => {
        console.error("Failed to fetch strategies:", err);
      });
  }, []);

  // Fetch analysis when strategy changes
  useEffect(() => {
    loading.value = true;
    error.value = null;

    fetch(
      `/api/analysis/${productId}?strategy=${
        encodeURIComponent(selectedStrategy.value)
      }`,
    )
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        recommendation.value = data;
        loading.value = false;
      })
      .catch((err) => {
        error.value = err.message;
        loading.value = false;
      });
  }, [productId, selectedStrategy.value]);

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

  if (!recommendation.value) return null;

  const rec = recommendation.value;

  return (
    <div class="card bg-base-100 shadow-xl">
      <div class="card-body space-y-6">
        {/* Header with Strategy Selector */}
        <div class="flex items-start justify-between">
          <div>
            <h3 class="text-xl font-bold mb-2">
              Investment Analysis
            </h3>
            <p class="text-sm text-base-content/70">
              Strategy: {rec.strategy}
            </p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <select
              class="select select-bordered select-sm"
              value={selectedStrategy.value}
              onChange={(e) =>
                selectedStrategy.value = (e.target as HTMLSelectElement).value}
            >
              {strategies.value.map((strategy) => (
                <option key={strategy.name} value={strategy.name}>
                  {strategy.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Overall Score and Recommendation */}
        {rec.availableDimensions === 3
          ? (
            <div class="flex items-center gap-6 p-4 bg-base-200 rounded-lg">
              <div class="flex-1">
                <ScoreMeter
                  score={rec.overall.value}
                  label="Overall Score"
                  size="lg"
                />
                <p class="text-sm text-base-content/70 mt-2">
                  Confidence: {Math.round(rec.overall.confidence * 100)}%
                </p>
              </div>
              <div class="flex-shrink-0">
                <RecommendationBadge
                  action={rec.action}
                  urgency={rec.urgency}
                  size="lg"
                />
              </div>
            </div>
          )
          : (
            <div class="p-6 bg-warning/10 border-2 border-warning rounded-lg">
              <div class="flex items-start gap-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="h-6 w-6 text-warning flex-shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <h4 class="font-semibold text-warning mb-2">
                    Not Enough Data Yet
                  </h4>
                  <p class="text-sm text-base-content/80">
                    We need {3 - rec.availableDimensions} more dimension{3 -
                          rec.availableDimensions !== 1
                      ? "s"
                      : ""}{" "}
                    to provide a reliable score. Check back after we gather more
                    information about this product.
                  </p>
                  <p class="text-xs text-base-content/60 mt-2">
                    Currently analyzed: {rec.availableDimensions}{" "}
                    of 3 dimensions
                  </p>
                </div>
              </div>
            </div>
          )}

        {/* Investment Metrics */}
        {rec.availableDimensions === 3 &&
          (rec.recommendedBuyPrice || rec.timeHorizon) && (
          <div class="space-y-4">
            {rec.recommendedBuyPrice && (
              <div class="p-4 bg-success/10 border-2 border-success rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <p class="text-sm font-semibold text-success">
                    💰 Recommended Buy Price
                  </p>
                  <p class="text-xs text-success/70">
                    {Math.round(rec.recommendedBuyPrice.confidence * 100)}%
                    confidence
                  </p>
                </div>
                <p class="text-3xl font-bold text-success mb-2">
                  ${rec.recommendedBuyPrice.price.toFixed(2)} or below
                </p>
                <p class="text-xs text-base-content/70">
                  {rec.recommendedBuyPrice.reasoning}
                </p>
              </div>
            )}
            {rec.timeHorizon && (
              <div class="p-4 bg-primary/10 rounded-lg">
                <p class="text-xs text-primary font-medium mb-1">
                  Time Horizon
                </p>
                <p class="text-sm font-semibold">
                  {rec.timeHorizon}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Dimensional Scores */}
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="font-semibold">Dimensional Analysis</h4>
            <p class="text-xs text-base-content/50">
              {rec.availableDimensions} of 3 dimensions analyzed
            </p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            {rec.dimensions.demand
              ? (
                <div>
                  <ScoreMeter
                    score={rec.dimensions.demand.value}
                    label="📈 Demand"
                    size="md"
                  />
                  <p class="text-xs text-base-content/70 mt-1">
                    {rec.dimensions.demand.reasoning}
                  </p>
                </div>
              )
              : (
                <div class="opacity-50">
                  <div class="p-4 bg-base-200 rounded-lg">
                    <p class="text-sm font-medium text-base-content/50">
                      📈 Demand
                    </p>
                    <p class="text-xs text-base-content/40 mt-1">
                      Insufficient data
                    </p>
                  </div>
                </div>
              )}
            {rec.dimensions.availability
              ? (
                <div>
                  <ScoreMeter
                    score={rec.dimensions.availability.value}
                    label="📦 Availability"
                    size="md"
                  />
                  <p class="text-xs text-base-content/70 mt-1">
                    {rec.dimensions.availability.reasoning}
                  </p>
                </div>
              )
              : (
                <div class="opacity-50">
                  <div class="p-4 bg-base-200 rounded-lg">
                    <p class="text-sm font-medium text-base-content/50">
                      📦 Availability
                    </p>
                    <p class="text-xs text-base-content/40 mt-1">
                      Insufficient data
                    </p>
                  </div>
                </div>
              )}
            {rec.dimensions.quality
              ? (
                <div>
                  <ScoreMeter
                    score={rec.dimensions.quality.value}
                    label="⭐ Quality"
                    size="md"
                  />
                  <p class="text-xs text-base-content/70 mt-1">
                    {rec.dimensions.quality.reasoning}
                  </p>
                </div>
              )
              : (
                <div class="opacity-50">
                  <div class="p-4 bg-base-200 rounded-lg">
                    <p class="text-sm font-medium text-base-content/50">
                      ⭐ Quality
                    </p>
                    <p class="text-xs text-base-content/40 mt-1">
                      Insufficient data
                    </p>
                  </div>
                </div>
              )}
          </div>
        </div>

        {/* Opportunities and Risks Toggle */}
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
            {rec.opportunities.length > 0 && (
              <div>
                <h5 class="font-semibold text-success mb-2">
                  ✅ Opportunities
                </h5>
                <ul class="space-y-1">
                  {rec.opportunities.map((opp, idx) => (
                    <li key={idx} class="text-sm flex items-start">
                      <span class="text-success mr-2">•</span>
                      <span>{opp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risks */}
            {rec.risks.length > 0 && (
              <div>
                <h5 class="font-semibold text-error mb-2">⚠️ Risks</h5>
                <ul class="space-y-1">
                  {rec.risks.map((risk, idx) => (
                    <li key={idx} class="text-sm flex items-start">
                      <span class="text-error mr-2">•</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Analysis Timestamp */}
            <p class="text-xs text-base-content/50 mt-4">
              Analyzed: {new Date(rec.analyzedAt).toLocaleString()}
            </p>
          </div>
        )}

        {/* Overall Reasoning */}
        <div class="p-4 bg-base-200 rounded-lg">
          <p class="text-sm">
            <span class="font-semibold">Summary:</span>
            {rec.overall.reasoning}
          </p>
        </div>
      </div>
    </div>
  );
}

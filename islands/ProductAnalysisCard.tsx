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
  pricing: AnalysisScore | null;
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
      <div class="bg-white rounded-lg shadow-md p-6 animate-pulse">
        <div class="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div class="h-4 bg-gray-200 rounded w-full mb-2"></div>
        <div class="h-4 bg-gray-200 rounded w-2/3"></div>
      </div>
    );
  }

  if (error.value) {
    return (
      <div class="bg-red-50 border border-red-200 rounded-lg p-6">
        <h3 class="text-red-800 font-semibold mb-2">Analysis Error</h3>
        <p class="text-red-600">{error.value}</p>
      </div>
    );
  }

  if (!recommendation.value) return null;

  const rec = recommendation.value;

  return (
    <div class="bg-white rounded-lg shadow-md p-6 space-y-6">
      {/* Header with Strategy Selector */}
      <div class="flex items-start justify-between">
        <div>
          <h3 class="text-xl font-bold text-gray-900 mb-2">
            Investment Analysis
          </h3>
          <p class="text-sm text-gray-600">
            Strategy: {rec.strategy}
          </p>
        </div>
        <div class="flex flex-col items-end gap-2">
          <select
            class="px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
      <div class="flex items-center gap-6 p-4 bg-gray-50 rounded-lg">
        <div class="flex-1">
          <ScoreMeter
            score={rec.overall.value}
            label="Overall Score"
            size="lg"
          />
          <p class="text-sm text-gray-600 mt-2">
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

      {/* Investment Metrics */}
      {(rec.estimatedROI !== undefined || rec.timeHorizon) && (
        <div class="grid grid-cols-2 gap-4 p-4 bg-blue-50 rounded-lg">
          {rec.estimatedROI !== undefined && (
            <div>
              <p class="text-xs text-blue-700 font-medium mb-1">
                Estimated ROI
              </p>
              <p class="text-2xl font-bold text-blue-900">
                {rec.estimatedROI > 0 ? "+" : ""}
                {rec.estimatedROI.toFixed(0)}%
              </p>
            </div>
          )}
          {rec.timeHorizon && (
            <div>
              <p class="text-xs text-blue-700 font-medium mb-1">
                Time Horizon
              </p>
              <p class="text-sm font-semibold text-blue-900">
                {rec.timeHorizon}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Dimensional Scores */}
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h4 class="font-semibold text-gray-900">Dimensional Analysis</h4>
          <p class="text-xs text-gray-500">
            {rec.availableDimensions} of 4 dimensions analyzed
          </p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rec.dimensions.pricing
            ? (
              <div>
                <ScoreMeter
                  score={rec.dimensions.pricing.value}
                  label="💰 Pricing"
                  size="md"
                />
                <p class="text-xs text-gray-600 mt-1">
                  {rec.dimensions.pricing.reasoning}
                </p>
              </div>
            )
            : (
              <div class="opacity-50">
                <div class="p-4 bg-gray-100 rounded-lg">
                  <p class="text-sm font-medium text-gray-500">💰 Pricing</p>
                  <p class="text-xs text-gray-400 mt-1">
                    Insufficient data
                  </p>
                </div>
              </div>
            )}
          {rec.dimensions.demand
            ? (
              <div>
                <ScoreMeter
                  score={rec.dimensions.demand.value}
                  label="📈 Demand"
                  size="md"
                />
                <p class="text-xs text-gray-600 mt-1">
                  {rec.dimensions.demand.reasoning}
                </p>
              </div>
            )
            : (
              <div class="opacity-50">
                <div class="p-4 bg-gray-100 rounded-lg">
                  <p class="text-sm font-medium text-gray-500">📈 Demand</p>
                  <p class="text-xs text-gray-400 mt-1">
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
                <p class="text-xs text-gray-600 mt-1">
                  {rec.dimensions.availability.reasoning}
                </p>
              </div>
            )
            : (
              <div class="opacity-50">
                <div class="p-4 bg-gray-100 rounded-lg">
                  <p class="text-sm font-medium text-gray-500">
                    📦 Availability
                  </p>
                  <p class="text-xs text-gray-400 mt-1">
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
                <p class="text-xs text-gray-600 mt-1">
                  {rec.dimensions.quality.reasoning}
                </p>
              </div>
            )
            : (
              <div class="opacity-50">
                <div class="p-4 bg-gray-100 rounded-lg">
                  <p class="text-sm font-medium text-gray-500">⭐ Quality</p>
                  <p class="text-xs text-gray-400 mt-1">
                    Insufficient data
                  </p>
                </div>
              </div>
            )}
        </div>
      </div>

      {/* Opportunities and Risks Toggle */}
      <button
        class="w-full py-2 px-4 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium text-gray-700 transition-colors"
        onClick={() => showDetails.value = !showDetails.value}
      >
        {showDetails.value ? "▲ Hide Details" : "▼ Show Opportunities & Risks"}
      </button>

      {/* Details Section */}
      {showDetails.value && (
        <div class="space-y-4 pt-4 border-t border-gray-200">
          {/* Opportunities */}
          {rec.opportunities.length > 0 && (
            <div>
              <h5 class="font-semibold text-green-800 mb-2">
                ✅ Opportunities
              </h5>
              <ul class="space-y-1">
                {rec.opportunities.map((opp, idx) => (
                  <li key={idx} class="text-sm text-gray-700 flex items-start">
                    <span class="text-green-600 mr-2">•</span>
                    <span>{opp}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risks */}
          {rec.risks.length > 0 && (
            <div>
              <h5 class="font-semibold text-red-800 mb-2">⚠️ Risks</h5>
              <ul class="space-y-1">
                {rec.risks.map((risk, idx) => (
                  <li key={idx} class="text-sm text-gray-700 flex items-start">
                    <span class="text-red-600 mr-2">•</span>
                    <span>{risk}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Analysis Timestamp */}
          <p class="text-xs text-gray-500 mt-4">
            Analyzed: {new Date(rec.analyzedAt).toLocaleString()}
          </p>
        </div>
      )}

      {/* Overall Reasoning */}
      <div class="p-4 bg-gray-50 rounded-lg">
        <p class="text-sm text-gray-700">
          <span class="font-semibold">Summary:</span>
          {rec.overall.reasoning}
        </p>
      </div>
    </div>
  );
}

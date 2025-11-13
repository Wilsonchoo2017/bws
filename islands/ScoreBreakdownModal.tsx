/**
 * ScoreBreakdownModal - Modal for displaying detailed score calculation breakdown
 * Shows components, weights, formulas, and all data used in analysis
 */

import { Signal } from "@preact/signals";

interface ScoreComponent {
  name: string;
  weight: number;
  score: number;
  rawValue?: number | string;
  calculation: string;
  reasoning: string;
}

interface ScoreBreakdown {
  components: ScoreComponent[];
  formula: string;
  totalScore: number;
  dataPoints: Record<string, unknown>;
  missingData?: string[];
}

interface AnalysisScore {
  value: number;
  confidence: number;
  reasoning: string;
  dataPoints: Record<string, unknown>;
  breakdown?: ScoreBreakdown;
}

interface ScoreBreakdownModalProps {
  isOpen: Signal<boolean>;
  dimensionName: string;
  dimensionScore: AnalysisScore | null;
  dimensionIcon: string;
}

export default function ScoreBreakdownModal(
  { isOpen, dimensionName, dimensionScore, dimensionIcon }:
    ScoreBreakdownModalProps,
) {
  if (!isOpen.value || !dimensionScore || !dimensionScore.breakdown) {
    return null;
  }

  const breakdown = dimensionScore.breakdown;

  return (
    <div class="modal modal-open">
      <div class="modal-box max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <span class="text-3xl">{dimensionIcon}</span>
            <div>
              <h3 class="font-bold text-2xl">{dimensionName} Analysis</h3>
              <p class="text-sm text-base-content/70">
                Detailed calculation breakdown
              </p>
            </div>
          </div>
          <button
            class="btn btn-sm btn-circle btn-ghost"
            onClick={() => isOpen.value = false}
          >
            ✕
          </button>
        </div>

        {/* Overall Score */}
        <div class="p-4 bg-primary/10 rounded-lg mb-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-primary/70 font-medium">Total Score</p>
              <p class="text-4xl font-bold text-primary">
                {breakdown.totalScore}
                <span class="text-xl">/100</span>
              </p>
            </div>
            <div class="text-right">
              <p class="text-xs text-base-content/70">Confidence</p>
              <p class="text-2xl font-semibold">
                {Math.round(dimensionScore.confidence * 100)}%
              </p>
            </div>
          </div>
        </div>

        {/* Formula */}
        <div class="mb-6">
          <h4 class="font-semibold text-sm text-base-content/70 mb-2">
            CALCULATION FORMULA
          </h4>
          <div class="p-3 bg-base-200 rounded font-mono text-sm">
            {breakdown.formula}
          </div>
        </div>

        {/* Components Breakdown */}
        <div class="mb-6">
          <h4 class="font-semibold text-sm text-base-content/70 mb-3">
            SCORE COMPONENTS
          </h4>
          <div class="space-y-3">
            {breakdown.components.map((component, idx) => (
              <details key={idx} class="collapse collapse-arrow bg-base-200">
                <summary class="collapse-title font-medium">
                  <div class="flex items-center justify-between pr-12">
                    <div class="flex items-center gap-3">
                      <div class="badge badge-primary">
                        {(component.weight * 100).toFixed(0)}%
                      </div>
                      <span>{component.name}</span>
                    </div>
                    <div class="flex items-center gap-2">
                      {component.rawValue && (
                        <span class="text-xs text-base-content/50">
                          {component.rawValue}
                        </span>
                      )}
                      <span class="font-bold text-primary">
                        {component.score.toFixed(1)}
                      </span>
                    </div>
                  </div>
                </summary>
                <div class="collapse-content space-y-3">
                  {/* Calculation */}
                  <div>
                    <p class="text-xs font-semibold text-base-content/60 mb-1">
                      Calculation:
                    </p>
                    <p class="text-sm bg-base-300 p-2 rounded">
                      {component.calculation}
                    </p>
                  </div>

                  {/* Reasoning */}
                  <div>
                    <p class="text-xs font-semibold text-base-content/60 mb-1">
                      Why it matters:
                    </p>
                    <p class="text-sm text-base-content/80">
                      {component.reasoning}
                    </p>
                  </div>

                  {/* Impact on final score */}
                  <div class="stats shadow w-full">
                    <div class="stat py-2 px-3">
                      <div class="stat-title text-xs">Component Score</div>
                      <div class="stat-value text-lg">
                        {component.score.toFixed(1)}
                      </div>
                    </div>
                    <div class="stat py-2 px-3">
                      <div class="stat-title text-xs">Weight</div>
                      <div class="stat-value text-lg">
                        {(component.weight * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div class="stat py-2 px-3">
                      <div class="stat-title text-xs">Contribution</div>
                      <div class="stat-value text-lg text-primary">
                        {(component.score * component.weight).toFixed(1)}
                      </div>
                    </div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </div>

        {/* Missing Data */}
        {breakdown.missingData && breakdown.missingData.length > 0 && (
          <div class="mb-6">
            <h4 class="font-semibold text-sm text-base-content/70 mb-3">
              MISSING DATA
            </h4>
            <div class="p-3 bg-warning/10 border border-warning/30 rounded">
              <ul class="text-sm space-y-1">
                {breakdown.missingData.map((data, idx) => (
                  <li key={idx} class="flex items-start gap-2">
                    <span class="text-warning">⚠</span>
                    <span>{data}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Data Points Used */}
        <div>
          <h4 class="font-semibold text-sm text-base-content/70 mb-3">
            RAW DATA POINTS
          </h4>
          <details class="collapse collapse-arrow bg-base-200">
            <summary class="collapse-title text-sm">
              View all data points ({Object.keys(breakdown.dataPoints).length})
            </summary>
            <div class="collapse-content">
              <div class="overflow-x-auto">
                <table class="table table-xs">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(breakdown.dataPoints).map(([key, value]) => (
                      <tr key={key}>
                        <td class="font-mono text-xs">{key}</td>
                        <td class="text-xs">
                          {typeof value === "object"
                            ? JSON.stringify(value)
                            : String(value)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </details>
        </div>

        {/* Close Button */}
        <div class="modal-action">
          <button
            class="btn btn-primary"
            onClick={() => isOpen.value = false}
          >
            Close
          </button>
        </div>
      </div>

      {/* Backdrop */}
      <div class="modal-backdrop" onClick={() => isOpen.value = false}>
      </div>
    </div>
  );
}

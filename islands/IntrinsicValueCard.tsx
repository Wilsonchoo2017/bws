/**
 * IntrinsicValueCard - Interactive island for displaying intrinsic value analysis
 * Shows value investing metrics consistently across the application
 */

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

interface ValueMetrics {
  currentPrice: number;
  targetPrice: number;
  intrinsicValue: number;
  realizedValue?: number;
  marginOfSafety: number;
  expectedROI: number;
  realizedROI?: number;
  timeHorizon: string;
}

interface IntrinsicValueData {
  valueMetrics: ValueMetrics;
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  risks: string[];
  opportunities: string[];
  analyzedAt: string;
  currency: string;
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

  const { valueMetrics, action, risks, opportunities, analyzedAt, currency } =
    data.value;

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
    }).format(amount);
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
        return (
          <div class="badge badge-ghost badge-lg">INSUFFICIENT DATA</div>
        );
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

        {/* Analysis Timestamp */}
        <p class="text-xs text-base-content/50 text-center pt-4 border-t border-base-300">
          Analyzed: {new Date(analyzedAt).toLocaleString()}
        </p>
      </div>
    </div>
  );
}

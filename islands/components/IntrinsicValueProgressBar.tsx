import { type JSX } from "preact";

interface IntrinsicValueProgressBarProps {
  currentPriceCents: number;
  intrinsicValueCents: number;
}

export function IntrinsicValueProgressBar(
  { currentPriceCents, intrinsicValueCents }: IntrinsicValueProgressBarProps,
): JSX.Element {
  // Calculate distance from intrinsic value
  const distancePercent = intrinsicValueCents > 0
    ? ((currentPriceCents - intrinsicValueCents) / intrinsicValueCents) * 100
    : 0;

  // Determine color class based on distance
  let progressClass = "progress-success"; // Green - below intrinsic (good buy)
  let textColorClass = "text-success";
  let bgColorClass = "bg-success/10";

  if (distancePercent > 15) {
    // More than 15% above intrinsic value - overpriced
    progressClass = "progress-error";
    textColorClass = "text-error";
    bgColorClass = "bg-error/10";
  } else if (distancePercent > 5) {
    // 5-15% above intrinsic value - slightly overpriced
    progressClass = "progress-warning";
    textColorClass = "text-warning";
    bgColorClass = "bg-warning/10";
  } else if (distancePercent > -5) {
    // Within ±5% of intrinsic value - fair price
    progressClass = "progress-info";
    textColorClass = "text-info";
    bgColorClass = "bg-info/10";
  }

  // Calculate progress bar value (0-100)
  // Map distance from -50% to +50% onto 0-100 scale
  // -50% = 0 (far below intrinsic - great buy)
  // 0% = 50 (at intrinsic value)
  // +50% = 100 (far above intrinsic - overpriced)
  const clampedDistance = Math.max(-50, Math.min(50, distancePercent));
  const progressValue = ((clampedDistance + 50) / 100) * 100;

  // Format the distance percentage
  const formattedDistance = distancePercent > 0
    ? `+${distancePercent.toFixed(1)}%`
    : `${distancePercent.toFixed(1)}%`;

  return (
    <div class="flex items-center gap-3">
      <div class="flex-1 min-w-0">
        <progress
          class={`progress ${progressClass} w-full`}
          value={progressValue}
          max="100"
        >
        </progress>
        <div class="text-xs text-gray-500 mt-0.5">
          {distancePercent < 0
            ? "Below intrinsic"
            : distancePercent === 0
            ? "At intrinsic"
            : "Above intrinsic"}
        </div>
      </div>
      <div class={`badge ${bgColorClass} ${textColorClass} font-semibold`}>
        {formattedDistance}
      </div>
    </div>
  );
}

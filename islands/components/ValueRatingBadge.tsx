import { ValueCalculator } from "../../services/value-investing/ValueCalculator.ts";

interface ValueRatingBadgeProps {
  marginOfSafety: number;
}

/**
 * ValueRatingBadge - Displays value investing rating badge
 *
 * Shows the investment rating based on margin of safety percentage
 * Following separation of concerns - pure presentation component
 */
export function ValueRatingBadge({ marginOfSafety }: ValueRatingBadgeProps) {
  const { rating, color } = ValueCalculator.getValueRating(marginOfSafety);

  return (
    <span class={`badge badge-${color} badge-sm`}>
      {rating}
    </span>
  );
}

/**
 * RecommendationBadge - Color-coded badge for buy/hold/pass actions
 */

interface RecommendationBadgeProps {
  action: "strong_buy" | "buy" | "hold" | "pass" | "insufficient_data";
  urgency?: "urgent" | "moderate" | "low" | "no_rush";
  size?: "sm" | "md" | "lg";
}

export default function RecommendationBadge(
  { action, urgency, size = "md" }: RecommendationBadgeProps,
) {
  // Action styling
  const getActionStyle = (action: string): string => {
    switch (action) {
      case "strong_buy":
        return "bg-green-600 text-white border-green-700";
      case "buy":
        return "bg-green-500 text-white border-green-600";
      case "hold":
        return "bg-yellow-500 text-white border-yellow-600";
      case "pass":
        return "bg-red-500 text-white border-red-600";
      case "insufficient_data":
        return "bg-gray-400 text-white border-gray-500";
      default:
        return "bg-gray-500 text-white border-gray-600";
    }
  };

  const getActionLabel = (action: string): string => {
    switch (action) {
      case "strong_buy":
        return "STRONG BUY";
      case "buy":
        return "BUY";
      case "hold":
        return "HOLD";
      case "pass":
        return "PASS";
      case "insufficient_data":
        return "INSUFFICIENT DATA";
      default:
        return "UNKNOWN";
    }
  };

  // Urgency styling
  const getUrgencyStyle = (urgency: string): string => {
    switch (urgency) {
      case "urgent":
        return "bg-red-100 text-red-800 border-red-300";
      case "moderate":
        return "bg-orange-100 text-orange-800 border-orange-300";
      case "low":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "no_rush":
        return "bg-gray-100 text-gray-800 border-gray-300";
      default:
        return "bg-gray-100 text-gray-800 border-gray-300";
    }
  };

  const getUrgencyIcon = (urgency: string): string => {
    switch (urgency) {
      case "urgent":
        return "⚡";
      case "moderate":
        return "⏱️";
      case "low":
        return "📅";
      case "no_rush":
        return "🕐";
      default:
        return "";
    }
  };

  const getUrgencyLabel = (urgency: string): string => {
    return urgency.replace("_", " ").toUpperCase();
  };

  // Size variants
  const sizeClasses = {
    sm: "text-xs px-2 py-1",
    md: "text-sm px-3 py-1.5",
    lg: "text-base px-4 py-2",
  };

  return (
    <div class="flex flex-col gap-2">
      <span
        class={`${sizeClasses[size]} ${
          getActionStyle(action)
        } font-bold rounded border-2 inline-flex items-center justify-center`}
      >
        {getActionLabel(action)}
      </span>
      {urgency && (
        <span
          class={`${sizeClasses[size]} ${
            getUrgencyStyle(urgency)
          } font-medium rounded border inline-flex items-center justify-center gap-1`}
        >
          <span>{getUrgencyIcon(urgency)}</span>
          <span>{getUrgencyLabel(urgency)}</span>
        </span>
      )}
    </div>
  );
}

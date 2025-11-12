/**
 * ScoreMeter - Reusable component to display 0-100 scores
 * with color-coded visual indicator
 */

interface ScoreMeterProps {
  score: number; // 0-100
  label: string;
  size?: "sm" | "md" | "lg";
  showValue?: boolean;
}

export default function ScoreMeter(
  { score, label, size = "md", showValue = true }: ScoreMeterProps,
) {
  // Determine color based on score
  const getColor = (score: number): string => {
    if (score >= 80) return "text-green-600 bg-green-100";
    if (score >= 65) return "text-blue-600 bg-blue-100";
    if (score >= 45) return "text-yellow-600 bg-yellow-100";
    return "text-red-600 bg-red-100";
  };

  const getBarColor = (score: number): string => {
    if (score >= 80) return "bg-green-500";
    if (score >= 65) return "bg-blue-500";
    if (score >= 45) return "bg-yellow-500";
    return "bg-red-500";
  };

  // Size variants
  const sizeClasses = {
    sm: {
      container: "w-24",
      height: "h-2",
      text: "text-xs",
      badge: "text-xs px-1.5 py-0.5",
    },
    md: {
      container: "w-32",
      height: "h-3",
      text: "text-sm",
      badge: "text-sm px-2 py-1",
    },
    lg: {
      container: "w-40",
      height: "h-4",
      text: "text-base",
      badge: "text-base px-3 py-1",
    },
  };

  const classes = sizeClasses[size];

  return (
    <div class="flex flex-col gap-1">
      <div class="flex items-center justify-between">
        <span class={`font-medium ${classes.text}`}>{label}</span>
        {showValue && (
          <span
            class={`font-bold ${classes.badge} rounded ${getColor(score)}`}
          >
            {score}
          </span>
        )}
      </div>
      <div
        class={`${classes.container} bg-gray-200 rounded-full overflow-hidden`}
      >
        <div
          class={`${classes.height} ${
            getBarColor(score)
          } transition-all duration-300`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

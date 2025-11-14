interface TagBadgeProps {
  name: string;
  isExpired?: boolean;
  isSelected?: boolean;
  onClick?: () => void;
  className?: string;
  showStatus?: boolean;
}

export default function TagBadge({
  name,
  isExpired = false,
  isSelected = false,
  onClick,
  className = "",
  showStatus = false,
}: TagBadgeProps) {
  const baseClasses = "badge gap-1";

  // Determine badge style based on state
  let styleClasses = "";
  if (onClick) {
    // Interactive badge (for selector)
    if (isSelected) {
      styleClasses = isExpired
        ? "badge-neutral"
        : "badge-primary";
    } else {
      styleClasses = isExpired
        ? "badge-outline badge-neutral opacity-50"
        : "badge-outline badge-primary";
    }
  } else {
    // Display-only badge
    styleClasses = isExpired
      ? "badge-ghost opacity-60"
      : "badge-success";
  }

  const cursorClass = onClick ? "cursor-pointer hover:scale-105 transition-transform" : "";
  const opacityClass = isExpired ? "opacity-70" : "";

  return (
    <div
      class={`${baseClasses} ${styleClasses} ${cursorClass} ${opacityClass} ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick
        ? (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onClick();
          }
        }
        : undefined}
    >
      {name}
      {showStatus && isExpired && (
        <span class="text-xs opacity-75">(expired)</span>
      )}
    </div>
  );
}

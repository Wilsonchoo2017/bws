/**
 * Sync Status Badge Component
 * Displays color-coded status badge with icon for sync state
 */

import {
  getSyncStatusInfo,
  type SyncStatus,
} from "../../utils/sync-helpers.ts";

interface SyncStatusBadgeProps {
  status: SyncStatus;
  size?: "sm" | "md" | "lg";
}

export default function SyncStatusBadge(
  { status, size = "sm" }: SyncStatusBadgeProps,
) {
  const info = getSyncStatusInfo(status);
  const sizeClass = size === "sm"
    ? "badge-sm"
    : size === "lg"
    ? "badge-lg"
    : "";

  return (
    <div class={`badge ${info.badgeClass} ${sizeClass} gap-1`}>
      {info.icon === "loading loading-spinner loading-xs"
        ? <span class={info.icon}></span>
        : <span>{info.icon}</span>}
      <span>{info.label}</span>
    </div>
  );
}

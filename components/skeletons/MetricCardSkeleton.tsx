/**
 * Skeleton loader for metric cards in the queue diagnostics dashboard
 */

export default function MetricCardSkeleton() {
  return (
    <div class="stat bg-base-100 shadow rounded-box">
      <div class="stat-figure">
        <div class="skeleton w-8 h-8 rounded-full"></div>
      </div>
      <div class="stat-title">
        <div class="skeleton h-4 w-20"></div>
      </div>
      <div class="stat-value">
        <div class="skeleton h-10 w-16"></div>
      </div>
    </div>
  );
}

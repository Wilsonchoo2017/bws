/**
 * Skeleton loader for the Queue Diagnostics Dashboard
 * Displays realistic loading state matching the actual dashboard structure
 */

import MetricCardSkeleton from "./MetricCardSkeleton.tsx";

export default function QueueDashboardSkeleton() {
  return (
    <div class="space-y-6">
      {/* Health Status Card Skeleton */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div class="flex items-center gap-4">
              <div class="skeleton h-8 w-24 rounded-full"></div>
              <div class="space-y-2">
                <div class="skeleton h-8 w-64"></div>
                <div class="skeleton h-4 w-32"></div>
              </div>
            </div>
            <div class="skeleton h-12 w-32 rounded-lg"></div>
          </div>
        </div>
      </div>

      {/* Metrics Grid Skeleton */}
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCardSkeleton />
        <MetricCardSkeleton />
        <MetricCardSkeleton />
        <MetricCardSkeleton />
      </div>

      {/* Worker Status Skeleton */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <div class="skeleton h-7 w-32 mb-4"></div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="flex items-center gap-3">
              <div class="skeleton w-3 h-3 rounded-full"></div>
              <div class="space-y-2">
                <div class="skeleton h-4 w-24"></div>
                <div class="skeleton h-5 w-12"></div>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="skeleton w-3 h-3 rounded-full"></div>
              <div class="space-y-2">
                <div class="skeleton h-4 w-24"></div>
                <div class="skeleton h-5 w-12"></div>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="skeleton w-3 h-3 rounded-full"></div>
              <div class="space-y-2">
                <div class="skeleton h-4 w-24"></div>
                <div class="skeleton h-5 w-12"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Jobs Panel Skeleton */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <div class="skeleton h-7 w-32 mb-4"></div>
          <div class="overflow-x-auto">
            <table class="table table-zebra w-full">
              <thead>
                <tr>
                  <th><div class="skeleton h-4 w-16"></div></th>
                  <th><div class="skeleton h-4 w-12"></div></th>
                  <th><div class="skeleton h-4 w-16"></div></th>
                  <th><div class="skeleton h-4 w-24"></div></th>
                  <th><div class="skeleton h-4 w-16"></div></th>
                </tr>
              </thead>
              <tbody>
                {[...Array(5)].map((_, idx) => (
                  <tr key={idx}>
                    <td><div class="skeleton h-4 w-32"></div></td>
                    <td><div class="skeleton h-5 w-16 rounded-full"></div></td>
                    <td><div class="skeleton h-4 w-48"></div></td>
                    <td><div class="skeleton h-4 w-20"></div></td>
                    <td><div class="skeleton h-5 w-12 rounded-full"></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

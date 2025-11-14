import type { VoucherStatus } from "../../hooks/useVoucherList.ts";

interface ProductTag {
  id: string;
  name: string;
}

interface VoucherFiltersProps {
  searchQuery: string;
  statusFilter: VoucherStatus;
  platformFilter: string;
  tagFilter: string | null;
  availableTags: ProductTag[];
  onSearchChange: (value: string) => void;
  onStatusChange: (value: VoucherStatus) => void;
  onPlatformChange: (value: string) => void;
  onTagFilterChange: (tagId: string | null) => void;
}

/**
 * Voucher filter controls component.
 * Displays search, status, platform, and tag filter inputs.
 * Follows Single Responsibility Principle - only handles filter UI.
 */
export function VoucherFilters({
  searchQuery,
  statusFilter,
  platformFilter,
  tagFilter,
  availableTags,
  onSearchChange,
  onStatusChange,
  onPlatformChange,
  onTagFilterChange,
}: VoucherFiltersProps) {
  return (
    <div class="space-y-4 mb-6">
      {/* Status tabs */}
      <div class="tabs tabs-boxed bg-base-200">
        <button
          class={`tab ${statusFilter === "all" ? "tab-active" : ""}`}
          onClick={() => onStatusChange("all")}
        >
          All
        </button>
        <button
          class={`tab ${statusFilter === "active" ? "tab-active" : ""}`}
          onClick={() => onStatusChange("active")}
        >
          <span class="badge badge-success badge-sm mr-2"></span>
          Active
        </button>
        <button
          class={`tab ${statusFilter === "soon" ? "tab-active" : ""}`}
          onClick={() => onStatusChange("soon")}
        >
          <span class="badge badge-warning badge-sm mr-2"></span>
          Starting Soon
        </button>
        <button
          class={`tab ${statusFilter === "expired" ? "tab-active" : ""}`}
          onClick={() => onStatusChange("expired")}
        >
          <span class="badge badge-error badge-sm mr-2"></span>
          Expired
        </button>
      </div>

      {/* Filters row */}
      <div class="flex flex-col lg:flex-row gap-4">
        <div class="form-control flex-1">
          <label class="label">
            <span class="label-text">Search by name</span>
          </label>
          <input
            type="text"
            placeholder="Search vouchers..."
            class="input input-bordered w-full"
            value={searchQuery}
            onInput={(e) =>
              onSearchChange((e.target as HTMLInputElement).value)}
          />
        </div>

        <div class="form-control flex-1">
          <label class="label">
            <span class="label-text">Platform</span>
          </label>
          <select
            class="select select-bordered w-full"
            value={platformFilter}
            onChange={(e) =>
              onPlatformChange((e.target as HTMLSelectElement).value)}
          >
            <option value="all">All Platforms</option>
            <option value="shopee">Shopee</option>
            <option value="toysrus">Toys"R"Us</option>
          </select>
        </div>

        <div class="form-control flex-1">
          <label class="label">
            <span class="label-text">Tag</span>
          </label>
          <select
            class="select select-bordered w-full"
            value={tagFilter || ""}
            onChange={(e) => {
              const value = (e.target as HTMLSelectElement).value;
              onTagFilterChange(value || null);
            }}
          >
            <option value="">All Tags</option>
            {availableTags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

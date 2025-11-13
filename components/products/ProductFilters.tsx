import type { ProductSource } from "../../db/schema.ts";

interface ProductFiltersProps {
  searchQuery: string;
  legoSetFilter: string;
  sourceFilter: ProductSource | "all";
  onSearchChange: (value: string) => void;
  onLegoSetChange: (value: string) => void;
  onSourceChange: (value: ProductSource | "all") => void;
}

/**
 * Product filter controls component.
 * Displays search, LEGO set number, and platform filter inputs.
 * Follows Single Responsibility Principle - only handles filter UI.
 */
export function ProductFilters({
  searchQuery,
  legoSetFilter,
  sourceFilter,
  onSearchChange,
  onLegoSetChange,
  onSourceChange,
}: ProductFiltersProps) {
  return (
    <div class="flex flex-col lg:flex-row gap-4 mb-6">
      <div class="form-control flex-1">
        <label class="label">
          <span class="label-text">Search by name</span>
        </label>
        <input
          type="text"
          placeholder="Search products..."
          class="input input-bordered w-full"
          value={searchQuery}
          onInput={(e) => onSearchChange((e.target as HTMLInputElement).value)}
        />
      </div>

      <div class="form-control flex-1">
        <label class="label">
          <span class="label-text">LEGO Set Number</span>
        </label>
        <input
          type="text"
          placeholder="e.g., 75192"
          class="input input-bordered w-full"
          value={legoSetFilter}
          onInput={(e) => onLegoSetChange((e.target as HTMLInputElement).value)}
        />
      </div>

      <div class="form-control flex-1">
        <label class="label">
          <span class="label-text">Platform</span>
        </label>
        <select
          class="select select-bordered w-full"
          value={sourceFilter}
          onChange={(e) => {
            onSourceChange(
              (e.target as HTMLSelectElement).value as ProductSource | "all",
            );
          }}
        >
          <option value="all">All Platforms</option>
          <option value="shopee">Shopee</option>
          <option value="toysrus">Toys"R"Us</option>
          <option value="self">Manual Entry</option>
        </select>
      </div>
    </div>
  );
}

import type { ProductSource } from "../../db/schema.ts";

interface ProductTag {
  id: string;
  name: string;
  endDate: string | null;
  isExpired?: boolean;
}

interface ProductFiltersProps {
  searchQuery: string;
  legoSetFilter: string;
  sourceFilter: ProductSource | "all";
  tagFilter: string[];
  availableTags: ProductTag[];
  onSearchChange: (value: string) => void;
  onLegoSetChange: (value: string) => void;
  onSourceChange: (value: ProductSource | "all") => void;
  onTagFilterChange: (tagIds: string[]) => void;
}

/**
 * Product filter controls component.
 * Displays search, LEGO set number, platform, and tag filter inputs.
 * Follows Single Responsibility Principle - only handles filter UI.
 */
export function ProductFilters({
  searchQuery,
  legoSetFilter,
  sourceFilter,
  tagFilter,
  availableTags,
  onSearchChange,
  onLegoSetChange,
  onSourceChange,
  onTagFilterChange,
}: ProductFiltersProps) {
  const handleTagToggle = (tagId: string) => {
    if (tagFilter.includes(tagId)) {
      onTagFilterChange(tagFilter.filter((id) => id !== tagId));
    } else {
      onTagFilterChange([...tagFilter, tagId]);
    }
  };

  return (
    <div class="space-y-4 mb-6">
      <div class="flex flex-col lg:flex-row gap-4">
        <div class="form-control flex-1">
          <label class="label">
            <span class="label-text">Search by name</span>
          </label>
          <input
            type="text"
            placeholder="Search products..."
            class="input input-bordered w-full"
            value={searchQuery}
            onInput={(e) =>
              onSearchChange((e.target as HTMLInputElement).value)}
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
            onInput={(e) =>
              onLegoSetChange((e.target as HTMLInputElement).value)}
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

      {/* Tag Filter */}
      {availableTags.length > 0 && (
        <div class="form-control">
          <label class="label">
            <span class="label-text">Filter by Tags</span>
            {tagFilter.length > 0 && (
              <button
                class="label-text-alt link link-hover"
                onClick={() => onTagFilterChange([])}
              >
                Clear all
              </button>
            )}
          </label>
          <div class="flex flex-wrap gap-2">
            {availableTags.map((tag) => (
              <button
                key={tag.id}
                class={`badge badge-lg gap-2 cursor-pointer ${
                  tagFilter.includes(tag.id)
                    ? "badge-primary"
                    : tag.isExpired
                    ? "badge-ghost opacity-50"
                    : "badge-outline"
                }`}
                onClick={() => handleTagToggle(tag.id)}
              >
                {tag.name}
                {tag.isExpired && (
                  <span class="text-xs opacity-70">(expired)</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

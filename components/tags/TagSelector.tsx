import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import TagBadge from "./TagBadge.tsx";

interface ProductTag {
  id: string;
  name: string;
  description: string | null;
  endDate: string | null;
  isExpired?: boolean;
  productCount?: number;
}

interface TagSelectorProps {
  selectedTagIds: string[];
  onChange: (tagIds: string[]) => void;
  disabled?: boolean;
}

export default function TagSelector({
  selectedTagIds,
  onChange,
  disabled = false,
}: TagSelectorProps) {
  const tags = useSignal<ProductTag[]>([]);
  const isLoading = useSignal(true);
  const error = useSignal<string | null>(null);

  useEffect(() => {
    loadTags();
  }, []);

  const loadTags = async () => {
    try {
      isLoading.value = true;
      error.value = null;
      const response = await fetch("/api/tags");

      if (!response.ok) {
        throw new Error(`Failed to load tags: ${response.statusText}`);
      }

      tags.value = await response.json();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Failed to load tags";
      console.error("Error loading tags:", err);
    } finally {
      isLoading.value = false;
    }
  };

  const toggleTag = (tagId: string) => {
    if (disabled) return;

    const isSelected = selectedTagIds.includes(tagId);
    const newSelection = isSelected
      ? selectedTagIds.filter((id) => id !== tagId)
      : [...selectedTagIds, tagId];

    onChange(newSelection);
  };

  if (isLoading.value) {
    return (
      <div class="flex justify-center items-center p-4">
        <span class="loading loading-spinner loading-sm"></span>
      </div>
    );
  }

  if (error.value) {
    return (
      <div class="alert alert-error alert-sm">
        <span class="text-sm">{error.value}</span>
        <button class="btn btn-xs" onClick={loadTags}>
          Retry
        </button>
      </div>
    );
  }

  if (tags.value.length === 0) {
    return (
      <div class="text-sm text-base-content/70 p-4 text-center">
        No tags available.{" "}
        <a href="/tags" class="link link-primary">
          Create tags
        </a>{" "}
        first.
      </div>
    );
  }

  // Sort tags: active first, then by name
  const sortedTags = [...tags.value].sort((a, b) => {
    if (a.isExpired !== b.isExpired) {
      return a.isExpired ? 1 : -1;
    }
    return a.name.localeCompare(b.name);
  });

  return (
    <div class="space-y-2">
      <div class="flex flex-wrap gap-2">
        {sortedTags.map((tag) => (
          <TagBadge
            key={tag.id}
            name={tag.name}
            isExpired={tag.isExpired}
            isSelected={selectedTagIds.includes(tag.id)}
            onClick={() => toggleTag(tag.id)}
            showStatus={tag.isExpired}
          />
        ))}
      </div>

      {selectedTagIds.length > 0 && (
        <div class="text-xs text-base-content/60">
          {selectedTagIds.length} tag{selectedTagIds.length !== 1 ? "s" : ""}{" "}
          selected
        </div>
      )}
    </div>
  );
}

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

interface ProductTag {
  id: string;
  name: string;
  description: string | null;
  endDate: string | null;
  createdAt: string;
  updatedAt: string;
  productCount?: number;
  isExpired?: boolean;
}

export default function TagManager() {
  const tags = useSignal<ProductTag[]>([]);
  const isLoading = useSignal(true);
  const error = useSignal<string | null>(null);
  const isAddingNew = useSignal(false);
  const editingId = useSignal<string | null>(null);
  const isCleaningUp = useSignal(false);

  // Form state
  const formName = useSignal("");
  const formDescription = useSignal("");
  const formEndDate = useSignal("");

  // Load tags on mount
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

  const resetForm = () => {
    formName.value = "";
    formDescription.value = "";
    formEndDate.value = "";
    isAddingNew.value = false;
    editingId.value = null;
  };

  const startEdit = (tag: ProductTag) => {
    formName.value = tag.name;
    formDescription.value = tag.description || "";
    formEndDate.value = tag.endDate
      ? new Date(tag.endDate).toISOString().split("T")[0]
      : "";
    editingId.value = tag.id;
    isAddingNew.value = false;
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();

    if (!formName.value.trim()) {
      alert("Tag name is required");
      return;
    }

    try {
      // Prepare endDate - if not provided, default to end of today
      let endDate = formEndDate.value;
      if (!endDate) {
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        endDate = today.toISOString();
      } else {
        // Set to end of selected day
        const date = new Date(endDate);
        date.setHours(23, 59, 59, 999);
        endDate = date.toISOString();
      }

      const payload = {
        name: formName.value.trim(),
        description: formDescription.value.trim() || null,
        endDate,
      };

      let response;

      if (editingId.value) {
        // Update existing tag
        response = await fetch("/api/tags", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, id: editingId.value }),
        });
      } else {
        // Create new tag
        response = await fetch("/api/tags", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to save tag");
      }

      resetForm();
      await loadTags();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save tag");
      console.error("Error saving tag:", err);
    }
  };

  const handleDelete = async (tagId: string, tagName: string) => {
    if (
      !confirm(
        `Are you sure you want to delete the tag "${tagName}"? This will remove it from all products.`,
      )
    ) {
      return;
    }

    try {
      const response = await fetch(`/api/tags?id=${tagId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to delete tag");
      }

      await loadTags();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete tag");
      console.error("Error deleting tag:", err);
    }
  };

  const handleCleanupExpired = async () => {
    if (
      !confirm(
        "This will remove all expired tags from products. Are you sure?",
      )
    ) {
      return;
    }

    try {
      isCleaningUp.value = true;
      const response = await fetch("/api/tags/cleanup-expired", {
        method: "POST",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to cleanup expired tags");
      }

      const result = await response.json();
      alert(result.message);
      await loadTags();
    } catch (err) {
      alert(
        err instanceof Error ? err.message : "Failed to cleanup expired tags",
      );
      console.error("Error cleaning up expired tags:", err);
    } finally {
      isCleaningUp.value = false;
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "No expiry";
    return new Date(dateStr).toLocaleDateString("en-MY", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  if (isLoading.value) {
    return (
      <div class="flex justify-center items-center p-8">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error.value) {
    return (
      <div class="alert alert-error">
        <span>{error.value}</span>
        <button class="btn btn-sm" onClick={loadTags}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div class="space-y-6">
      {/* Action Buttons */}
      <div class="flex gap-2 flex-wrap">
        <button
          class="btn btn-primary"
          onClick={() => {
            isAddingNew.value = true;
            editingId.value = null;
          }}
        >
          + Add New Tag
        </button>
        <button
          class="btn btn-warning"
          onClick={handleCleanupExpired}
          disabled={isCleaningUp.value}
        >
          {isCleaningUp.value ? "Cleaning up..." : "Cleanup Expired Tags"}
        </button>
      </div>

      {/* Add/Edit Form */}
      {(isAddingNew.value || editingId.value) && (
        <div class="card bg-base-200">
          <div class="card-body">
            <h2 class="card-title">
              {editingId.value ? "Edit Tag" : "Add New Tag"}
            </h2>
            <form onSubmit={handleSubmit} class="space-y-4">
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Tag Name *</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered"
                  value={formName.value}
                  onInput={(e) =>
                    formName.value = (e.target as HTMLInputElement).value}
                  placeholder="e.g., 11.11 Sale, Flash Sale"
                  required
                />
              </div>

              <div class="form-control">
                <label class="label">
                  <span class="label-text">Description</span>
                </label>
                <textarea
                  class="textarea textarea-bordered"
                  value={formDescription.value}
                  onInput={(e) =>
                    formDescription.value =
                      (e.target as HTMLTextAreaElement).value}
                  placeholder="Optional description"
                  rows={2}
                />
              </div>

              <div class="form-control">
                <label class="label">
                  <span class="label-text">End Date</span>
                </label>
                <input
                  type="date"
                  class="input input-bordered"
                  value={formEndDate.value}
                  onInput={(e) =>
                    formEndDate.value = (e.target as HTMLInputElement).value}
                />
                <label class="label">
                  <span class="label-text-alt">
                    Leave empty to default to end of today
                  </span>
                </label>
              </div>

              <div class="card-actions justify-end">
                <button
                  type="button"
                  class="btn btn-ghost"
                  onClick={resetForm}
                >
                  Cancel
                </button>
                <button type="submit" class="btn btn-primary">
                  {editingId.value ? "Update" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tags List */}
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title">Existing Tags ({tags.value.length})</h2>

          {tags.value.length === 0
            ? (
              <p class="text-base-content/70">
                No tags yet. Create your first tag to get started!
              </p>
            )
            : (
              <div class="overflow-x-auto">
                <table class="table table-zebra">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Description</th>
                      <th>End Date</th>
                      <th>Status</th>
                      <th>Products</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tags.value.map((tag) => (
                      <tr key={tag.id}>
                        <td class="font-semibold">{tag.name}</td>
                        <td class="text-sm text-base-content/70">
                          {tag.description || "-"}
                        </td>
                        <td class="text-sm">{formatDate(tag.endDate)}</td>
                        <td>
                          {tag.isExpired
                            ? (
                              <span class="badge badge-error badge-sm">
                                Expired
                              </span>
                            )
                            : (
                              <span class="badge badge-success badge-sm">
                                Active
                              </span>
                            )}
                        </td>
                        <td>
                          <span class="badge badge-neutral">
                            {tag.productCount || 0}
                          </span>
                        </td>
                        <td class="space-x-2">
                          <button
                            class="btn btn-xs btn-ghost"
                            onClick={() => startEdit(tag)}
                          >
                            Edit
                          </button>
                          <button
                            class="btn btn-xs btn-error"
                            onClick={() => handleDelete(tag.id, tag.name)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}

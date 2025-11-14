import { signal } from "@preact/signals";
import type {
  BrickrankerRetirementItem,
  Product,
  WorldbricksSet,
} from "../db/schema.ts";
import TagSelector from "../components/tags/TagSelector.tsx";

interface ProductEditModalProps {
  product: Product;
  worldbricksSet?: WorldbricksSet;
  brickrankerItem?: BrickrankerRetirementItem;
}

const showModal = signal(false);
const isLoading = signal(false);
const error = signal<string | null>(null);
const success = signal(false);

// Form field signals
const editName = signal("");
const editLegoSetNumber = signal("");
const editPrice = signal("");
const editPriceBeforeDiscount = signal("");
const editWatchStatus = signal<"active" | "paused" | "stopped" | "archived">(
  "active",
);
const editYearReleased = signal("");
const editYearRetired = signal("");
const editExpectedRetirement = signal("");
const editSelectedTagIds = signal<string[]>([]);

export default function ProductEditModal(
  { product, worldbricksSet, brickrankerItem }: ProductEditModalProps,
) {
  const openModal = () => {
    // Initialize form with current product data
    editName.value = product.name || "";
    editLegoSetNumber.value = product.legoSetNumber || "";
    editPrice.value = product.price ? (product.price / 100).toFixed(2) : "";
    editPriceBeforeDiscount.value = product.priceBeforeDiscount
      ? (product.priceBeforeDiscount / 100).toFixed(2)
      : "";
    editWatchStatus.value = product.watchStatus || "active";
    editYearReleased.value = worldbricksSet?.yearReleased?.toString() ||
      brickrankerItem?.yearReleased?.toString() || "";
    editYearRetired.value = worldbricksSet?.yearRetired?.toString() || "";
    editExpectedRetirement.value = brickrankerItem?.expectedRetirementDate ||
      "";
    error.value = null;
    success.value = false;
    showModal.value = true;
  };

  const closeModal = () => {
    if (!isLoading.value) {
      showModal.value = false;
    }
  };

  const handleSubmit = async () => {
    isLoading.value = true;
    error.value = null;
    success.value = false;

    try {
      // Convert prices from dollars to cents
      const priceInCents = editPrice.value
        ? Math.round(parseFloat(editPrice.value) * 100)
        : null;
      const priceBeforeDiscountInCents = editPriceBeforeDiscount.value
        ? Math.round(parseFloat(editPriceBeforeDiscount.value) * 100)
        : null;

      // Parse retirement years
      const yearReleased = editYearReleased.value
        ? parseInt(editYearReleased.value)
        : null;
      const yearRetired = editYearRetired.value
        ? parseInt(editYearRetired.value)
        : null;

      const response = await fetch(`/api/products/${product.productId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: editName.value || null,
          legoSetNumber: editLegoSetNumber.value || null,
          price: priceInCents,
          priceBeforeDiscount: priceBeforeDiscountInCents,
          watchStatus: editWatchStatus.value,
          yearReleased,
          yearRetired,
          expectedRetirementDate: editExpectedRetirement.value || null,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to update product");
      }

      success.value = true;

      // Reload the page after a short delay to show updated data
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err) {
      error.value = err instanceof Error ? err.message : "An error occurred";
      isLoading.value = false;
    }
  };

  return (
    <>
      {/* Edit Button */}
      <button onClick={openModal} class="btn btn-outline btn-sm">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          stroke-width="1.5"
          stroke="currentColor"
          class="w-4 h-4"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
          />
        </svg>
        Edit Metadata
      </button>

      {/* Modal */}
      {showModal.value && (
        <div class="modal modal-open">
          <div class="modal-box max-w-2xl">
            <h3 class="font-bold text-lg mb-4">Edit Product Metadata</h3>

            <div class="space-y-4 max-h-96 overflow-y-auto">
              {/* Name */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Product Name</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editName.value}
                  onInput={(e) => editName.value = e.currentTarget.value}
                  disabled={isLoading.value}
                />
              </div>

              {/* LEGO Set Number */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">LEGO Set Number</span>
                  <span class="label-text-alt">Max 10 characters</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editLegoSetNumber.value}
                  onInput={(e) =>
                    editLegoSetNumber.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  maxLength={10}
                />
              </div>

              {/* Price */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Price</span>
                  <span class="label-text-alt">In dollars (e.g., 99.99)</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  class="input input-bordered w-full"
                  value={editPrice.value}
                  onInput={(e) => editPrice.value = e.currentTarget.value}
                  disabled={isLoading.value}
                />
              </div>

              {/* Retail Price (MSRP) */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Retail Price (MSRP)</span>
                  <span class="label-text-alt">
                    Manufacturer's suggested retail price
                  </span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  class="input input-bordered w-full"
                  value={editPriceBeforeDiscount.value}
                  onInput={(e) =>
                    editPriceBeforeDiscount.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  placeholder="Enter MSRP"
                />
              </div>

              <div class="divider">Retirement Information</div>

              {/* Year Released */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Release Year</span>
                  <span class="label-text-alt">Year the set was released</span>
                </label>
                <input
                  type="number"
                  class="input input-bordered w-full"
                  value={editYearReleased.value}
                  onInput={(e) =>
                    editYearReleased.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  placeholder="e.g., 2023"
                  min="1900"
                  max="2100"
                />
              </div>

              {/* Year Retired */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Retirement Year</span>
                  <span class="label-text-alt">
                    Year the set was retired (leave empty if active)
                  </span>
                </label>
                <input
                  type="number"
                  class="input input-bordered w-full"
                  value={editYearRetired.value}
                  onInput={(e) => editYearRetired.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  placeholder="e.g., 2025"
                  min="1900"
                  max="2100"
                />
              </div>

              {/* Expected Retirement Date */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Expected Retirement Date</span>
                  <span class="label-text-alt">
                    Expected retirement (e.g., "Q4 2024", "2025")
                  </span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editExpectedRetirement.value}
                  onInput={(e) =>
                    editExpectedRetirement.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  placeholder="e.g., Q4 2024, December 2024, 2025"
                />
              </div>

              {/* Watch Status */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Watch Status</span>
                </label>
                <select
                  class="select select-bordered w-full"
                  value={editWatchStatus.value}
                  onChange={(e) =>
                    editWatchStatus.value = e.currentTarget.value as
                      | "active"
                      | "paused"
                      | "stopped"
                      | "archived"}
                  disabled={isLoading.value}
                >
                  <option value="active">Active</option>
                  <option value="paused">Paused</option>
                  <option value="stopped">Stopped</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
            </div>

            {/* Error Alert */}
            {error.value && (
              <div class="alert alert-error mt-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{error.value}</span>
              </div>
            )}

            {/* Success Alert */}
            {success.value && (
              <div class="alert alert-success mt-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="stroke-current shrink-0 h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>Product updated successfully! Reloading...</span>
              </div>
            )}

            {/* Modal Actions */}
            <div class="modal-action">
              <button
                class="btn btn-ghost"
                onClick={closeModal}
                disabled={isLoading.value}
              >
                Cancel
              </button>
              <button
                class="btn btn-primary"
                onClick={handleSubmit}
                disabled={isLoading.value}
              >
                {isLoading.value
                  ? (
                    <>
                      <span class="loading loading-spinner"></span>
                      Saving...
                    </>
                  )
                  : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

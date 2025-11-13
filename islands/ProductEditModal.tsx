import { signal } from "@preact/signals";
import type { Product } from "../db/schema.ts";

interface ProductEditModalProps {
  product: Product;
}

const showModal = signal(false);
const isLoading = signal(false);
const error = signal<string | null>(null);
const success = signal(false);

// Form field signals
const editName = signal("");
const editBrand = signal("");
const editLegoSetNumber = signal("");
const editCurrency = signal("");
const editPrice = signal("");
const editPriceMin = signal("");
const editPriceMax = signal("");
const editPriceBeforeDiscount = signal("");
const editImage = signal("");
const editWatchStatus = signal<"active" | "paused" | "stopped" | "archived">(
  "active",
);

export default function ProductEditModal({ product }: ProductEditModalProps) {
  const openModal = () => {
    // Initialize form with current product data
    editName.value = product.name || "";
    editBrand.value = product.brand || "";
    editLegoSetNumber.value = product.legoSetNumber || "";
    editCurrency.value = product.currency || "SGD";
    editPrice.value = product.price ? (product.price / 100).toFixed(2) : "";
    editPriceMin.value = product.priceMin
      ? (product.priceMin / 100).toFixed(2)
      : "";
    editPriceMax.value = product.priceMax
      ? (product.priceMax / 100).toFixed(2)
      : "";
    editPriceBeforeDiscount.value = product.priceBeforeDiscount
      ? (product.priceBeforeDiscount / 100).toFixed(2)
      : "";
    editImage.value = product.image || "";
    editWatchStatus.value = product.watchStatus || "active";
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
      const priceMinInCents = editPriceMin.value
        ? Math.round(parseFloat(editPriceMin.value) * 100)
        : null;
      const priceMaxInCents = editPriceMax.value
        ? Math.round(parseFloat(editPriceMax.value) * 100)
        : null;
      const priceBeforeDiscountInCents = editPriceBeforeDiscount.value
        ? Math.round(parseFloat(editPriceBeforeDiscount.value) * 100)
        : null;

      const response = await fetch(`/api/products/${product.productId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: editName.value || null,
          brand: editBrand.value || null,
          legoSetNumber: editLegoSetNumber.value || null,
          currency: editCurrency.value || null,
          price: priceInCents,
          priceMin: priceMinInCents,
          priceMax: priceMaxInCents,
          priceBeforeDiscount: priceBeforeDiscountInCents,
          image: editImage.value || null,
          watchStatus: editWatchStatus.value,
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

              {/* Brand */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Brand</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editBrand.value}
                  onInput={(e) => editBrand.value = e.currentTarget.value}
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

              {/* Currency */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Currency</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editCurrency.value}
                  onInput={(e) => editCurrency.value = e.currentTarget.value}
                  disabled={isLoading.value}
                  placeholder="SGD"
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

              {/* Price Before Discount */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Price Before Discount</span>
                  <span class="label-text-alt">Optional</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  class="input input-bordered w-full"
                  value={editPriceBeforeDiscount.value}
                  onInput={(e) =>
                    editPriceBeforeDiscount.value = e.currentTarget.value}
                  disabled={isLoading.value}
                />
              </div>

              {/* Price Range */}
              <div class="grid grid-cols-2 gap-4">
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">Min Price</span>
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    class="input input-bordered w-full"
                    value={editPriceMin.value}
                    onInput={(e) => editPriceMin.value = e.currentTarget.value}
                    disabled={isLoading.value}
                  />
                </div>
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">Max Price</span>
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    class="input input-bordered w-full"
                    value={editPriceMax.value}
                    onInput={(e) => editPriceMax.value = e.currentTarget.value}
                    disabled={isLoading.value}
                  />
                </div>
              </div>

              {/* Image URL */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Image URL</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={editImage.value}
                  onInput={(e) => editImage.value = e.currentTarget.value}
                  disabled={isLoading.value}
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

interface AddProductModalProps {
  showModal: boolean;
  legoSetNumber: string;
  isAdding: boolean;
  error: string | null;
  success: string | null;
  onClose: () => void;
  onLegoSetNumberChange: (value: string) => void;
  onSubmit: () => void;
}

/**
 * Add Product modal component.
 * Displays a modal dialog for manually adding LEGO products by set number.
 * Follows Single Responsibility Principle - only handles modal UI.
 */
export function AddProductModal({
  showModal,
  legoSetNumber,
  isAdding,
  error,
  success,
  onClose,
  onLegoSetNumberChange,
  onSubmit,
}: AddProductModalProps) {
  if (!showModal) {
    return null;
  }

  return (
    <div class="modal modal-open">
      <div class="modal-box">
        <h3 class="font-bold text-lg mb-4">Add LEGO Product Manually</h3>

        <div class="form-control">
          <label class="label">
            <span class="label-text">
              LEGO Set Number (5 digits)
            </span>
          </label>
          <input
            type="text"
            placeholder="e.g., 75192"
            class="input input-bordered w-full"
            value={legoSetNumber}
            onInput={(e) =>
              onLegoSetNumberChange((e.target as HTMLInputElement).value)}
            disabled={isAdding}
            maxLength={5}
          />
          <label class="label">
            <span class="label-text-alt text-base-content/60">
              Data will be scraped from Bricklink (takes 10-30 seconds)
            </span>
          </label>
        </div>

        {/* Error message */}
        {error && (
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
            <span>{error}</span>
          </div>
        )}

        {/* Success message */}
        {success && (
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
            <span>{success}</span>
          </div>
        )}

        <div class="modal-action">
          <button
            class="btn btn-ghost"
            onClick={onClose}
            disabled={isAdding}
          >
            Cancel
          </button>
          <button
            class="btn btn-primary"
            onClick={onSubmit}
            disabled={isAdding}
          >
            {isAdding && (
              <span class="loading loading-spinner"></span>
            )}
            {isAdding ? "Adding..." : "Add Product"}
          </button>
        </div>
      </div>
      <div class="modal-backdrop" onClick={onClose}></div>
    </div>
  );
}

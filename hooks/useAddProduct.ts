import { useSignal } from "@preact/signals";

export interface AddProductState {
  showModal: boolean;
  legoSetNumber: string;
  isAdding: boolean;
  error: string | null;
  success: string | null;
}

export interface AddProductActions {
  openModal: () => void;
  closeModal: () => void;
  setLegoSetNumber: (value: string) => void;
  submitProduct: () => Promise<void>;
}

export interface UseAddProductReturn {
  state: AddProductState;
  actions: AddProductActions;
}

/**
 * Custom hook for managing the "Add Product" modal state and logic.
 * Handles form validation, submission, and success/error states.
 */
export function useAddProduct(
  onSuccess?: () => void,
): UseAddProductReturn {
  const showModal = useSignal(false);
  const legoSetNumber = useSignal("");
  const isAdding = useSignal(false);
  const error = useSignal<string | null>(null);
  const success = useSignal<string | null>(null);

  const openModal = () => {
    showModal.value = true;
    // Reset form state
    legoSetNumber.value = "";
    error.value = null;
    success.value = null;
  };

  const closeModal = () => {
    showModal.value = false;
    legoSetNumber.value = "";
    error.value = null;
    success.value = null;
  };

  const setLegoSetNumber = (value: string) => {
    legoSetNumber.value = value;
    // Clear errors when user types
    if (error.value) {
      error.value = null;
    }
  };

  const validateInput = (setNumber: string): string | null => {
    if (!setNumber) {
      return "Please enter a LEGO set number";
    }

    if (!/^\d{5}$/.test(setNumber)) {
      return "Please enter a valid 5-digit LEGO set number (e.g., 75192)";
    }

    return null;
  };

  const submitProduct = async () => {
    const setNumber = legoSetNumber.value.trim();

    // Validate input
    const validationError = validateInput(setNumber);
    if (validationError) {
      error.value = validationError;
      return;
    }

    isAdding.value = true;
    error.value = null;
    success.value = null;

    try {
      const response = await fetch("/api/products/manual", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          legoSetNumber: setNumber,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `HTTP error! status: ${response.status}`);
      }

      // Show success message
      success.value = data.message ||
        "Product added successfully! Data will appear once scraping completes.";
      legoSetNumber.value = "";

      // Close modal and refresh after showing success
      setTimeout(() => {
        closeModal();
        if (onSuccess) {
          onSuccess();
        }
      }, 3000);
    } catch (err) {
      error.value = err instanceof Error
        ? err.message
        : "Failed to add product";
      console.error("Error adding product:", err);
    } finally {
      isAdding.value = false;
    }
  };

  return {
    state: {
      showModal: showModal.value,
      legoSetNumber: legoSetNumber.value,
      isAdding: isAdding.value,
      error: error.value,
      success: success.value,
    },
    actions: {
      openModal,
      closeModal,
      setLegoSetNumber,
      submitProduct,
    },
  };
}

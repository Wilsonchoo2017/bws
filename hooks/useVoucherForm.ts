import { useSignal } from "@preact/signals";
import type { Voucher } from "./useVoucherList.ts";

export interface VoucherFormState {
  name: string;
  description: string;
  voucherType: "platform" | "shop" | "item_tag";
  discountType: "percentage" | "fixed";
  discountValue: string; // String for input handling
  platform: string;
  shopId: string;
  shopName: string;
  minPurchase: string;
  maxDiscount: string;
  requiredTagIds: string[];
  isActive: boolean;
  startDate: string;
  endDate: string;
}

export interface VoucherFormActions {
  setName: (value: string) => void;
  setDescription: (value: string) => void;
  setVoucherType: (value: "platform" | "shop" | "item_tag") => void;
  setDiscountType: (value: "percentage" | "fixed") => void;
  setDiscountValue: (value: string) => void;
  setPlatform: (value: string) => void;
  setShopId: (value: string) => void;
  setShopName: (value: string) => void;
  setMinPurchase: (value: string) => void;
  setMaxDiscount: (value: string) => void;
  setRequiredTagIds: (value: string[]) => void;
  setIsActive: (value: boolean) => void;
  setStartDate: (value: string) => void;
  setEndDate: (value: string) => void;
  resetForm: () => void;
  loadVoucher: (voucher: Voucher) => void;
  duplicateVoucher: (voucher: Voucher) => void;
  validateForm: () => string | null;
  toApiPayload: () => Record<string, unknown>;
}

export interface UseVoucherFormReturn {
  form: VoucherFormState;
  actions: VoucherFormActions;
  isEditing: boolean;
  editingId: string | null;
}

const getInitialState = (): VoucherFormState => ({
  name: "",
  description: "",
  voucherType: "platform",
  discountType: "percentage",
  discountValue: "",
  platform: "",
  shopId: "",
  shopName: "",
  minPurchase: "",
  maxDiscount: "",
  requiredTagIds: [],
  isActive: true,
  startDate: "",
  endDate: "",
});

/**
 * Custom hook for managing voucher form state and logic.
 * Handles form validation, editing, and duplication.
 */
export function useVoucherForm(): UseVoucherFormReturn {
  const name = useSignal("");
  const description = useSignal("");
  const voucherType = useSignal<"platform" | "shop" | "item_tag">("platform");
  const discountType = useSignal<"percentage" | "fixed">("percentage");
  const discountValue = useSignal("");
  const platform = useSignal("");
  const shopId = useSignal("");
  const shopName = useSignal("");
  const minPurchase = useSignal("");
  const maxDiscount = useSignal("");
  const requiredTagIds = useSignal<string[]>([]);
  const isActive = useSignal(true);
  const startDate = useSignal("");
  const endDate = useSignal("");
  const editingId = useSignal<string | null>(null);

  const resetForm = () => {
    const initial = getInitialState();
    name.value = initial.name;
    description.value = initial.description;
    voucherType.value = initial.voucherType;
    discountType.value = initial.discountType;
    discountValue.value = initial.discountValue;
    platform.value = initial.platform;
    shopId.value = initial.shopId;
    shopName.value = initial.shopName;
    minPurchase.value = initial.minPurchase;
    maxDiscount.value = initial.maxDiscount;
    requiredTagIds.value = initial.requiredTagIds;
    isActive.value = initial.isActive;
    startDate.value = initial.startDate;
    endDate.value = initial.endDate;
    editingId.value = null;
  };

  const loadVoucher = (voucher: Voucher) => {
    name.value = voucher.name;
    description.value = voucher.description || "";
    voucherType.value = voucher.voucherType;
    discountType.value = voucher.discountType;
    // Convert from cents/basis points to display value
    discountValue.value = voucher.discountType === "percentage"
      ? (voucher.discountValue / 100).toString()
      : (voucher.discountValue / 100).toFixed(2);
    platform.value = voucher.platform || "";
    shopId.value = voucher.shopId?.toString() || "";
    shopName.value = voucher.shopName || "";
    minPurchase.value = voucher.minPurchase ? (voucher.minPurchase / 100).toFixed(2) : "";
    maxDiscount.value = voucher.maxDiscount ? (voucher.maxDiscount / 100).toFixed(2) : "";
    requiredTagIds.value = voucher.requiredTagIds || [];
    isActive.value = voucher.isActive;
    startDate.value = voucher.startDate
      ? new Date(voucher.startDate).toISOString().split("T")[0]
      : "";
    endDate.value = voucher.endDate
      ? new Date(voucher.endDate).toISOString().split("T")[0]
      : "";
    editingId.value = voucher.id;
  };

  const duplicateVoucher = (voucher: Voucher) => {
    loadVoucher(voucher);
    name.value = `${voucher.name} (Copy)`;
    editingId.value = null; // Clear editing ID for duplicate
  };

  const validateForm = (): string | null => {
    if (!name.value.trim()) {
      return "Voucher name is required";
    }

    if (!discountValue.value || parseFloat(discountValue.value) <= 0) {
      return "Discount value must be greater than 0";
    }

    if (discountType.value === "percentage" && parseFloat(discountValue.value) > 100) {
      return "Percentage discount cannot exceed 100%";
    }

    if (voucherType.value === "shop" && !shopId.value.trim()) {
      return "Shop ID is required for shop vouchers";
    }

    if (voucherType.value === "platform" && !platform.value.trim()) {
      return "Platform is required for platform vouchers";
    }

    if (voucherType.value === "item_tag" && requiredTagIds.value.length === 0) {
      return "At least one tag is required for tag-based vouchers";
    }

    return null;
  };

  const toApiPayload = (): Record<string, unknown> => {
    // Convert display values to cents/basis points
    const discountVal = parseFloat(discountValue.value);
    const discountValueInCents = discountType.value === "percentage"
      ? Math.round(discountVal * 100) // Percentage * 100 (e.g., 15% = 1500)
      : Math.round(discountVal * 100); // Dollar amount to cents

    const payload: Record<string, unknown> = {
      name: name.value.trim(),
      description: description.value.trim() || null,
      voucherType: voucherType.value,
      discountType: discountType.value,
      discountValue: discountValueInCents,
      platform: platform.value.trim() || null,
      shopId: shopId.value.trim() ? parseInt(shopId.value.trim()) : null,
      shopName: shopName.value.trim() || null,
      minPurchase: minPurchase.value.trim()
        ? Math.round(parseFloat(minPurchase.value) * 100)
        : null,
      maxDiscount: maxDiscount.value.trim()
        ? Math.round(parseFloat(maxDiscount.value) * 100)
        : null,
      requiredTagIds: requiredTagIds.value.length > 0 ? requiredTagIds.value : null,
      isActive: isActive.value,
      startDate: startDate.value || null,
      endDate: endDate.value || null,
    };

    if (editingId.value) {
      payload.id = editingId.value;
    }

    return payload;
  };

  return {
    form: {
      name: name.value,
      description: description.value,
      voucherType: voucherType.value,
      discountType: discountType.value,
      discountValue: discountValue.value,
      platform: platform.value,
      shopId: shopId.value,
      shopName: shopName.value,
      minPurchase: minPurchase.value,
      maxDiscount: maxDiscount.value,
      requiredTagIds: requiredTagIds.value,
      isActive: isActive.value,
      startDate: startDate.value,
      endDate: endDate.value,
    },
    actions: {
      setName: (value: string) => name.value = value,
      setDescription: (value: string) => description.value = value,
      setVoucherType: (value: "platform" | "shop" | "item_tag") => voucherType.value = value,
      setDiscountType: (value: "percentage" | "fixed") => discountType.value = value,
      setDiscountValue: (value: string) => discountValue.value = value,
      setPlatform: (value: string) => platform.value = value,
      setShopId: (value: string) => shopId.value = value,
      setShopName: (value: string) => shopName.value = value,
      setMinPurchase: (value: string) => minPurchase.value = value,
      setMaxDiscount: (value: string) => maxDiscount.value = value,
      setRequiredTagIds: (value: string[]) => requiredTagIds.value = value,
      setIsActive: (value: boolean) => isActive.value = value,
      setStartDate: (value: string) => startDate.value = value,
      setEndDate: (value: string) => endDate.value = value,
      resetForm,
      loadVoucher,
      duplicateVoucher,
      validateForm,
      toApiPayload,
    },
    isEditing: editingId.value !== null,
    editingId: editingId.value,
  };
}

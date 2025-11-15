import { useComputed, useSignal } from "@preact/signals";
import type { VoucherTemplate } from "../types/voucher.ts";
import { DiscountType, VoucherType } from "../types/voucher.ts";
import type { Voucher } from "../hooks/useVoucherList.ts";

export interface VoucherSelectorProps {
  availableVouchers: Voucher[];
  selectedVouchers: VoucherTemplate[];
  onSelectionChange: (vouchers: VoucherTemplate[]) => void;
  maxSelections?: number;
}

/**
 * Convert database Voucher to VoucherTemplate format for calculations
 */
function convertToVoucherTemplate(voucher: Voucher): VoucherTemplate {
  return {
    id: voucher.id,
    name: voucher.name,
    type: voucher.voucherType as VoucherType,
    discountType: voucher.discountType as DiscountType,
    discountValue: voucher.discountValue,
    tieredDiscounts: voucher.tieredDiscounts || undefined,
    conditions: {
      minPurchase: voucher.minPurchase || undefined,
      maxDiscount: voucher.maxDiscount || undefined,
      requiredTags: voucher.requiredTagIds || undefined,
    },
    description: voucher.description || undefined,
  };
}

/**
 * Format discount display text
 */
function formatDiscount(voucher: Voucher): string {
  if (voucher.tieredDiscounts && voucher.tieredDiscounts.length > 0) {
    const tiers = voucher.tieredDiscounts
      .map((t) =>
        `RM${(t.discount / 100).toFixed(0)} off RM${
          (t.minSpend / 100).toFixed(0)
        }`
      )
      .join(", ");
    return `Tiered: ${tiers}`;
  }

  if (voucher.discountType === "percentage") {
    const pct = voucher.discountValue / 100;
    const cap = voucher.maxDiscount
      ? ` (max RM${(voucher.maxDiscount / 100).toFixed(0)})`
      : "";
    return `${pct}% off${cap}`;
  } else {
    return `RM${(voucher.discountValue / 100).toFixed(2)} off`;
  }
}

/**
 * Format minimum purchase requirement
 */
function formatMinPurchase(minPurchase: number | null): string {
  if (!minPurchase) return "";
  return `Min: RM${(minPurchase / 100).toFixed(0)}`;
}

/**
 * Get voucher type badge color
 */
function getTypeBadgeClass(type: string): string {
  switch (type) {
    case "platform":
      return "bg-blue-100 text-blue-800";
    case "shop":
      return "bg-green-100 text-green-800";
    case "item_tag":
      return "bg-purple-100 text-purple-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

/**
 * VoucherSelector - Interactive component for selecting vouchers to apply
 * Allows multi-select and provides visual feedback on selection
 */
export default function VoucherSelector({
  availableVouchers,
  selectedVouchers,
  onSelectionChange,
  maxSelections = 5,
}: VoucherSelectorProps) {
  const searchQuery = useSignal("");
  const filterType = useSignal<string>("all");
  const isExpanded = useSignal(true);

  // Filter vouchers based on search and type
  const filteredVouchers = useComputed(() => {
    let filtered = availableVouchers;

    // Filter by search query
    if (searchQuery.value.trim()) {
      const query = searchQuery.value.toLowerCase();
      filtered = filtered.filter((v) =>
        v.name.toLowerCase().includes(query) ||
        v.description?.toLowerCase().includes(query)
      );
    }

    // Filter by type
    if (filterType.value !== "all") {
      filtered = filtered.filter((v) => v.voucherType === filterType.value);
    }

    return filtered;
  });

  // Check if voucher is selected
  const isSelected = (voucherId: string): boolean => {
    return selectedVouchers.some((v) => v.id === voucherId);
  };

  // Toggle voucher selection
  const toggleVoucher = (voucher: Voucher) => {
    const voucherTemplate = convertToVoucherTemplate(voucher);

    if (isSelected(voucher.id)) {
      // Remove from selection
      const updated = selectedVouchers.filter((v) => v.id !== voucher.id);
      onSelectionChange(updated);
    } else {
      // Add to selection (check max limit)
      if (selectedVouchers.length < maxSelections) {
        onSelectionChange([...selectedVouchers, voucherTemplate]);
      }
    }
  };

  // Clear all selections
  const clearAll = () => {
    onSelectionChange([]);
  };

  return (
    <div class="bg-white border border-gray-200 rounded-lg shadow-sm">
      {/* Header */}
      <div class="flex items-center justify-between p-4 border-b border-gray-200">
        <div class="flex items-center gap-2">
          <button
            onClick={() => isExpanded.value = !isExpanded.value}
            class="text-gray-600 hover:text-gray-800 transition-colors"
            aria-label={isExpanded.value
              ? "Collapse voucher selector"
              : "Expand voucher selector"}
          >
            <svg
              class={`w-5 h-5 transition-transform ${
                isExpanded.value ? "rotate-90" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
          <h3 class="font-semibold text-gray-900">
            Apply Vouchers
          </h3>
          {selectedVouchers.length > 0 && (
            <span class="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
              {selectedVouchers.length} selected
            </span>
          )}
        </div>
        {selectedVouchers.length > 0 && (
          <button
            onClick={clearAll}
            class="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Content */}
      {isExpanded.value && (
        <div class="p-4 space-y-4">
          {/* Search and Filter */}
          <div class="flex gap-2">
            <input
              type="text"
              placeholder="Search vouchers..."
              value={searchQuery.value}
              onInput={(e) =>
                searchQuery.value = (e.target as HTMLInputElement).value}
              class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <select
              value={filterType.value}
              onChange={(e) =>
                filterType.value = (e.target as HTMLSelectElement).value}
              class="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="all">All Types</option>
              <option value="platform">Platform</option>
              <option value="shop">Shop</option>
              <option value="item_tag">Item Tag</option>
            </select>
          </div>

          {/* Info message */}
          <p class="text-sm text-gray-600">
            Select up to {maxSelections}{" "}
            vouchers to simulate discounts on value investing opportunities
            below. The system will automatically find the optimal order to
            maximize your savings.
          </p>

          {/* Voucher List */}
          <div class="space-y-2 max-h-96 overflow-y-auto">
            {filteredVouchers.value.length === 0
              ? (
                <div class="text-center py-8 text-gray-500">
                  {availableVouchers.length === 0
                    ? "No active vouchers available"
                    : "No vouchers match your search"}
                </div>
              )
              : (
                filteredVouchers.value.map((voucher) => {
                  const selected = isSelected(voucher.id);
                  return (
                    <button
                      key={voucher.id}
                      onClick={() => toggleVoucher(voucher)}
                      disabled={!selected &&
                        selectedVouchers.length >= maxSelections}
                      class={`w-full text-left p-3 rounded-lg border-2 transition-all ${
                        selected
                          ? "border-blue-500 bg-blue-50"
                          : "border-gray-200 hover:border-gray-300 bg-white"
                      } ${
                        !selected && selectedVouchers.length >= maxSelections
                          ? "opacity-50 cursor-not-allowed"
                          : "cursor-pointer"
                      }`}
                    >
                      <div class="flex items-start justify-between gap-2">
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center gap-2 mb-1">
                            <span
                              class={`px-2 py-0.5 text-xs font-medium rounded ${
                                getTypeBadgeClass(voucher.voucherType)
                              }`}
                            >
                              {voucher.voucherType}
                            </span>
                            {voucher.platform && (
                              <span class="text-xs text-gray-500">
                                {voucher.platform}
                              </span>
                            )}
                          </div>
                          <h4 class="font-medium text-gray-900 truncate">
                            {voucher.name}
                          </h4>
                          <div class="flex items-center gap-2 mt-1 text-sm">
                            <span class="text-green-600 font-medium">
                              {formatDiscount(voucher)}
                            </span>
                            {voucher.minPurchase && (
                              <span class="text-gray-500">
                                • {formatMinPurchase(voucher.minPurchase)}
                              </span>
                            )}
                          </div>
                          {voucher.description && (
                            <p class="text-xs text-gray-600 mt-1 line-clamp-2">
                              {voucher.description}
                            </p>
                          )}
                        </div>
                        <div class="flex-shrink-0">
                          {selected
                            ? (
                              <svg
                                class="w-6 h-6 text-blue-600"
                                fill="currentColor"
                                viewBox="0 0 20 20"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                  clipRule="evenodd"
                                />
                              </svg>
                            )
                            : (
                              <svg
                                class="w-6 h-6 text-gray-300"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <circle
                                  cx="12"
                                  cy="12"
                                  r="10"
                                  strokeWidth="2"
                                />
                              </svg>
                            )}
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
          </div>

          {/* Selection limit warning */}
          {selectedVouchers.length >= maxSelections && (
            <div class="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p class="text-sm text-yellow-800">
                Maximum number of vouchers selected. Remove one to add another.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

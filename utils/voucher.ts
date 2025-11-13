/**
 * Voucher calculation and optimization engine
 */

import {
  AppliedVoucher,
  DiscountType,
  TaggedCartItem,
  TieredDiscount,
  VoucherApplicationResult,
  VoucherTemplate,
  VoucherType,
} from "../types/voucher.ts";

/**
 * Predefined voucher templates for common scenarios
 */
export const DEFAULT_VOUCHER_TEMPLATES: VoucherTemplate[] = [
  {
    id: "shopee-11-11",
    name: "Shopee 11.11 (15% off, max RM30)",
    type: VoucherType.ITEM_TAG,
    discountType: DiscountType.PERCENTAGE,
    discountValue: 15,
    conditions: {
      minPurchase: 5000, // RM50 in cents
      maxDiscount: 3000, // RM30 in cents
      requiredTags: ["11.11"],
    },
    description: "15% off on 11.11 tagged items, min RM50, max RM30 discount",
  },
  {
    id: "platform-flash-sale",
    name: "Platform Flash Sale (20% off, max RM15)",
    type: VoucherType.PLATFORM,
    discountType: DiscountType.PERCENTAGE,
    discountValue: 20,
    conditions: {
      minPurchase: 8000, // RM80 in cents
      maxDiscount: 1500, // RM15 in cents
    },
    description: "20% off entire cart, min RM80, max RM15 discount",
  },
  {
    id: "shop-tiered",
    name: "Shop Voucher (Tiered: RM10/RM25/RM50)",
    type: VoucherType.SHOP,
    discountType: DiscountType.FIXED,
    discountValue: 0, // Not used for tiered
    tieredDiscounts: [
      { minSpend: 10000, discount: 1000 }, // RM100 → RM10 off
      { minSpend: 20000, discount: 2500 }, // RM200 → RM25 off
      { minSpend: 30000, discount: 5000 }, // RM300 → RM50 off
    ],
    conditions: {
      maxDiscount: 5000, // RM50 cap
    },
    description: "Spend RM100 save RM10, RM200 save RM25, RM300 save RM50",
  },
  {
    id: "coins-redemption",
    name: "Shopee Coins (RM5 off)",
    type: VoucherType.PLATFORM,
    discountType: DiscountType.FIXED,
    discountValue: 500, // RM5 in cents
    conditions: {
      minPurchase: 3000, // RM30 in cents
    },
    description: "RM5 off, min RM30 purchase, no cap",
  },
  {
    id: "shipping-free",
    name: "Free Shipping (RM5 off)",
    type: VoucherType.PLATFORM,
    discountType: DiscountType.FIXED,
    discountValue: 500, // RM5 in cents
    conditions: {
      minPurchase: 2500, // RM25 in cents
    },
    description: "Free shipping (RM5 discount), min RM25",
  },
];

/**
 * Calculate the subtotal for items matching the voucher criteria
 */
function calculateEligibleSubtotal(
  items: TaggedCartItem[],
  voucher: VoucherTemplate,
): number {
  // For ITEM_TAG vouchers, only include items with required tags
  if (
    voucher.type === VoucherType.ITEM_TAG &&
    voucher.conditions?.requiredTags
  ) {
    const requiredTags = voucher.conditions.requiredTags;
    return items
      .filter((item) =>
        item.tags?.some((tag) => requiredTags.includes(tag))
      )
      .reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
  }

  // For PLATFORM and SHOP vouchers, include all items
  return items.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
}

/**
 * Get the best tier discount for a given spend amount
 */
function getBestTierDiscount(
  spendAmount: number,
  tiers?: TieredDiscount[],
): number {
  if (!tiers || tiers.length === 0) return 0;

  // Sort tiers by minSpend descending to find the highest applicable tier
  const sortedTiers = [...tiers].sort((a, b) => b.minSpend - a.minSpend);

  for (const tier of sortedTiers) {
    if (spendAmount >= tier.minSpend) {
      return tier.discount;
    }
  }

  return 0;
}

/**
 * Calculate the discount amount for a single voucher
 * Returns the effective discount after applying caps
 */
export function calculateVoucherDiscount(
  items: TaggedCartItem[],
  voucher: VoucherTemplate,
  currentSubtotal: number, // Current cart subtotal after previous vouchers
): {
  discount: number;
  isCapped: boolean;
  originalDiscount?: number;
  isValid: boolean;
  validationMessage?: string;
} {
  const eligibleSubtotal = calculateEligibleSubtotal(items, voucher);

  // Check minimum purchase requirement
  if (voucher.conditions?.minPurchase) {
    if (eligibleSubtotal < voucher.conditions.minPurchase) {
      const needed = voucher.conditions.minPurchase - eligibleSubtotal;
      return {
        discount: 0,
        isCapped: false,
        isValid: false,
        validationMessage:
          `Minimum purchase not met. Add RM${(needed / 100).toFixed(2)} more.`,
      };
    }
  }

  // Check required tags
  if (
    voucher.type === VoucherType.ITEM_TAG &&
    voucher.conditions?.requiredTags
  ) {
    const hasTaggedItems = items.some((item) =>
      item.tags?.some((tag) =>
        voucher.conditions!.requiredTags!.includes(tag)
      )
    );

    if (!hasTaggedItems) {
      return {
        discount: 0,
        isCapped: false,
        isValid: false,
        validationMessage: `No items with required tags: ${
          voucher.conditions.requiredTags.join(", ")
        }`,
      };
    }
  }

  let calculatedDiscount = 0;

  // Calculate discount based on type
  if (voucher.tieredDiscounts && voucher.tieredDiscounts.length > 0) {
    // Tiered discount (shop vouchers)
    calculatedDiscount = getBestTierDiscount(
      eligibleSubtotal,
      voucher.tieredDiscounts,
    );
  } else if (voucher.discountType === DiscountType.PERCENTAGE) {
    // Percentage discount
    calculatedDiscount = Math.round(
      (eligibleSubtotal * voucher.discountValue) / 100,
    );
  } else {
    // Fixed discount
    calculatedDiscount = voucher.discountValue;
  }

  // Apply cap if specified
  const maxDiscount = voucher.conditions?.maxDiscount;
  if (maxDiscount && calculatedDiscount > maxDiscount) {
    return {
      discount: maxDiscount,
      isCapped: true,
      originalDiscount: calculatedDiscount,
      isValid: true,
    };
  }

  // Ensure discount doesn't exceed current subtotal
  const effectiveDiscount = Math.min(calculatedDiscount, currentSubtotal);

  return {
    discount: effectiveDiscount,
    isCapped: effectiveDiscount < calculatedDiscount,
    originalDiscount: effectiveDiscount < calculatedDiscount
      ? calculatedDiscount
      : undefined,
    isValid: true,
  };
}

/**
 * Apply a list of vouchers in the given order and return results
 */
export function applyVouchers(
  items: TaggedCartItem[],
  vouchers: VoucherTemplate[],
): VoucherApplicationResult {
  const subtotal = items.reduce(
    (sum, item) => sum + item.unitPrice * item.quantity,
    0,
  );

  let currentSubtotal = subtotal;
  const appliedVouchers: AppliedVoucher[] = [];
  let totalDiscount = 0;

  for (const voucher of vouchers) {
    const result = calculateVoucherDiscount(items, voucher, currentSubtotal);

    appliedVouchers.push({
      ...voucher,
      calculatedDiscount: result.discount,
      isCapped: result.isCapped,
      originalDiscount: result.originalDiscount,
      isValid: result.isValid,
      validationMessage: result.validationMessage,
    });

    if (result.isValid) {
      totalDiscount += result.discount;
      currentSubtotal -= result.discount;
    }
  }

  return {
    appliedVouchers,
    subtotal,
    totalDiscount,
    finalTotal: Math.max(0, subtotal - totalDiscount),
    optimalOrder: false, // Will be set by optimization function
  };
}

/**
 * Find the optimal order to apply vouchers for maximum savings
 * Tests all permutations and returns the best order
 */
export function findOptimalVoucherOrder(
  items: TaggedCartItem[],
  vouchers: VoucherTemplate[],
): VoucherApplicationResult {
  if (vouchers.length === 0) {
    const subtotal = items.reduce(
      (sum, item) => sum + item.unitPrice * item.quantity,
      0,
    );
    return {
      appliedVouchers: [],
      subtotal,
      totalDiscount: 0,
      finalTotal: subtotal,
      optimalOrder: true,
    };
  }

  if (vouchers.length === 1) {
    const result = applyVouchers(items, vouchers);
    return { ...result, optimalOrder: true };
  }

  // Generate all permutations of vouchers
  const permutations = generatePermutations(vouchers);

  let bestResult: VoucherApplicationResult | null = null;
  let maxSavings = 0;

  for (const permutation of permutations) {
    const result = applyVouchers(items, permutation);

    if (result.totalDiscount > maxSavings) {
      maxSavings = result.totalDiscount;
      bestResult = result;
    }
  }

  if (bestResult) {
    return { ...bestResult, optimalOrder: true };
  }

  // Fallback
  const result = applyVouchers(items, vouchers);
  return { ...result, optimalOrder: true };
}

/**
 * Generate all permutations of an array
 * Uses Heap's algorithm for efficiency
 */
function generatePermutations<T>(array: T[]): T[][] {
  const results: T[][] = [];

  function permute(arr: T[], n: number = arr.length) {
    if (n === 1) {
      results.push([...arr]);
      return;
    }

    for (let i = 0; i < n; i++) {
      permute(arr, n - 1);

      // Swap elements
      if (n % 2 === 0) {
        [arr[i], arr[n - 1]] = [arr[n - 1], arr[i]];
      } else {
        [arr[0], arr[n - 1]] = [arr[n - 1], arr[0]];
      }
    }
  }

  permute([...array]);
  return results;
}

/**
 * Validate if a voucher can be applied to the cart
 */
export function validateVoucherConditions(
  items: TaggedCartItem[],
  voucher: VoucherTemplate,
): { isValid: boolean; message?: string } {
  const eligibleSubtotal = calculateEligibleSubtotal(items, voucher);

  // Check minimum purchase
  if (voucher.conditions?.minPurchase) {
    if (eligibleSubtotal < voucher.conditions.minPurchase) {
      const needed = voucher.conditions.minPurchase - eligibleSubtotal;
      return {
        isValid: false,
        message: `Add RM${(needed / 100).toFixed(2)} more to unlock`,
      };
    }
  }

  // Check required tags
  if (
    voucher.type === VoucherType.ITEM_TAG &&
    voucher.conditions?.requiredTags
  ) {
    const hasTaggedItems = items.some((item) =>
      item.tags?.some((tag) =>
        voucher.conditions!.requiredTags!.includes(tag)
      )
    );

    if (!hasTaggedItems) {
      return {
        isValid: false,
        message: `No items with tags: ${
          voucher.conditions.requiredTags.join(", ")
        }`,
      };
    }
  }

  return { isValid: true };
}

/**
 * Get effective discount description including cap information
 */
export function getDiscountDescription(voucher: AppliedVoucher): string {
  if (!voucher.isValid) {
    return voucher.validationMessage || "Invalid voucher";
  }

  const discountRM = (voucher.calculatedDiscount / 100).toFixed(2);

  if (voucher.isCapped && voucher.originalDiscount) {
    const originalRM = (voucher.originalDiscount / 100).toFixed(2);
    return `RM${discountRM} (capped from RM${originalRM})`;
  }

  return `RM${discountRM}`;
}

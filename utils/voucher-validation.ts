/**
 * Voucher validation utilities
 * Extracted from voucher.ts to eliminate duplication and improve testability
 */

import type { TaggedCartItem, VoucherTemplate } from "../types/voucher.ts";
import { VoucherType } from "../types/voucher.ts";
import { formatRMFromCents } from "./currency.ts";

/**
 * Validation result interface
 */
export interface ValidationResult {
  isValid: boolean;
  message?: string;
}

/**
 * Validate minimum purchase requirement
 */
export function validateMinimumPurchase(
  eligibleSubtotal: number,
  minPurchase?: number,
): ValidationResult {
  if (!minPurchase) {
    return { isValid: true };
  }

  if (eligibleSubtotal < minPurchase) {
    const needed = minPurchase - eligibleSubtotal;
    return {
      isValid: false,
      message: `Minimum purchase not met. Add RM${
        formatRMFromCents(needed)
      } more.`,
    };
  }

  return { isValid: true };
}

/**
 * Validate required tags for item-tag vouchers
 */
export function validateRequiredTags(
  items: TaggedCartItem[],
  requiredTags?: string[],
): ValidationResult {
  if (!requiredTags || requiredTags.length === 0) {
    return { isValid: true };
  }

  const hasTaggedItems = items.some((item) =>
    hasRequiredTags(item, requiredTags)
  );

  if (!hasTaggedItems) {
    return {
      isValid: false,
      message: `No items with required tags: ${requiredTags.join(", ")}`,
    };
  }

  return { isValid: true };
}

/**
 * Check if an item has any of the required tags
 */
export function hasRequiredTags(
  item: TaggedCartItem,
  requiredTags: string[],
): boolean {
  if (!item.tags || item.tags.length === 0) return false;
  return item.tags.some((tag) => requiredTags.includes(tag));
}

/**
 * Validate all voucher conditions
 */
export function validateVoucherConditions(
  items: TaggedCartItem[],
  voucher: VoucherTemplate,
  eligibleSubtotal: number,
): ValidationResult {
  // Validate minimum purchase
  const minPurchaseValidation = validateMinimumPurchase(
    eligibleSubtotal,
    voucher.conditions?.minPurchase,
  );
  if (!minPurchaseValidation.isValid) {
    return minPurchaseValidation;
  }

  // Validate required tags for ITEM_TAG vouchers
  if (voucher.type === VoucherType.ITEM_TAG) {
    const tagsValidation = validateRequiredTags(
      items,
      voucher.conditions?.requiredTags,
    );
    if (!tagsValidation.isValid) {
      return tagsValidation;
    }
  }

  return { isValid: true };
}

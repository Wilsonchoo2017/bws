/**
 * Type conversion utilities for voucher system
 */

import type {
  AppliedVoucher,
  TaggedCartItem,
  VoucherTemplate,
} from "../types/voucher.ts";
import type { CartItem } from "./cart.ts";

/**
 * Convert CartItem to TaggedCartItem (ensures quantity is defined)
 */
export function toTaggedCartItem(item: CartItem): TaggedCartItem {
  return {
    ...item,
    quantity: item.quantity || 1,
  };
}

/**
 * Convert array of CartItems to TaggedCartItems
 */
export function toTaggedCartItems(items: CartItem[]): TaggedCartItem[] {
  return items.map(toTaggedCartItem);
}

/**
 * Convert AppliedVoucher back to VoucherTemplate
 * Strips out calculation results (discount, isCapped, etc.)
 */
export function toVoucherTemplate(applied: AppliedVoucher): VoucherTemplate {
  const {
    calculatedDiscount: _,
    isCapped: __,
    originalDiscount: ___,
    isValid: ____,
    validationMessage: _____,
    ...template
  } = applied;
  return template;
}

/**
 * Convert array of AppliedVouchers to VoucherTemplates
 */
export function toVoucherTemplates(
  applied: AppliedVoucher[],
): VoucherTemplate[] {
  return applied.map(toVoucherTemplate);
}

/**
 * Parse comma-separated tags from input string
 */
export function parseTagsFromInput(input: string): string[] | undefined {
  if (!input || !input.trim()) return undefined;

  const parsed = input
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  return parsed.length > 0 ? parsed : undefined;
}

/**
 * Convert tags array to comma-separated string
 */
export function tagsToString(tags?: string[]): string {
  return tags?.join(", ") || "";
}

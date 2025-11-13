/**
 * Voucher types and interfaces for cart discount simulation
 */

/**
 * Type of voucher discount
 */
export enum VoucherType {
  PLATFORM = "platform", // Platform-wide vouchers (e.g., Shopee vouchers)
  SHOP = "shop", // Shop-specific vouchers
  ITEM_TAG = "item_tag", // Vouchers that require specific item tags
}

/**
 * How the discount is calculated
 */
export enum DiscountType {
  PERCENTAGE = "percentage", // Percentage off (e.g., 15%)
  FIXED = "fixed", // Fixed amount off (e.g., RM10)
}

/**
 * Tiered discount structure for shop vouchers
 * Example: Spend RM100 save RM10, spend RM200 save RM25
 */
export interface TieredDiscount {
  minSpend: number; // Minimum spend in cents to unlock this tier
  discount: number; // Discount amount in cents
}

/**
 * Conditions that must be met for a voucher to be applied
 */
export interface VoucherConditions {
  minPurchase?: number; // Minimum cart value in cents
  requiredTags?: string[]; // Tags that items must have (e.g., ["11.11"])
  maxDiscount?: number; // Maximum discount cap in cents (e.g., RM30 = 3000)
  maxUsagePerUser?: number; // Usage limit (for future use)
}

/**
 * Voucher template that can be saved and reused
 */
export interface VoucherTemplate {
  id: string; // Unique identifier
  name: string; // Display name (e.g., "Shopee 11.11 15% off")
  type: VoucherType;
  discountType: DiscountType;
  discountValue: number; // Percentage (0-100) or fixed amount in cents
  tieredDiscounts?: TieredDiscount[]; // For shop vouchers with spending tiers
  conditions?: VoucherConditions;
  description?: string; // Optional description
}

/**
 * Applied voucher with calculated discount information
 */
export interface AppliedVoucher extends VoucherTemplate {
  calculatedDiscount: number; // Actual discount applied in cents
  isCapped: boolean; // Whether the discount was limited by maxDiscount
  originalDiscount?: number; // Original discount before cap (if capped)
  isValid: boolean; // Whether voucher conditions were met
  validationMessage?: string; // Reason if voucher is not valid
}

/**
 * Result of applying vouchers to a cart
 */
export interface VoucherApplicationResult {
  appliedVouchers: AppliedVoucher[];
  subtotal: number; // Cart subtotal before vouchers (in cents)
  totalDiscount: number; // Total discount from all vouchers (in cents)
  finalTotal: number; // Final cart total after vouchers (in cents)
  optimalOrder: boolean; // Whether vouchers are in optimal order
}

/**
 * Cart item with tag support for voucher filtering
 */
export interface TaggedCartItem {
  id: string;
  legoId: string;
  unitPrice: number; // In cents
  quantity: number;
  tags?: string[]; // Tags like "11.11", "Flash Sale", etc.
}

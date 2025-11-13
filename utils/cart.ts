import type { VoucherTemplate } from "../types/voucher.ts";
import {
  safeLoadFromStorage,
  safeLoadNumber,
  safeSaveNumber,
  safeSaveToStorage,
  StorageKeys,
} from "./storage.ts";

export interface CartItem {
  id: string; // UUID for cart item
  legoId: string; // LEGO set number
  unitPrice: number; // In cents (already discounted at item level)
  quantity?: number;
  purchaseDate?: string; // ISO date string
  platform?: string; // e.g., "Shopee", "ToysRUs"
  notes?: string;
  tags?: string[]; // Tags for voucher filtering (e.g., ["11.11", "Flash Sale"])
  addedAt: string; // ISO timestamp
}

/**
 * Load total cart price from localStorage
 */
export function loadTotalCartPrice(): number {
  return safeLoadNumber(
    StorageKeys.CART_TOTAL_PRICE,
    0,
    "load total cart price",
  );
}

/**
 * Save total cart price to localStorage
 */
export function saveTotalCartPrice(priceInCents: number): void {
  safeSaveNumber(
    StorageKeys.CART_TOTAL_PRICE,
    priceInCents,
    "save total cart price",
  );
}

/**
 * Calculate total unit price (before cart-level discounts) across all cart items
 */
export function calculateCartSubtotal(items: CartItem[]): number {
  return items.reduce((total, item) => {
    const quantity = item.quantity || 1;
    return total + item.unitPrice * quantity;
  }, 0);
}

/**
 * Calculate final price for a single item based on proportional distribution of cart discount
 */
export function calculateItemFinalPrice(
  item: CartItem,
  cartSubtotal: number,
  totalCartPrice: number,
): number {
  if (cartSubtotal <= 0) return item.unitPrice * (item.quantity || 1);

  const quantity = item.quantity || 1;
  const itemSubtotal = item.unitPrice * quantity;

  // Proportionally distribute the total cart price
  const proportion = itemSubtotal / cartSubtotal;
  return Math.round(totalCartPrice * proportion);
}

/**
 * Calculate total final price across all cart items (uses stored totalCartPrice or falls back to subtotal)
 */
export function calculateCartTotal(items: CartItem[]): number {
  const totalCartPrice = loadTotalCartPrice();

  // If no total cart price is set, return subtotal (no cart-level discount)
  if (totalCartPrice <= 0) {
    return calculateCartSubtotal(items);
  }

  return totalCartPrice;
}

/**
 * Calculate total savings (subtotal - total cart price)
 */
export function calculateTotalSavings(items: CartItem[]): number {
  const subtotal = calculateCartSubtotal(items);
  const totalCartPrice = loadTotalCartPrice();

  // If no total cart price is set, no savings
  if (totalCartPrice <= 0) return 0;

  return subtotal - totalCartPrice;
}

/**
 * Calculate savings for a single item based on proportional distribution
 */
export function calculateItemSavings(
  item: CartItem,
  cartSubtotal: number,
  totalCartPrice: number,
): number {
  const quantity = item.quantity || 1;
  const itemSubtotal = item.unitPrice * quantity;
  const itemFinalPrice = calculateItemFinalPrice(
    item,
    cartSubtotal,
    totalCartPrice,
  );

  return itemSubtotal - itemFinalPrice;
}

/**
 * Calculate discount percentage for entire cart
 */
export function calculateCartDiscountPercentage(items: CartItem[]): number {
  const subtotal = calculateCartSubtotal(items);
  if (subtotal <= 0) return 0;

  const totalCartPrice = loadTotalCartPrice();
  if (totalCartPrice <= 0) return 0;

  return ((subtotal - totalCartPrice) / subtotal) * 100;
}

/**
 * Load cart items from localStorage
 */
export function loadCartItems(): CartItem[] {
  return safeLoadFromStorage<CartItem[]>(
    StorageKeys.CART_ITEMS,
    [],
    "load cart items",
  );
}

/**
 * Save cart items to localStorage
 */
export function saveCartItems(items: CartItem[]): void {
  safeSaveToStorage(StorageKeys.CART_ITEMS, items, "save cart items");
}

/**
 * Generate a unique ID for cart items
 */
export function generateCartItemId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Add item to cart (finalPrice is calculated, not stored)
 */
export function addCartItem(item: Omit<CartItem, "id" | "addedAt">): CartItem {
  const newItem: CartItem = {
    ...item,
    id: generateCartItemId(),
    addedAt: new Date().toISOString(),
  };

  const items = loadCartItems();
  items.push(newItem);
  saveCartItems(items);

  return newItem;
}

/**
 * Update cart item
 */
export function updateCartItem(
  id: string,
  updates: Partial<Omit<CartItem, "id" | "addedAt">>,
): boolean {
  const items = loadCartItems();
  const index = items.findIndex((item) => item.id === id);

  if (index === -1) return false;

  items[index] = { ...items[index], ...updates };
  saveCartItems(items);

  return true;
}

/**
 * Remove cart item
 */
export function removeCartItem(id: string): boolean {
  const items = loadCartItems();
  const filtered = items.filter((item) => item.id !== id);

  if (filtered.length === items.length) return false;

  saveCartItems(filtered);
  return true;
}

/**
 * Clear all cart items
 */
export function clearCart(): void {
  saveCartItems([]);
}

/**
 * Load applied vouchers from localStorage
 */
export function loadAppliedVouchers(): VoucherTemplate[] {
  return safeLoadFromStorage<VoucherTemplate[]>(
    StorageKeys.CART_VOUCHERS,
    [],
    "load applied vouchers",
  );
}

/**
 * Save applied vouchers to localStorage
 */
export function saveAppliedVouchers(vouchers: VoucherTemplate[]): void {
  safeSaveToStorage(
    StorageKeys.CART_VOUCHERS,
    vouchers,
    "save applied vouchers",
  );
}

/**
 * Load user-saved voucher templates from localStorage
 */
export function loadVoucherTemplates(): VoucherTemplate[] {
  return safeLoadFromStorage<VoucherTemplate[]>(
    StorageKeys.VOUCHER_TEMPLATES,
    [],
    "load voucher templates",
  );
}

/**
 * Save user voucher templates to localStorage
 */
export function saveVoucherTemplates(templates: VoucherTemplate[]): void {
  safeSaveToStorage(
    StorageKeys.VOUCHER_TEMPLATES,
    templates,
    "save voucher templates",
  );
}

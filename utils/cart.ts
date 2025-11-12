export interface CartItem {
  id: string; // UUID for cart item
  legoId: string; // LEGO set number
  unitPrice: number; // In cents
  finalPrice: number; // In cents (after all discounts)
  quantity?: number;
  purchaseDate?: string; // ISO date string
  platform?: string; // e.g., "Shopee", "ToysRUs"
  notes?: string;
  addedAt: string; // ISO timestamp
}

const CART_STORAGE_KEY = "lego-cart-items";

/**
 * Calculate discount percentage for a cart item
 */
export function calculateDiscountPercentage(
  unitPrice: number,
  finalPrice: number,
): number {
  if (unitPrice <= 0) return 0;
  return ((unitPrice - finalPrice) / unitPrice) * 100;
}

/**
 * Calculate total savings (unit price - final price) * quantity
 */
export function calculateItemSavings(item: CartItem): number {
  const quantity = item.quantity || 1;
  return (item.unitPrice - item.finalPrice) * quantity;
}

/**
 * Calculate total savings across all cart items
 */
export function calculateTotalSavings(items: CartItem[]): number {
  return items.reduce((total, item) => total + calculateItemSavings(item), 0);
}

/**
 * Calculate total final price across all cart items
 */
export function calculateCartTotal(items: CartItem[]): number {
  return items.reduce((total, item) => {
    const quantity = item.quantity || 1;
    return total + item.finalPrice * quantity;
  }, 0);
}

/**
 * Calculate total unit price (before discounts) across all cart items
 */
export function calculateCartSubtotal(items: CartItem[]): number {
  return items.reduce((total, item) => {
    const quantity = item.quantity || 1;
    return total + item.unitPrice * quantity;
  }, 0);
}

/**
 * Load cart items from localStorage
 */
export function loadCartItems(): CartItem[] {
  if (typeof window === "undefined") return [];

  try {
    const stored = localStorage.getItem(CART_STORAGE_KEY);
    if (!stored) return [];
    return JSON.parse(stored);
  } catch (error) {
    console.error("Failed to load cart items:", error);
    return [];
  }
}

/**
 * Save cart items to localStorage
 */
export function saveCartItems(items: CartItem[]): void {
  if (typeof window === "undefined") return;

  try {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
  } catch (error) {
    console.error("Failed to save cart items:", error);
  }
}

/**
 * Generate a unique ID for cart items
 */
export function generateCartItemId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Add item to cart
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

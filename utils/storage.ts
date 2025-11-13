/**
 * Generic localStorage utilities with error handling
 * Eliminates duplicate try-catch patterns throughout the codebase
 */

/**
 * Storage keys used throughout the application
 */
export const StorageKeys = {
  CART_ITEMS: "lego-cart-items",
  CART_TOTAL_PRICE: "lego-cart-total-price",
  CART_VOUCHERS: "lego-cart-vouchers",
  VOUCHER_TEMPLATES: "lego-cart-voucher-templates",
} as const;

/**
 * Safely load data from localStorage with error handling
 */
export function safeLoadFromStorage<T>(
  key: string,
  defaultValue: T,
  errorContext: string,
): T {
  if (typeof window === "undefined") return defaultValue;

  try {
    const stored = localStorage.getItem(key);
    if (!stored) return defaultValue;
    return JSON.parse(stored);
  } catch (error) {
    console.error(`Failed to ${errorContext}:`, error);
    return defaultValue;
  }
}

/**
 * Safely save data to localStorage with error handling
 */
export function safeSaveToStorage<T>(
  key: string,
  value: T,
  errorContext: string,
): void {
  if (typeof window === "undefined") return;

  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error(`Failed to ${errorContext}:`, error);
  }
}

/**
 * Safely load a number from localStorage
 */
export function safeLoadNumber(
  key: string,
  defaultValue: number,
  errorContext: string,
): number {
  if (typeof window === "undefined") return defaultValue;

  try {
    const stored = localStorage.getItem(key);
    if (!stored) return defaultValue;
    const parsed = parseFloat(stored);
    return isNaN(parsed) ? defaultValue : parsed;
  } catch (error) {
    console.error(`Failed to ${errorContext}:`, error);
    return defaultValue;
  }
}

/**
 * Safely save a number to localStorage
 */
export function safeSaveNumber(
  key: string,
  value: number,
  errorContext: string,
): void {
  if (typeof window === "undefined") return;

  try {
    localStorage.setItem(key, value.toString());
  } catch (error) {
    console.error(`Failed to ${errorContext}:`, error);
  }
}

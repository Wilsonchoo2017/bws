/**
 * Currency conversion utilities for RM (Malaysian Ringgit)
 * All prices are stored in cents for precision
 */

const CENTS_PER_RM = 100;

/**
 * Convert cents to RM
 */
export function centsToRM(cents: number): number {
  return cents / CENTS_PER_RM;
}

/**
 * Convert RM to cents
 */
export function rmToCents(rm: number): number {
  return Math.round(rm * CENTS_PER_RM);
}

/**
 * Format cents as RM string with optional decimals
 */
export function formatRMFromCents(cents: number, decimals = 2): string {
  return centsToRM(cents).toFixed(decimals);
}

/**
 * Parse RM string/number input to cents
 */
export function parseRMToCents(input: string | number): number {
  const rm = typeof input === "string" ? parseFloat(input) : input;
  if (isNaN(rm)) return 0;
  return rmToCents(rm);
}

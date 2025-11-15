/**
 * Price Type System
 *
 * This module provides type-safe handling of monetary values throughout the application.
 *
 * CONVENTION: All prices are stored and calculated in CENTS (smallest currency unit).
 * Only convert to dollars for display purposes.
 *
 * @example
 * // Converting from dollars to cents
 * const price: Cents = dollarsToCents(49.99);  // 4999 cents
 *
 * // Converting from string
 * const parsed: Cents = centsFromString("RM 49.99");  // 4999 cents
 *
 * // Formatting for display
 * const display = formatCents(price, "MYR");  // "RM 49.99"
 */

/**
 * Branded type for prices in cents (smallest currency unit).
 * Use this type for all price storage, calculations, and business logic.
 */
export type Cents = number & { readonly __brand: "cents" };

/**
 * Branded type for prices in dollars (base currency unit).
 * Use this type only for display or when interfacing with external APIs that require dollars.
 */
export type Dollars = number & { readonly __brand: "dollars" };

/**
 * Converts dollars to cents.
 * @param dollars - Price in dollars (e.g., 49.99)
 * @returns Price in cents (e.g., 4999)
 */
export function dollarsToCents(dollars: number): Cents {
  if (!isFinite(dollars)) {
    throw new Error(`Invalid dollar amount: ${dollars}`);
  }
  return Math.round(dollars * 100) as Cents;
}

/**
 * Converts cents to dollars.
 * @param cents - Price in cents (e.g., 4999)
 * @returns Price in dollars (e.g., 49.99)
 */
export function centsToDollars(cents: Cents): Dollars {
  if (!isValidCents(cents)) {
    throw new Error(`Invalid cents amount: ${cents}`);
  }
  return (cents / 100) as Dollars;
}

/**
 * Parses a price string and converts to cents.
 * Handles various formats: "RM 49.99", "$49.99", "49.99", "1,234.56"
 *
 * @param priceStr - String representation of price
 * @returns Price in cents, or null if parsing fails
 */
export function centsFromString(priceStr: string): Cents | null {
  const cleanPrice = priceStr
    .replace(/RM/gi, "")
    .replace(/\$/g, "")
    .replace(/,/g, "")
    .trim();

  const price = parseFloat(cleanPrice);

  if (isNaN(price) || !isFinite(price)) {
    return null;
  }

  const cents = Math.round(price * 100);
  return isValidCents(cents) ? (cents as Cents) : null;
}

/**
 * Converts a raw number to Cents type (use when you're certain the value is already in cents).
 * @param value - Numeric value in cents
 * @returns Branded Cents type
 */
export function asCents(value: number): Cents {
  if (!isValidCents(value)) {
    throw new Error(
      `Invalid cents value: ${value}. Must be a non-negative integer.`,
    );
  }
  return value as Cents;
}

/**
 * Safely converts a database price (number | null) to Cents type.
 * Returns null if the input is null or invalid.
 * Use this when reading prices from the database.
 *
 * @param value - Price from database (may be null)
 * @returns Branded Cents type or null
 */
export function priceFromDb(value: number | null | undefined): Cents | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (!isValidCents(value)) {
    console.warn(`[priceFromDb] Invalid price from database: ${value}`);
    return null;
  }
  return value as Cents;
}

/**
 * Converts a raw number to Dollars type (use when you're certain the value is in dollars).
 * @param value - Numeric value in dollars
 * @returns Branded Dollars type
 */
export function asDollars(value: number): Dollars {
  if (!isFinite(value)) {
    throw new Error(`Invalid dollars value: ${value}`);
  }
  return value as Dollars;
}

/**
 * Validates that a value is a valid price in cents.
 * @param value - Value to validate
 * @returns True if value is valid cents (non-negative integer)
 */
export function isValidCents(value: unknown): value is Cents {
  return (
    typeof value === "number" &&
    isFinite(value) &&
    value >= 0 &&
    Math.round(value) === value // Must be an integer
  );
}

/**
 * Validates that a value is a valid price in dollars.
 * @param value - Value to validate
 * @returns True if value is valid dollars (non-negative number)
 */
export function isValidDollars(value: unknown): value is Dollars {
  return typeof value === "number" && isFinite(value) && value >= 0;
}

/**
 * Asserts that a value is valid cents, throwing an error if not.
 * @param value - Value to check
 * @param context - Optional context for error message
 * @throws Error if value is not valid cents
 */
export function assertCents(
  value: unknown,
  context?: string,
): asserts value is Cents {
  if (!isValidCents(value)) {
    const msg = context
      ? `Expected valid cents in ${context}, got: ${value}`
      : `Expected valid cents, got: ${value}`;
    throw new Error(msg);
  }
}

/**
 * Asserts that a value is valid dollars, throwing an error if not.
 * @param value - Value to check
 * @param context - Optional context for error message
 * @throws Error if value is not valid dollars
 */
export function assertDollars(
  value: unknown,
  context?: string,
): asserts value is Dollars {
  if (!isValidDollars(value)) {
    const msg = context
      ? `Expected valid dollars in ${context}, got: ${value}`
      : `Expected valid dollars, got: ${value}`;
    throw new Error(msg);
  }
}

/**
 * Formats cents as a currency string for display.
 * @param cents - Price in cents
 * @param currency - Currency code (default: "MYR")
 * @param locale - Locale for formatting (default: "en-MY")
 * @returns Formatted price string (e.g., "RM 49.99")
 */
export function formatCents(
  cents: Cents | null | undefined,
  currency: string = "MYR",
  locale: string = "en-MY",
): string {
  if (cents === null || cents === undefined) {
    return "N/A";
  }

  assertCents(cents, "formatCents");

  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

/**
 * Formats dollars as a currency string for display.
 * @param dollars - Price in dollars
 * @param currency - Currency code (default: "MYR")
 * @param locale - Locale for formatting (default: "en-MY")
 * @returns Formatted price string (e.g., "RM 49.99")
 */
export function formatDollars(
  dollars: Dollars | null | undefined,
  currency: string = "MYR",
  locale: string = "en-MY",
): string {
  if (dollars === null || dollars === undefined) {
    return "N/A";
  }

  assertDollars(dollars, "formatDollars");

  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(dollars);
}

/**
 * Formats a price delta (difference) in cents.
 * @param deltaCents - Price difference in cents
 * @param currency - Currency code (default: "MYR")
 * @returns Formatted delta with +/- prefix
 */
export function formatCentsDelta(
  deltaCents: Cents | null,
  currency: string = "MYR",
): { text: string; isPositive: boolean } | null {
  if (deltaCents === null || deltaCents === undefined) {
    return null;
  }

  const isPositive = deltaCents >= 0;
  const prefix = isPositive ? "+" : "";
  const dollars = Math.abs(deltaCents) / 100;
  const formatted = dollars.toFixed(2);

  return {
    text: `${prefix}${currency} ${formatted}`,
    isPositive,
  };
}

/**
 * Safely adds two prices in cents.
 * @param a - First price
 * @param b - Second price
 * @returns Sum in cents
 */
export function addCents(a: Cents, b: Cents): Cents {
  assertCents(a, "addCents first argument");
  assertCents(b, "addCents second argument");
  return asCents(a + b);
}

/**
 * Safely subtracts two prices in cents.
 * @param a - Minuend
 * @param b - Subtrahend
 * @returns Difference in cents
 */
export function subtractCents(a: Cents, b: Cents): Cents {
  assertCents(a, "subtractCents first argument");
  assertCents(b, "subtractCents second argument");
  const result = a - b;
  if (result < 0) {
    throw new Error(
      `Subtraction would result in negative price: ${a} - ${b} = ${result}`,
    );
  }
  return asCents(result);
}

/**
 * Multiplies a price in cents by a multiplier.
 * @param cents - Price in cents
 * @param multiplier - Multiplier (e.g., 1.5 for 50% increase)
 * @returns Product in cents
 */
export function multiplyCents(cents: Cents, multiplier: number): Cents {
  assertCents(cents, "multiplyCents first argument");
  if (!isFinite(multiplier)) {
    throw new Error(`Invalid multiplier: ${multiplier}`);
  }
  return asCents(Math.round(cents * multiplier));
}

/**
 * Divides a price in cents by a divisor.
 * @param cents - Price in cents
 * @param divisor - Divisor
 * @returns Quotient in cents
 */
export function divideCents(cents: Cents, divisor: number): Cents {
  assertCents(cents, "divideCents first argument");
  if (!isFinite(divisor) || divisor === 0) {
    throw new Error(`Invalid divisor: ${divisor}`);
  }
  return asCents(Math.round(cents / divisor));
}

/**
 * Calculates percentage difference between two prices.
 * @param current - Current price in cents
 * @param target - Target price in cents
 * @returns Percentage difference (positive if current > target)
 */
export function percentageDifference(current: Cents, target: Cents): number {
  assertCents(current, "percentageDifference current");
  assertCents(target, "percentageDifference target");

  if (target === 0) {
    return current === 0 ? 0 : Infinity;
  }

  return ((current - target) / target) * 100;
}

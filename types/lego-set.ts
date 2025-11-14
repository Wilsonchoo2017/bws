/**
 * Type-safe LEGO Set Number System
 *
 * This module provides branded types to distinguish between:
 * - Base LEGO set numbers (e.g., "60365")
 * - Bricklink item IDs (e.g., "60365-1")
 *
 * Branded types provide compile-time type safety without runtime overhead,
 * preventing accidental mixing of the two formats.
 *
 * Pattern follows the Cents branded type pattern used elsewhere in the codebase.
 */

/**
 * Base LEGO set number without any suffix
 * Format: 5 digits (e.g., "60365", "10332")
 *
 * This is the canonical LEGO set number as used by LEGO themselves.
 */
export type BaseSetNumber = string & { readonly __brand: "BaseSetNumber" };

/**
 * Bricklink item ID with -1 suffix for primary variant
 * Format: 5 digits + "-1" (e.g., "60365-1", "10332-1")
 *
 * This is the format required by Bricklink URLs and their database.
 * The "-1" suffix indicates the primary/standard variant of a set.
 */
export type BricklinkItemId = string & { readonly __brand: "BricklinkItemId" };

/**
 * Regular expression for validating base LEGO set numbers
 * Matches: 5 digits only
 */
const BASE_SET_NUMBER_REGEX = /^\d{5}$/;

/**
 * Regular expression for validating Bricklink item IDs
 * Matches: 5 digits followed by "-1"
 */
const BRICKLINK_ITEM_ID_REGEX = /^\d{5}-1$/;

/**
 * Validate and cast a string to BaseSetNumber
 *
 * @param value - String to validate (should be 5 digits)
 * @returns Branded BaseSetNumber
 * @throws Error if format is invalid
 *
 * @example
 * const setNumber = asBaseSetNumber("60365"); // ✓ Valid
 * const invalid = asBaseSetNumber("60365-1"); // ✗ Throws error
 */
export function asBaseSetNumber(value: string): BaseSetNumber {
  const trimmed = value.trim();

  if (!BASE_SET_NUMBER_REGEX.test(trimmed)) {
    throw new Error(
      `Invalid base set number: "${value}". Expected 5 digits (e.g., "60365")`,
    );
  }

  return trimmed as BaseSetNumber;
}

/**
 * Validate and cast a string to BricklinkItemId
 *
 * @param value - String to validate (should be 5 digits + "-1")
 * @returns Branded BricklinkItemId
 * @throws Error if format is invalid
 *
 * @example
 * const itemId = asBricklinkItemId("60365-1"); // ✓ Valid
 * const invalid = asBricklinkItemId("60365"); // ✗ Throws error
 */
export function asBricklinkItemId(value: string): BricklinkItemId {
  const trimmed = value.trim();

  if (!BRICKLINK_ITEM_ID_REGEX.test(trimmed)) {
    throw new Error(
      `Invalid Bricklink item ID: "${value}". Expected format: "NNNNN-1" (e.g., "60365-1")`,
    );
  }

  return trimmed as BricklinkItemId;
}

/**
 * Convert BaseSetNumber to BricklinkItemId by appending "-1"
 *
 * @param base - Base LEGO set number
 * @returns Bricklink item ID with -1 suffix
 *
 * @example
 * const base = asBaseSetNumber("60365");
 * const itemId = toBricklinkItemId(base); // "60365-1"
 */
export function toBricklinkItemId(base: BaseSetNumber): BricklinkItemId {
  return `${base}-1` as BricklinkItemId;
}

/**
 * Convert BricklinkItemId to BaseSetNumber by removing "-1" suffix
 *
 * @param itemId - Bricklink item ID
 * @returns Base LEGO set number without suffix
 *
 * @example
 * const itemId = asBricklinkItemId("60365-1");
 * const base = toBaseSetNumber(itemId); // "60365"
 */
export function toBaseSetNumber(itemId: BricklinkItemId): BaseSetNumber {
  return itemId.replace(/-1$/, "") as BaseSetNumber;
}

/**
 * Try to parse a string that might be either format
 * Returns an object with both formats
 *
 * @param value - String that might be base or Bricklink format
 * @returns Object with both base and Bricklink formats
 * @throws Error if value doesn't match either format
 *
 * @example
 * parseLegoSetNumber("60365")    // { base: "60365", bricklink: "60365-1" }
 * parseLegoSetNumber("60365-1")  // { base: "60365", bricklink: "60365-1" }
 * parseLegoSetNumber("invalid")  // throws Error
 */
export function parseLegoSetNumber(
  value: string,
): { base: BaseSetNumber; bricklink: BricklinkItemId } {
  const trimmed = value.trim();

  // Try base format first
  if (BASE_SET_NUMBER_REGEX.test(trimmed)) {
    const base = trimmed as BaseSetNumber;
    return {
      base,
      bricklink: toBricklinkItemId(base),
    };
  }

  // Try Bricklink format
  if (BRICKLINK_ITEM_ID_REGEX.test(trimmed)) {
    const bricklink = trimmed as BricklinkItemId;
    return {
      base: toBaseSetNumber(bricklink),
      bricklink,
    };
  }

  throw new Error(
    `Invalid LEGO set number format: "${value}". ` +
      `Expected either base format (e.g., "60365") or Bricklink format (e.g., "60365-1")`,
  );
}

/**
 * Build a Bricklink catalog URL for an item
 *
 * @param itemId - Bricklink item ID (must include -1 suffix)
 * @param itemType - Bricklink item type (default: "S" for sets)
 * @returns Complete Bricklink catalog URL
 *
 * @example
 * const itemId = asBricklinkItemId("60365-1");
 * const url = buildBricklinkCatalogUrl(itemId);
 * // "https://www.bricklink.com/v2/catalog/catalogitem.page?S=60365-1"
 */
export function buildBricklinkCatalogUrl(
  itemId: BricklinkItemId,
  itemType: string = "S",
): string {
  return `https://www.bricklink.com/v2/catalog/catalogitem.page?${itemType}=${itemId}`;
}

/**
 * Validate if a string is a valid base set number (without throwing)
 *
 * @param value - String to validate
 * @returns true if valid base set number, false otherwise
 *
 * @example
 * isValidBaseSetNumber("60365")   // true
 * isValidBaseSetNumber("60365-1") // false
 */
export function isValidBaseSetNumber(value: string): value is BaseSetNumber {
  return BASE_SET_NUMBER_REGEX.test(value.trim());
}

/**
 * Validate if a string is a valid Bricklink item ID (without throwing)
 *
 * @param value - String to validate
 * @returns true if valid Bricklink item ID, false otherwise
 *
 * @example
 * isValidBricklinkItemId("60365-1") // true
 * isValidBricklinkItemId("60365")   // false
 */
export function isValidBricklinkItemId(
  value: string,
): value is BricklinkItemId {
  return BRICKLINK_ITEM_ID_REGEX.test(value.trim());
}

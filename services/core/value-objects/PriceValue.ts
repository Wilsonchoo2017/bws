import type { Cents } from "../../../types/price.ts";

/**
 * Value object for handling monetary values
 * Encapsulates cents/dollars conversion logic to eliminate duplication
 *
 * DESIGN PRINCIPLES:
 * - Immutable: All operations return new instances
 * - Type-safe: Uses branded Cents type
 * - DRY: Single source of truth for price conversions
 * - Pure: No side effects, deterministic outputs
 */
export class PriceValue {
  private readonly _cents: Cents;

  private constructor(cents: number) {
    if (!Number.isInteger(cents) || cents < 0) {
      throw new Error(`Invalid price: ${cents} cents. Must be a non-negative integer.`);
    }
    this._cents = cents as Cents;
  }

  /**
   * Create PriceValue from cents (integer)
   */
  static fromCents(cents: number | Cents): PriceValue {
    return new PriceValue(cents);
  }

  /**
   * Create PriceValue from dollars (will be converted to cents)
   * @param dollars - Dollar amount (will be rounded to nearest cent)
   */
  static fromDollars(dollars: number): PriceValue {
    const cents = Math.round(dollars * 100);
    return new PriceValue(cents);
  }

  /**
   * Create PriceValue representing zero
   */
  static zero(): PriceValue {
    return new PriceValue(0);
  }

  /**
   * Get value in cents (branded type)
   */
  toCents(): Cents {
    return this._cents;
  }

  /**
   * Get value in dollars (decimal)
   */
  toDollars(): number {
    return this._cents / 100;
  }

  /**
   * Format as dollar string (e.g., "$12.34")
   */
  format(options?: { includeCents?: boolean; currency?: string }): string {
    const { includeCents = true, currency = "$" } = options ?? {};
    const dollars = this.toDollars();

    if (includeCents) {
      return `${currency}${dollars.toFixed(2)}`;
    }
    return `${currency}${Math.round(dollars)}`;
  }

  /**
   * Add another price value
   */
  add(other: PriceValue): PriceValue {
    return PriceValue.fromCents(this._cents + other._cents);
  }

  /**
   * Subtract another price value
   */
  subtract(other: PriceValue): PriceValue {
    const result = this._cents - other._cents;
    if (result < 0) {
      throw new Error("Cannot subtract to negative price");
    }
    return PriceValue.fromCents(result);
  }

  /**
   * Multiply by a scalar (e.g., multiplier, percentage)
   */
  multiply(multiplier: number): PriceValue {
    if (multiplier < 0) {
      throw new Error("Cannot multiply by negative value");
    }
    const result = Math.round(this._cents * multiplier);
    return PriceValue.fromCents(result);
  }

  /**
   * Divide by a scalar
   */
  divide(divisor: number): PriceValue {
    if (divisor <= 0) {
      throw new Error("Cannot divide by zero or negative value");
    }
    const result = Math.round(this._cents / divisor);
    return PriceValue.fromCents(result);
  }

  /**
   * Calculate percentage of this price
   * @param percent - Percentage (e.g., 20 for 20%)
   */
  percentage(percent: number): PriceValue {
    return this.multiply(percent / 100);
  }

  /**
   * Compare with another price
   */
  isGreaterThan(other: PriceValue): boolean {
    return this._cents > other._cents;
  }

  isLessThan(other: PriceValue): boolean {
    return this._cents < other._cents;
  }

  equals(other: PriceValue): boolean {
    return this._cents === other._cents;
  }

  isZero(): boolean {
    return this._cents === 0;
  }

  /**
   * Calculate ratio between two prices
   * @returns ratio as decimal (e.g., 1.5 means this is 1.5x the other)
   */
  ratioTo(other: PriceValue): number {
    if (other.isZero()) {
      throw new Error("Cannot calculate ratio with zero price");
    }
    return this._cents / other._cents;
  }

  /**
   * Calculate percentage difference from another price
   * @returns percentage (e.g., -20 means this is 20% less than other)
   */
  percentDifferenceFrom(other: PriceValue): number {
    if (other.isZero()) {
      throw new Error("Cannot calculate percentage from zero price");
    }
    return ((this._cents - other._cents) / other._cents) * 100;
  }

  /**
   * Get the minimum of two prices
   */
  min(other: PriceValue): PriceValue {
    return this._cents < other._cents ? this : other;
  }

  /**
   * Get the maximum of two prices
   */
  max(other: PriceValue): PriceValue {
    return this._cents > other._cents ? this : other;
  }

  /**
   * Create a copy (immutability helper)
   */
  clone(): PriceValue {
    return PriceValue.fromCents(this._cents);
  }

  /**
   * String representation
   */
  toString(): string {
    return this.format();
  }

  /**
   * JSON serialization
   */
  toJSON(): number {
    return this._cents;
  }
}

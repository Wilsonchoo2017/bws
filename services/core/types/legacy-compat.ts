import type {
  IntrinsicValueInputs as LegacyIntrinsicValueInputs,
} from "../../../types/value-investing.ts";
import type {
  IntrinsicValueInputs,
  MarketInputs,
  PricingInputs,
  QualityInputs,
  RetirementInputs,
} from "./pricing.ts";

/**
 * Compatibility layer for migrating from flat interface to focused interfaces
 * Allows gradual refactoring without breaking existing code
 *
 * MIGRATION PATH:
 * 1. Use these converters to wrap old code
 * 2. Gradually update services to use new interfaces
 * 3. Remove this file once migration complete
 */

/**
 * Convert legacy flat inputs to new focused structure
 */
export function toFocusedInputs(
  legacy: LegacyIntrinsicValueInputs,
): IntrinsicValueInputs {
  const pricing: PricingInputs = {
    msrp: legacy.msrp,
    currentRetailPrice: legacy.currentRetailPrice,
    originalRetailPrice: legacy.originalRetailPrice,
    bricklinkAvgPrice: legacy.bricklinkAvgPrice,
    bricklinkMaxPrice: legacy.bricklinkMaxPrice,
    historicalPriceData: legacy.historicalPriceData,
  };

  const market: MarketInputs = {
    salesVelocity: legacy.salesVelocity,
    avgDaysBetweenSales: legacy.avgDaysBetweenSales,
    timesSold: legacy.timesSold,
    availableQty: legacy.availableQty,
    availableLots: legacy.availableLots,
    priceVolatility: legacy.priceVolatility,
    priceDecline: legacy.priceDecline,
    priceTrend: legacy.priceTrend,
  };

  const retirement: RetirementInputs = {
    retirementStatus: legacy.retirementStatus,
    yearsPostRetirement: legacy.yearsPostRetirement,
    yearReleased: legacy.yearReleased,
  };

  const quality: QualityInputs = {
    demandScore: legacy.demandScore,
    qualityScore: legacy.qualityScore,
    availabilityScore: legacy.availabilityScore,
    theme: legacy.theme,
    partsCount: legacy.partsCount,
  };

  return {
    pricing,
    market,
    retirement,
    quality,
  };
}

/**
 * Convert new focused structure back to legacy flat interface
 * Useful for maintaining backward compatibility during migration
 */
export function toLegacyInputs(
  focused: IntrinsicValueInputs,
): LegacyIntrinsicValueInputs {
  return {
    // Pricing
    msrp: focused.pricing.msrp,
    currentRetailPrice: focused.pricing.currentRetailPrice,
    originalRetailPrice: focused.pricing.originalRetailPrice,
    bricklinkAvgPrice: focused.pricing.bricklinkAvgPrice,
    bricklinkMaxPrice: focused.pricing.bricklinkMaxPrice,
    historicalPriceData: focused.pricing.historicalPriceData,

    // Market
    salesVelocity: focused.market.salesVelocity,
    avgDaysBetweenSales: focused.market.avgDaysBetweenSales,
    timesSold: focused.market.timesSold,
    availableQty: focused.market.availableQty,
    availableLots: focused.market.availableLots,
    priceVolatility: focused.market.priceVolatility,
    priceDecline: focused.market.priceDecline,
    priceTrend: focused.market.priceTrend,

    // Retirement
    retirementStatus: focused.retirement.retirementStatus,
    yearsPostRetirement: focused.retirement.yearsPostRetirement,
    yearReleased: focused.retirement.yearReleased,

    // Quality
    demandScore: focused.quality.demandScore,
    qualityScore: focused.quality.qualityScore,
    availabilityScore: focused.quality.availabilityScore,
    theme: focused.quality.theme,
    partsCount: focused.quality.partsCount,
  };
}

/**
 * Type guard to check if inputs are in new focused format
 */
export function isFocusedInputs(
  inputs: unknown,
): inputs is IntrinsicValueInputs {
  return (
    typeof inputs === "object" &&
    inputs !== null &&
    "pricing" in inputs &&
    "market" in inputs &&
    "retirement" in inputs &&
    "quality" in inputs
  );
}

/**
 * Type guard to check if inputs are in legacy flat format
 */
export function isLegacyInputs(
  inputs: unknown,
): inputs is LegacyIntrinsicValueInputs {
  return (
    typeof inputs === "object" &&
    inputs !== null &&
    !isFocusedInputs(inputs)
  );
}

/**
 * Normalize inputs to focused format regardless of input type
 * Useful for functions that need to accept both formats during migration
 */
export function normalizeInputs(
  inputs: LegacyIntrinsicValueInputs | IntrinsicValueInputs,
): IntrinsicValueInputs {
  if (isFocusedInputs(inputs)) {
    return inputs;
  }
  return toFocusedInputs(inputs);
}

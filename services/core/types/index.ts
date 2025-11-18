/**
 * Centralized type exports for the refactored value investing system
 *
 * SOLID PRINCIPLES APPLIED:
 * - Interface Segregation: Split large interfaces into focused ones
 * - Single Responsibility: Each interface has one clear purpose
 */

// Focused input interfaces
export type {
  IntrinsicValueInputs,
  MarketInputs,
  PricingInputs,
  QualityInputs,
  RetirementInputs,
} from "./pricing.ts";

// Legacy compatibility (to be removed after migration)
export {
  isFocusedInputs,
  isLegacyInputs,
  normalizeInputs,
  toLegacyInputs,
  toFocusedInputs,
} from "./legacy-compat.ts";

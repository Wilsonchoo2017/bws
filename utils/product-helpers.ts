import type { ProductSource } from "../db/schema.ts";

/**
 * Get badge color class based on units sold volume.
 * Higher volume products get more prominent badge colors.
 */
export function getSoldBadgeColor(unitsSold: number | null): string {
  if (unitsSold === null || unitsSold === 0) return "badge-ghost";
  if (unitsSold < 100) return "badge-info";
  if (unitsSold < 500) return "badge-success";
  if (unitsSold < 1000) return "badge-warning";
  return "badge-error"; // High volume (1000+)
}

/**
 * Get human-readable label for product platform source.
 */
export function getProductPlatformLabel(source: ProductSource): string {
  switch (source) {
    case "shopee":
      return "Shopee";
    case "toysrus":
      return 'Toys"R"Us';
    case "self":
      return "Manual";
    default:
      return source;
  }
}

/**
 * Get badge CSS class for product platform source.
 */
export function getProductPlatformBadgeClass(source: ProductSource): string {
  switch (source) {
    case "shopee":
      return "badge-primary";
    case "toysrus":
      return "badge-secondary";
    case "self":
      return "badge-accent";
    default:
      return "badge-ghost";
  }
}

/**
 * DealQualityCalculator
 *
 * Analyzes the quality of a deal by comparing current retail prices
 * against market prices and intrinsic value calculations.
 *
 * This helps identify when retail prices offer good value compared to
 * the secondary market (BrickLink) and fundamental worth.
 */

import type { Cents } from "../../types/price.ts";

export interface DealQualityInputs {
  // Current retail price (what you can buy it for now)
  currentRetailPrice?: Cents;

  // Original retail price before discount
  originalRetailPrice?: Cents;

  // BrickLink current market average (secondary market)
  bricklinkMarketPrice?: Cents;

  // Calculated intrinsic value (fundamental worth)
  intrinsicValue?: Cents;

  // MSRP (original manufacturer suggested retail price)
  msrp?: Cents;
}

export interface DealQualityMetrics {
  // Overall deal quality score (0-100)
  dealQualityScore: number;

  // Component scores
  retailDiscountScore: number;      // How good is the retail discount?
  priceToMarketScore: number;       // How does retail compare to market?
  priceToValueScore: number;        // How does retail compare to intrinsic value?

  // Raw metrics for display
  retailDiscountPercent: number;    // Percentage discount from original
  priceToMarketRatio: number;       // Retail / BrickLink market
  priceToValueRatio: number;        // Retail / Intrinsic value

  // Human-readable assessment
  dealQualityLabel: string;         // "Excellent", "Good", "Fair", etc.
  recommendation: string;           // Brief recommendation text
}

export class DealQualityCalculator {
  // Weights for composite score calculation
  private static readonly RETAIL_DISCOUNT_WEIGHT = 0.25;
  private static readonly PRICE_TO_MARKET_WEIGHT = 0.35;
  private static readonly PRICE_TO_VALUE_WEIGHT = 0.40;

  /**
   * Calculate comprehensive deal quality metrics
   */
  calculateDealQuality(inputs: DealQualityInputs): DealQualityMetrics {
    const retailDiscountScore = this.calculateRetailDiscountScore(
      inputs.currentRetailPrice,
      inputs.originalRetailPrice,
      inputs.msrp,
    );

    const priceToMarketScore = this.calculatePriceToMarketScore(
      inputs.currentRetailPrice,
      inputs.bricklinkMarketPrice,
    );

    const priceToValueScore = this.calculatePriceToValueScore(
      inputs.currentRetailPrice,
      inputs.intrinsicValue,
    );

    // Calculate composite deal quality score
    const dealQualityScore = this.calculateCompositeScore(
      retailDiscountScore,
      priceToMarketScore,
      priceToValueScore,
    );

    // Calculate raw metrics
    const retailDiscountPercent = this.calculateRetailDiscountPercent(
      inputs.currentRetailPrice,
      inputs.originalRetailPrice,
      inputs.msrp,
    );

    const priceToMarketRatio = this.calculatePriceRatio(
      inputs.currentRetailPrice,
      inputs.bricklinkMarketPrice,
    );

    const priceToValueRatio = this.calculatePriceRatio(
      inputs.currentRetailPrice,
      inputs.intrinsicValue,
    );

    // Generate human-readable assessment
    const dealQualityLabel = this.getDealQualityLabel(dealQualityScore);
    const recommendation = this.generateRecommendation(
      dealQualityScore,
      priceToMarketRatio,
      priceToValueRatio,
    );

    return {
      dealQualityScore,
      retailDiscountScore,
      priceToMarketScore,
      priceToValueScore,
      retailDiscountPercent,
      priceToMarketRatio,
      priceToValueRatio,
      dealQualityLabel,
      recommendation,
    };
  }

  /**
   * Score based on retail discount (0-100)
   * Higher discount = better score
   */
  private calculateRetailDiscountScore(
    currentRetailPrice?: Cents,
    originalRetailPrice?: Cents,
    msrp?: Cents,
  ): number {
    const discountPercent = this.calculateRetailDiscountPercent(
      currentRetailPrice,
      originalRetailPrice,
      msrp,
    );

    // Convert discount percentage to score
    // 0% discount = 50 points (neutral)
    // 20% discount = 70 points
    // 40% discount = 90 points
    // 50%+ discount = 100 points
    if (discountPercent <= 0) return 50;
    if (discountPercent >= 50) return 100;

    return 50 + (discountPercent * 1.0);
  }

  /**
   * Score based on price vs BrickLink market (0-100)
   * Lower retail vs market = better score
   */
  private calculatePriceToMarketScore(
    currentRetailPrice?: Cents,
    bricklinkMarketPrice?: Cents,
  ): number {
    if (!currentRetailPrice || !bricklinkMarketPrice) {
      return 50; // Neutral if no data
    }

    const ratio = currentRetailPrice / bricklinkMarketPrice;

    // Convert ratio to score
    // ratio <= 0.50 = 100 points (retail is 50% or less of market)
    // ratio = 0.75 = 85 points
    // ratio = 1.00 = 60 points (at market price)
    // ratio = 1.25 = 40 points
    // ratio >= 1.50 = 0 points (retail 50% above market)

    if (ratio <= 0.50) return 100;
    if (ratio >= 1.50) return 0;

    // Linear interpolation between key points
    if (ratio <= 1.00) {
      // 0.50 to 1.00 maps to 100 to 60
      return 100 - ((ratio - 0.50) / 0.50) * 40;
    } else {
      // 1.00 to 1.50 maps to 60 to 0
      return 60 - ((ratio - 1.00) / 0.50) * 60;
    }
  }

  /**
   * Score based on price vs intrinsic value (0-100)
   * Lower retail vs intrinsic value = better score
   */
  private calculatePriceToValueScore(
    currentRetailPrice?: Cents,
    intrinsicValue?: Cents,
  ): number {
    if (!currentRetailPrice || !intrinsicValue) {
      return 50; // Neutral if no data
    }

    const ratio = currentRetailPrice / intrinsicValue;

    // Convert ratio to score
    // This is the most important metric - buying below intrinsic value
    // ratio <= 0.60 = 100 points (retail is 60% or less of value - margin of safety)
    // ratio = 0.75 = 90 points (25% margin of safety)
    // ratio = 1.00 = 70 points (at intrinsic value)
    // ratio = 1.25 = 40 points
    // ratio >= 1.50 = 0 points (retail 50% above value)

    if (ratio <= 0.60) return 100;
    if (ratio >= 1.50) return 0;

    // Linear interpolation
    if (ratio <= 1.00) {
      // 0.60 to 1.00 maps to 100 to 70
      return 100 - ((ratio - 0.60) / 0.40) * 30;
    } else {
      // 1.00 to 1.50 maps to 70 to 0
      return 70 - ((ratio - 1.00) / 0.50) * 70;
    }
  }

  /**
   * Calculate weighted composite score
   */
  private calculateCompositeScore(
    retailDiscountScore: number,
    priceToMarketScore: number,
    priceToValueScore: number,
  ): number {
    const score = (
      retailDiscountScore * DealQualityCalculator.RETAIL_DISCOUNT_WEIGHT +
      priceToMarketScore * DealQualityCalculator.PRICE_TO_MARKET_WEIGHT +
      priceToValueScore * DealQualityCalculator.PRICE_TO_VALUE_WEIGHT
    );

    return Math.round(Math.max(0, Math.min(100, score)));
  }

  /**
   * Calculate retail discount percentage
   */
  private calculateRetailDiscountPercent(
    currentRetailPrice?: Cents,
    originalRetailPrice?: Cents,
    msrp?: Cents,
  ): number {
    if (!currentRetailPrice) return 0;

    // Use original retail price if available, otherwise fall back to MSRP
    const basePrice = originalRetailPrice || msrp;
    if (!basePrice) return 0;

    const discountPercent = ((basePrice - currentRetailPrice) / basePrice) * 100;
    return Math.max(0, Math.round(discountPercent * 10) / 10); // Round to 1 decimal
  }

  /**
   * Calculate price ratio (handles undefined values)
   */
  private calculatePriceRatio(
    numerator?: Cents,
    denominator?: Cents,
  ): number {
    if (!numerator || !denominator) return 1.0;
    return Math.round((numerator / denominator) * 100) / 100; // Round to 2 decimals
  }

  /**
   * Get human-readable label for deal quality score
   */
  private getDealQualityLabel(score: number): string {
    if (score >= 85) return "Excellent Deal";
    if (score >= 70) return "Very Good Deal";
    if (score >= 60) return "Good Deal";
    if (score >= 50) return "Fair Deal";
    if (score >= 40) return "Acceptable";
    if (score >= 30) return "Overpriced";
    return "Very Overpriced";
  }

  /**
   * Generate recommendation based on metrics
   */
  private generateRecommendation(
    dealQualityScore: number,
    priceToMarketRatio: number,
    priceToValueRatio: number,
  ): string {
    if (dealQualityScore >= 85) {
      return "Strong buy - Excellent value vs market and intrinsic worth";
    }

    if (dealQualityScore >= 70) {
      if (priceToValueRatio <= 0.75) {
        return "Buy recommended - Good margin of safety";
      }
      return "Buy recommended - Good deal vs current market";
    }

    if (dealQualityScore >= 60) {
      return "Consider buying - Decent value proposition";
    }

    if (dealQualityScore >= 50) {
      return "Fair price - Buy if needed, but not a great deal";
    }

    if (dealQualityScore >= 40) {
      return "Wait for discount - Price slightly high";
    }

    if (priceToMarketRatio > 1.2) {
      return "Overpriced - Retail price exceeds market value";
    }

    return "Wait for better price - Not recommended at current price";
  }
}

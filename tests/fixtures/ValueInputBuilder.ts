/**
 * Test fixture builder for IntrinsicValueInputs
 *
 * Purpose:
 * - Makes test data creation more readable
 * - Provides sensible defaults
 * - Follows Builder pattern for fluent API
 */

import type { IntrinsicValueInputs } from "../../types/value-investing.ts";
import type { Cents } from "../../types/price.ts";

/**
 * Builder for creating test IntrinsicValueInputs
 * Provides fluent API for constructing test data
 */
export class ValueInputBuilder {
  private inputs: IntrinsicValueInputs;

  private constructor() {
    // Sensible defaults that pass basic validation
    this.inputs = {
      msrp: 10000 as Cents, // $100
      demandScore: 60,
      qualityScore: 60,
      retirementStatus: "active",
    };
  }

  /**
   * Create a new builder with default values
   */
  static create(): ValueInputBuilder {
    return new ValueInputBuilder();
  }

  /**
   * Create a builder with typical "good investment" values
   */
  static goodInvestment(): ValueInputBuilder {
    return new ValueInputBuilder()
      .withMSRP(15000 as Cents) // $150
      .withDemandScore(75)
      .withQualityScore(80)
      .withRetirementStatus("retired")
      .withYearsPostRetirement(3)
      .withTheme("Star Wars")
      .withPartsCount(750)
      .withSalesVelocity(0.5); // Decent liquidity
  }

  /**
   * Create a builder with typical "poor investment" values
   */
  static poorInvestment(): ValueInputBuilder {
    return new ValueInputBuilder()
      .withMSRP(5000 as Cents) // $50
      .withDemandScore(30) // Low demand
      .withQualityScore(35) // Low quality
      .withSalesVelocity(0.01) // Poor liquidity
      .withAvailableQty(5000); // Oversaturated
  }

  /**
   * Create a builder with minimal data (tests data validation)
   */
  static minimal(): ValueInputBuilder {
    const builder = new ValueInputBuilder();
    builder.inputs = { msrp: 10000 as Cents }; // Only MSRP
    return builder;
  }

  // Pricing methods

  withMSRP(cents: Cents): this {
    this.inputs.msrp = cents;
    return this;
  }

  withCurrentRetailPrice(cents: Cents): this {
    this.inputs.currentRetailPrice = cents;
    return this;
  }

  withOriginalRetailPrice(cents: Cents): this {
    this.inputs.originalRetailPrice = cents;
    return this;
  }

  withBricklinkAvgPrice(cents: Cents): this {
    this.inputs.bricklinkAvgPrice = cents;
    return this;
  }

  withBricklinkMaxPrice(cents: Cents): this {
    this.inputs.bricklinkMaxPrice = cents;
    return this;
  }

  withHistoricalPrices(prices: Cents[]): this {
    this.inputs.historicalPriceData = prices;
    return this;
  }

  // Retirement methods

  withRetirementStatus(status: "active" | "retiring_soon" | "retired"): this {
    this.inputs.retirementStatus = status;
    return this;
  }

  withYearsPostRetirement(years: number): this {
    this.inputs.yearsPostRetirement = years;
    return this;
  }

  withYearReleased(year: number): this {
    this.inputs.yearReleased = year;
    return this;
  }

  // Quality/Demand methods

  withDemandScore(score: number): this {
    this.inputs.demandScore = score;
    return this;
  }

  withQualityScore(score: number): this {
    this.inputs.qualityScore = score;
    return this;
  }

  withAvailabilityScore(score: number): this {
    this.inputs.availabilityScore = score;
    return this;
  }

  // Market/Liquidity methods

  withSalesVelocity(velocity: number): this {
    this.inputs.salesVelocity = velocity;
    return this;
  }

  withAvgDaysBetweenSales(days: number): this {
    this.inputs.avgDaysBetweenSales = days;
    return this;
  }

  withTimesSold(count: number): this {
    this.inputs.timesSold = count;
    return this;
  }

  withPriceVolatility(volatility: number): this {
    this.inputs.priceVolatility = volatility;
    return this;
  }

  withPriceDecline(decline: number): this {
    this.inputs.priceDecline = decline;
    return this;
  }

  withPriceTrend(trend: number): this {
    this.inputs.priceTrend = trend;
    return this;
  }

  // Saturation methods

  withAvailableQty(qty: number): this {
    this.inputs.availableQty = qty;
    return this;
  }

  withAvailableLots(lots: number): this {
    this.inputs.availableLots = lots;
    return this;
  }

  // Set characteristics

  withTheme(theme: string): this {
    this.inputs.theme = theme;
    return this;
  }

  withPartsCount(count: number): this {
    this.inputs.partsCount = count;
    return this;
  }

  // Convenience methods for common scenarios

  /**
   * Configure as a pre-retirement opportunity
   */
  asPreRetirement(): this {
    return this
      .withRetirementStatus("retiring_soon")
      .withDemandScore(70)
      .withQualityScore(70)
      .withAvailableQty(50); // Limited supply
  }

  /**
   * Configure as a vintage collectible
   */
  asVintage(): this {
    return this
      .withRetirementStatus("retired")
      .withYearsPostRetirement(10)
      .withDemandScore(80)
      .withQualityScore(85)
      .withSalesVelocity(0.1) // Rare transactions
      .withAvailableQty(5); // Very limited
  }

  /**
   * Configure as an oversaturated market
   */
  asOversaturated(): this {
    return this
      .withAvailableQty(10000)
      .withAvailableLots(500)
      .withSalesVelocity(1.0); // 10000 days of inventory!
  }

  /**
   * Configure with zero sales (dead inventory)
   */
  asDeadInventory(): this {
    return this
      .withTimesSold(0)
      .withSalesVelocity(0)
      .withDemandScore(20);
  }

  /**
   * Build the final IntrinsicValueInputs object
   */
  build(): IntrinsicValueInputs {
    return { ...this.inputs };
  }
}

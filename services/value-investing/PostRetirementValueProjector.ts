/**
 * PostRetirementValueProjector - Future Value Prediction Engine
 *
 * Philosophy: "Ability to generate cash" = Ability to increase in value over time
 * Core question: What will this set be worth in 1/3/5 years based on supply/demand dynamics?
 *
 * Inspired by Mohnish Pabrai's focus on:
 * - Future cash flows (for us: future selling price)
 * - Catalysts (retirement = supply cut-off)
 * - Moats (themes with durable demand)
 */

// Note: Using `any` types because this projector accepts enriched/processed data
// from repositories, not the raw parser types. The data includes computed fields
// like avgPrice, salesVelocity, yearRetired, etc. that aren't on the base parser interfaces.

export interface ValueProjection {
  /** Current intrinsic value */
  currentValue: number;
  /** Projected value in 1 year */
  oneYearValue: number;
  /** Projected value in 3 years */
  threeYearValue: number;
  /** Projected value in 5 years */
  fiveYearValue: number;
  /** Expected annual appreciation rate */
  expectedCAGR: number; // Compound Annual Growth Rate
  /** When will available supply run out? (months) */
  supplyExhaustionMonths: number | null;
  /** Confidence in projection (0-100) */
  projectionConfidence: number;
  /** Key assumptions driving the projection */
  assumptions: string[];
  /** Risk factors that could invalidate projection */
  risks: string[];
}

export class PostRetirementValueProjector {
  /**
   * Project future value based on supply/demand dynamics
   */
  static projectFutureValue(
    currentIntrinsicValue: number,
    // deno-lint-ignore no-explicit-any
    bricklinkData: any | null,
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
    qualityScore: number,
  ): ValueProjection {
    // Calculate supply exhaustion timeline
    const supplyExhaustionMonths = this.calculateSupplyExhaustion(
      bricklinkData,
    );

    // Determine expected appreciation rate based on retirement status, demand, theme
    const expectedCAGR = this.calculateExpectedCAGR(
      worldBricksData,
      demandScore,
      qualityScore,
      supplyExhaustionMonths,
    );

    // Project values
    const oneYearValue = this.projectValue(currentIntrinsicValue, expectedCAGR, 1);
    const threeYearValue = this.projectValue(
      currentIntrinsicValue,
      expectedCAGR,
      3,
    );
    const fiveYearValue = this.projectValue(currentIntrinsicValue, expectedCAGR, 5);

    // Calculate projection confidence
    const projectionConfidence = this.calculateProjectionConfidence(
      bricklinkData,
      worldBricksData,
      demandScore,
    );

    // Document assumptions
    const assumptions = this.buildAssumptions(
      worldBricksData,
      expectedCAGR,
      supplyExhaustionMonths,
      demandScore,
    );

    // Document risks
    const risks = this.identifyRisks(
      worldBricksData,
      demandScore,
      qualityScore,
      supplyExhaustionMonths,
    );

    return {
      currentValue: currentIntrinsicValue,
      oneYearValue,
      threeYearValue,
      fiveYearValue,
      expectedCAGR,
      supplyExhaustionMonths,
      projectionConfidence,
      assumptions,
      risks,
    };
  }

  /**
   * Calculate when available supply will run out based on current velocity
   */
  private static calculateSupplyExhaustion(
    // deno-lint-ignore no-explicit-any
    bricklinkData: any | null,
  ): number | null {
    if (!bricklinkData) return null;

    const availableQty = bricklinkData.availableQty ?? 0;
    const salesVelocity = bricklinkData.salesVelocity ?? 0;

    if (availableQty === 0) return 0; // Already out of stock
    if (salesVelocity === 0) return null; // Not selling, infinite supply

    // Calculate daily sales rate
    const dailySalesRate = salesVelocity;

    // Calculate days until exhaustion
    const daysUntilExhaustion = availableQty / dailySalesRate;

    // Convert to months
    const monthsUntilExhaustion = daysUntilExhaustion / 30;

    return Math.round(monthsUntilExhaustion * 10) / 10; // Round to 1 decimal
  }

  /**
   * Calculate expected Compound Annual Growth Rate (CAGR)
   *
   * Based on:
   * - Retirement status (retired sets appreciate, active sets don't)
   * - Demand strength (high demand = higher appreciation)
   * - Quality score (quality sets hold value better)
   * - Supply exhaustion timeline (scarcity drives price)
   */
  private static calculateExpectedCAGR(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
    qualityScore: number,
    supplyExhaustionMonths: number | null,
  ): number {
    // Base CAGR assumptions by retirement status
    let baseCagr = 0;

    const status = worldBricksData?.status?.toLowerCase();
    const yearsRetired = this.getYearsRetired(worldBricksData);

    if (status === "retired") {
      // Retired sets appreciate, but rate depends on time since retirement
      if (yearsRetired !== null) {
        if (yearsRetired < 2) {
          baseCagr = 15; // Early retirement: strong appreciation (J-curve upswing)
        } else if (yearsRetired < 5) {
          baseCagr = 10; // Mid-retirement: moderate appreciation
        } else {
          baseCagr = 5; // Late retirement: slower appreciation (mature phase)
        }
      } else {
        baseCagr = 10; // Unknown retirement date, assume moderate
      }
    } else if (status === "retiring soon") {
      baseCagr = 8; // Pre-retirement: anticipatory appreciation
    } else {
      baseCagr = 0; // Active sets don't appreciate (supply keeps coming)
    }

    // Demand adjustment: High demand amplifies appreciation
    let demandMultiplier = 1.0;
    if (demandScore >= 80) {
      demandMultiplier = 1.5; // Exceptional demand
    } else if (demandScore >= 60) {
      demandMultiplier = 1.2; // Strong demand
    } else if (demandScore >= 40) {
      demandMultiplier = 1.0; // Moderate demand
    } else if (demandScore >= 20) {
      demandMultiplier = 0.7; // Weak demand
    } else {
      demandMultiplier = 0.3; // Very weak demand - kill the projection
    }

    // Quality adjustment: High quality sets appreciate better
    let qualityMultiplier = 1.0;
    if (qualityScore >= 80) {
      qualityMultiplier = 1.3; // Premium quality
    } else if (qualityScore >= 60) {
      qualityMultiplier = 1.1; // Good quality
    } else if (qualityScore >= 40) {
      qualityMultiplier = 1.0; // Average quality
    } else {
      qualityMultiplier = 0.8; // Poor quality
    }

    // Supply exhaustion bonus: Scarcity drives price
    let scarcityBonus = 0;
    if (supplyExhaustionMonths !== null) {
      if (supplyExhaustionMonths < 6) {
        scarcityBonus = 10; // Running out fast! Big bonus
      } else if (supplyExhaustionMonths < 12) {
        scarcityBonus = 5; // Running out soon, moderate bonus
      } else if (supplyExhaustionMonths < 24) {
        scarcityBonus = 2; // Will run out eventually, small bonus
      }
      // If > 24 months, no scarcity bonus (plenty of supply)
    }

    // Calculate final CAGR
    const expectedCAGR = (baseCagr * demandMultiplier * qualityMultiplier) +
      scarcityBonus;

    // Cap at reasonable bounds
    return Math.max(-10, Math.min(50, expectedCAGR)); // -10% to +50% CAGR
  }

  /**
   * Project value forward N years using CAGR
   */
  private static projectValue(
    currentValue: number,
    cagr: number,
    years: number,
  ): number {
    const growthMultiplier = Math.pow(1 + (cagr / 100), years);
    return Math.round(currentValue * growthMultiplier * 100) / 100;
  }

  /**
   * Calculate confidence in projection (0-100)
   */
  private static calculateProjectionConfidence(
    // deno-lint-ignore no-explicit-any
    bricklinkData: any | null,
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
  ): number {
    let confidence = 50; // Start at medium

    // Retirement status clarity
    if (worldBricksData?.status === "retired") {
      confidence += 20; // Clear catalyst
    } else if (worldBricksData?.status === "retiring soon") {
      confidence += 10; // Near-term catalyst
    } else {
      confidence -= 20; // No catalyst, very uncertain
    }

    // Sales history depth
    const timesSold = bricklinkData?.timesSold ?? 0;
    if (timesSold >= 50) {
      confidence += 20; // Lots of data
    } else if (timesSold >= 10) {
      confidence += 10; // Decent data
    } else if (timesSold < 3) {
      confidence -= 20; // Very little data
    }

    // Demand stability
    if (demandScore >= 60) {
      confidence += 10; // Strong, stable demand
    } else if (demandScore < 30) {
      confidence -= 15; // Weak, unstable demand
    }

    // Price history for trend analysis
    if (bricklinkData?.priceHistory && bricklinkData.priceHistory.length >= 6) {
      confidence += 10; // Good historical trend data
    }

    return Math.max(0, Math.min(100, confidence));
  }

  /**
   * Build list of key assumptions
   */
  private static buildAssumptions(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    expectedCAGR: number,
    supplyExhaustionMonths: number | null,
    demandScore: number,
  ): string[] {
    const assumptions: string[] = [];

    // Retirement assumption
    const status = worldBricksData?.status?.toLowerCase();
    if (status === "retired") {
      assumptions.push("Set is retired - no new supply will be produced");
    } else if (status === "retiring soon") {
      assumptions.push("Set will retire soon - supply will stop");
    } else {
      assumptions.push(
        "Set is still active - appreciation unlikely until retirement",
      );
    }

    // Demand assumption
    if (demandScore >= 60) {
      assumptions.push("Current strong demand will persist");
    } else if (demandScore >= 40) {
      assumptions.push("Current moderate demand will persist");
    } else {
      assumptions.push(
        "Current weak demand may limit appreciation regardless of scarcity",
      );
    }

    // Supply assumption
    if (supplyExhaustionMonths !== null && supplyExhaustionMonths < 24) {
      assumptions.push(
        `Available supply will exhaust in ~${supplyExhaustionMonths} months at current velocity`,
      );
    } else if (supplyExhaustionMonths !== null) {
      assumptions.push("Ample supply exists - scarcity is not imminent");
    }

    // Growth assumption
    if (expectedCAGR > 0) {
      assumptions.push(`Expected ${expectedCAGR.toFixed(1)}% annual appreciation`);
    } else {
      assumptions.push("No appreciation expected (may depreciate)");
    }

    return assumptions;
  }

  /**
   * Identify key risks to projection
   */
  private static identifyRisks(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
    qualityScore: number,
    supplyExhaustionMonths: number | null,
  ): string[] {
    const risks: string[] = [];

    // Demand risk
    if (demandScore < 40) {
      risks.push(
        "WEAK DEMAND: Low current demand may not support price appreciation",
      );
    }

    // Quality risk
    if (qualityScore < 40) {
      risks.push(
        "LOW QUALITY: Poor quality sets typically don't appreciate well",
      );
    }

    // Supply risk
    if (supplyExhaustionMonths === null || supplyExhaustionMonths > 36) {
      risks.push(
        "OVERSUPPLY: Large available inventory may suppress prices for years",
      );
    }

    // Reissue risk (theme-based)
    const theme = worldBricksData?.theme?.toLowerCase() ?? "";
    if (
      theme.includes("city") || theme.includes("friends") ||
      theme.includes("duplo")
    ) {
      risks.push(
        "REISSUE RISK: Theme has history of similar sets being re-released",
      );
    }

    // Active set risk
    if (worldBricksData?.status?.toLowerCase() === "active") {
      risks.push(
        "ACTIVE SET: Continued production will prevent appreciation until retirement",
      );
    }

    // Theme risk
    if (
      theme.includes("licensed") === false &&
      !["architecture", "creator expert", "ideas"].some((t) =>
        theme.includes(t)
      )
    ) {
      risks.push(
        "THEME RISK: Theme lacks strong collector community for long-term value",
      );
    }

    return risks.length > 0 ? risks : ["No major risks identified"];
  }

  /**
   * Helper: Calculate years since retirement
   */
  private static getYearsRetired(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
  ): number | null {
    if (!worldBricksData?.yearRetired) return null;

    const currentYear = new Date().getFullYear();
    const yearRetired = worldBricksData.yearRetired;

    return currentYear - yearRetired;
  }

  /**
   * Helper: Calculate months of inventory at current sales rate
   */
  static calculateMonthsOfInventory(
    // deno-lint-ignore no-explicit-any
    bricklinkData: any | null,
  ): number | null {
    if (!bricklinkData) return null;

    const availableQty = bricklinkData.availableQty ?? 0;
    const salesVelocity = bricklinkData.salesVelocity ?? 0;

    if (salesVelocity === 0) return null; // No sales = infinite inventory

    // Sales velocity is in units/day
    const monthlyVelocity = salesVelocity * 30;

    if (monthlyVelocity === 0) return null;

    return Math.round((availableQty / monthlyVelocity) * 10) / 10;
  }

  /**
   * Helper: Is this a "buy before retirement" opportunity?
   * Criteria: Retiring soon + Strong demand + Limited time to accumulate
   */
  static isPreRetirementOpportunity(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
  ): boolean {
    if (!worldBricksData) return false;

    const status = worldBricksData.status?.toLowerCase();
    const isRetiringSoon = status === "retiring soon";
    const hasStrongDemand = demandScore >= 50; // Must have at least moderate demand

    return isRetiringSoon && hasStrongDemand;
  }

  /**
   * Helper: Is this set in the "value appreciation phase"?
   * Retired + 0-5 years + Strong demand = Sweet spot
   */
  static isInAppreciationPhase(
    // deno-lint-ignore no-explicit-any
    worldBricksData: any | null,
    demandScore: number,
  ): boolean {
    if (!worldBricksData) return false;

    const status = worldBricksData.status?.toLowerCase();
    const yearsRetired = this.getYearsRetired(worldBricksData);

    const isRetired = status === "retired";
    const isEarlyRetirement = yearsRetired !== null && yearsRetired <= 5;
    const hasStrongDemand = demandScore >= 50;

    return isRetired && isEarlyRetirement && hasStrongDemand;
  }
}

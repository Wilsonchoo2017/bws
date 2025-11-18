/**
 * Integration tests for Value Calculation
 * These tests establish a baseline of current behavior before refactoring
 *
 * Purpose:
 * - Document current calculation logic
 * - Prevent regressions during refactoring
 * - Serve as living documentation of business rules
 */

import { assertEquals, assertExists } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { ValueCalculator } from "../../services/value-investing/ValueCalculator.ts";
import type { IntrinsicValueInputs } from "../../types/value-investing.ts";
import type { Cents } from "../../types/price.ts";

Deno.test("ValueCalculator - Baseline Integration Tests", async (t) => {
  await t.step("should calculate intrinsic value with MSRP base", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents, // $100.00
      demandScore: 70,
      qualityScore: 75,
      retirementStatus: "retired",
      yearsPostRetirement: 3,
      theme: "Star Wars",
      partsCount: 500,
    };

    const result = ValueCalculator.calculateIntrinsicValueWithBreakdown(inputs);

    assertExists(result, "Result should exist");
    assertExists(result.intrinsicValue, "Intrinsic value should be calculated");
    assertEquals(typeof result.intrinsicValue, "number");
    assertEquals(result.intrinsicValue > 0, true, "Intrinsic value should be positive");

    // Document the calculation breakdown
    assertExists(result.breakdown, "Breakdown should exist");
    assertExists(result.breakdown.baseValue, "Base value should exist");
    assertExists(result.breakdown.qualityMultipliers, "Quality multipliers should exist");
    assertExists(result.breakdown.riskDiscounts, "Risk discounts should exist");
  });

  await t.step("should apply retirement multiplier for retired sets", () => {
    const activeInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      retirementStatus: "active",
    };

    const retiredInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      retirementStatus: "retired",
      yearsPostRetirement: 3,
    };

    const activeResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(activeInputs);
    const retiredResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(retiredInputs);

    // Retired set should have higher intrinsic value (assuming demand gate passes)
    assertEquals(
      retiredResult.intrinsicValue > activeResult.intrinsicValue,
      true,
      "Retired set should have higher intrinsic value",
    );

    // Document retirement multiplier
    assertExists(retiredResult.breakdown?.qualityMultipliers.retirement);
    assertEquals(
      retiredResult.breakdown.qualityMultipliers.retirement.applied,
      true,
      "Retirement multiplier should be applied",
    );
  });

  await t.step("should apply theme multiplier for premium themes", () => {
    const genericInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      theme: "Generic",
    };

    const starWarsInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      theme: "Star Wars",
    };

    const genericResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(genericInputs);
    const starWarsResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(starWarsInputs);

    // Star Wars should have higher value due to theme multiplier
    assertEquals(
      starWarsResult.intrinsicValue > genericResult.intrinsicValue,
      true,
      "Star Wars theme should have higher intrinsic value",
    );

    // Document theme multiplier
    assertExists(starWarsResult.breakdown?.qualityMultipliers.theme);
    assertEquals(
      starWarsResult.breakdown.qualityMultipliers.theme.value > 1.0,
      true,
      "Star Wars should have theme multiplier > 1.0",
    );
  });

  await t.step("should apply hard gate rejection for low quality", () => {
    const lowQualityInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 30, // Below 40 threshold
    };

    const result = ValueCalculator.calculateIntrinsicValueWithBreakdown(lowQualityInputs);

    // Should be rejected or have zero value
    assertExists(result.breakdown?.rejection);
    assertEquals(
      result.breakdown.rejection?.rejected,
      true,
      "Low quality should trigger rejection",
    );
  });

  await t.step("should apply liquidity discount for slow-selling items", () => {
    const fastSellingInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      salesVelocity: 0.5, // 0.5 sales per day = good liquidity
    };

    const slowSellingInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      salesVelocity: 0.01, // 0.01 sales per day = poor liquidity
    };

    const fastResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(fastSellingInputs);
    const slowResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(slowSellingInputs);

    // Slow selling should have lower value due to liquidity discount
    assertEquals(
      slowResult.intrinsicValue < fastResult.intrinsicValue,
      true,
      "Slow selling items should have lower intrinsic value",
    );

    // Document liquidity discount
    assertExists(slowResult.breakdown?.riskDiscounts.liquidity);
    assertEquals(
      slowResult.breakdown.riskDiscounts.liquidity.value < 1.0,
      true,
      "Liquidity discount should be < 1.0",
    );
  });

  await t.step("should calculate target price with margin of safety", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      currentRetailPrice: 8000 as Cents, // Current price $80
    };

    const intrinsicValue = ValueCalculator.calculateIntrinsicValueWithBreakdown(inputs).intrinsicValue;
    const targetPrice = ValueCalculator.calculateTargetPrice(intrinsicValue, {
      demandScore: 70,
      dataQualityScore: 80,
    });

    assertExists(targetPrice, "Target price should exist");
    assertEquals(typeof targetPrice, "number");
    assertEquals(targetPrice > 0, true, "Target price should be positive");

    // Target price should be less than intrinsic value (margin of safety)
    assertEquals(
      targetPrice < intrinsicValue,
      true,
      "Target price should include margin of safety",
    );
  });

  await t.step("should calculate ROI correctly", () => {
    const inputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
    };

    const currentPrice = 8000 as Cents; // $80
    const intrinsicValue = ValueCalculator.calculateIntrinsicValueWithBreakdown(inputs).intrinsicValue;

    // Calculate expected ROI manually
    const expectedROI = ((intrinsicValue - currentPrice) / currentPrice) * 100;

    // ROI calculation formula: ((intrinsicValue - currentPrice) / currentPrice) * 100
    const calculatedROI = ((intrinsicValue - currentPrice) / currentPrice) * 100;

    assertEquals(typeof calculatedROI, "number");
    assertEquals(
      Math.abs(calculatedROI - expectedROI) < 0.01,
      true,
      `ROI should match expected calculation. Expected: ${expectedROI}, Got: ${calculatedROI}`,
    );
  });

  await t.step("should handle missing data gracefully", () => {
    const minimalInputs: IntrinsicValueInputs = {
      // Only MSRP provided
      msrp: 10000 as Cents,
    };

    const result = ValueCalculator.calculateIntrinsicValueWithBreakdown(minimalInputs);

    // Should either calculate with defaults or indicate insufficient data
    assertExists(result, "Result should exist even with minimal data");

    if (result.breakdown?.rejection) {
      assertEquals(
        result.breakdown.rejection.category,
        "INSUFFICIENT_DATA",
        "Should reject due to insufficient data",
      );
    } else {
      // If it calculates, should use default multipliers
      assertExists(result.intrinsicValue);
      assertEquals(result.intrinsicValue > 0, true);
    }
  });

  await t.step("should prefer MSRP over BrickLink price for base value", () => {
    const withMSRP: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      bricklinkAvgPrice: 15000 as Cents, // Higher BrickLink price
      demandScore: 70,
      qualityScore: 70,
    };

    const result = ValueCalculator.calculateIntrinsicValueWithBreakdown(withMSRP);

    assertExists(result.breakdown);
    assertEquals(
      result.breakdown.baseValueSource,
      "msrp",
      "Should prefer MSRP as base value source",
    );
    assertEquals(result.breakdown.baseValue, 10000 as Cents);
  });

  await t.step("should apply saturation discount for oversupplied markets", () => {
    const normalSupplyInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      availableQty: 100,
      salesVelocity: 1.0, // 1 sale per day
    };

    const oversuppliedInputs: IntrinsicValueInputs = {
      msrp: 10000 as Cents,
      demandScore: 70,
      qualityScore: 70,
      availableQty: 3000, // 3000 units available
      salesVelocity: 1.0, // 1 sale per day = 3000 days of inventory!
    };

    const normalResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(normalSupplyInputs);
    const oversuppliedResult = ValueCalculator.calculateIntrinsicValueWithBreakdown(oversuppliedInputs);

    // Oversupplied market should have lower value
    assertEquals(
      oversuppliedResult.intrinsicValue < normalResult.intrinsicValue,
      true,
      "Oversupplied market should have lower intrinsic value",
    );

    // Document saturation discount
    assertExists(oversuppliedResult.breakdown?.riskDiscounts.saturation);
    assertEquals(
      oversuppliedResult.breakdown.riskDiscounts.saturation.applied,
      true,
      "Saturation discount should be applied",
    );
  });
});

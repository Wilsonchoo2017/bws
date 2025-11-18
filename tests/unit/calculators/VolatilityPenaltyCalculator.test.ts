/**
 * Unit tests for VolatilityPenaltyCalculator
 * Tests context-aware volatility penalty logic
 */

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import { VolatilityPenaltyCalculator } from "../../../services/core/calculators/VolatilityPenaltyCalculator.ts";

Deno.test("VolatilityPenaltyCalculator - Unit Tests", async (t) => {
  const calculator = new VolatilityPenaltyCalculator();

  await t.step("should return 1.0 (no penalty) with no data", () => {
    const result = calculator.calculate({});
    assertEquals(result.multiplier, 1.0);
    assertEquals(result.context, "no_data");
  });

  await t.step("should return 1.0 for negative volatility", () => {
    const result = calculator.calculate({ priceVolatility: -0.5 });
    assertEquals(result.multiplier, 1.0);
  });

  await t.step("should handle retired set with rising prices (good volatility)", () => {
    const result = calculator.calculate({
      priceVolatility: 0.5,
      retirementStatus: "retired",
      yearsPostRetirement: 5,
      priceTrend: 0.2,
    });
    assertEquals(result.multiplier, 1.0);
    assertEquals(result.context, "retired_rising");
  });

  await t.step("should penalize retired set with falling prices (bad volatility)", () => {
    const result = calculator.calculate({
      priceVolatility: 0.4,
      retirementStatus: "retired",
      yearsPostRetirement: 5,
      priceTrend: -0.2,
    });
    assertEquals(result.multiplier, 0.85);
    assertEquals(result.context, "retired_falling");
  });

  await t.step("should apply mild penalty for stable falling prices", () => {
    const result = calculator.calculate({
      priceVolatility: 0.15,
      retirementStatus: "retired",
      yearsPostRetirement: 5,
      priceTrend: -0.1,
    });
    assertEquals(result.multiplier, 0.95);
  });

  await t.step("should apply standard penalty for active sets with volatility", () => {
    const result = calculator.calculate({
      priceVolatility: 0.3,
      retirementStatus: "active",
    });
    assertEquals(result.multiplier <= 0.95, true);
    assertEquals(result.context, "active_volatile");
  });

  await t.step("should cap maximum discount at 12%", () => {
    const result = calculator.calculate({
      priceVolatility: 1.0,
      retirementStatus: "active",
    });
    assertEquals(result.multiplier >= 0.88, true);
  });

  await t.step("should not penalize recently retired sets (< 2 years)", () => {
    const result = calculator.calculate({
      priceVolatility: 0.5,
      retirementStatus: "retired",
      yearsPostRetirement: 1,
    });
    assertEquals(result.multiplier < 1.0, true);
  });

  await t.step("should provide detailed explanation", () => {
    const result = calculator.calculate({
      priceVolatility: 0.3,
      retirementStatus: "active",
    });
    assertExists(result.explanation);
    assertEquals(result.isPenalized, true);
  });
});
